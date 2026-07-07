"""Output-based feature extraction for QD search.

This complements feature_extractor.py (which extracts context features).
Output features capture *behavioral* characteristics of generated solutions,
defining the quality-diversity search space.

Key distinction:
- Context features: What was asked for (prompt characteristics)
- Output features: How the solution behaves (solution characteristics)

QD search needs OUTPUT features to distinguish behavioral niches.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class FeatureVector:
    """Normalized feature vector with metadata."""

    values: np.ndarray  # Normalized features in [0, 1]
    names: List[str]  # Feature names for interpretability
    raw_values: Dict[str, float]  # Pre-normalization values
    metadata: Dict[str, Any] = None  # Domain-specific context

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        assert len(self.values) == len(self.names), "Dimension mismatch"
        # Allow slight numerical tolerance for [0, 1] bounds
        assert all(-1e-6 <= v <= 1.0 + 1e-6 for v in self.values), \
            f"Features must be normalized to [0,1], got {self.values}"

    def distance(self, other: FeatureVector) -> float:
        """Euclidean distance in normalized feature space."""
        return float(np.linalg.norm(self.values - other.values))

    def to_dict(self) -> dict:
        """Serialize for storage/logging."""
        return {
            "values": self.values.tolist(),
            "names": self.names,
            "raw_values": self.raw_values,
            "metadata": self.metadata,
        }


class FeatureFunction(ABC):
    """Base class for individual feature extractors.

    Each feature function computes a single scalar from (input, output, context).
    Features are composed into an OutputFeatureExtractor ensemble.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Feature name for interpretability."""
        pass

    @abstractmethod
    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        """Extract raw feature value.

        Args:
            input: The input/prompt/query that generated this output
            output: The generated output/solution to characterize
            context: Additional context (evaluation results, metadata, etc.)

        Returns:
            Raw feature value (will be normalized by OutputFeatureExtractor)
        """
        pass

    @property
    def expected_range(self) -> tuple[float, float]:
        """Expected (min, max) range for normalization.

        Override if you know the theoretical bounds. Otherwise OutputFeatureExtractor
        will normalize based on observed values in the archive.
        """
        return (0.0, 1.0)  # Default: assume already normalized


class OutputFeatureExtractor:
    """Ensemble of feature functions with automatic normalization.

    Computes feature vectors for generated outputs, maintaining normalization
    statistics across the archive to ensure consistent behavioral space.
    """

    def __init__(self, features: Sequence[FeatureFunction]):
        self.features = list(features)
        self.feature_names = [f.name for f in self.features]

        # Normalization statistics (updated as archive grows)
        self._observed_mins = {}
        self._observed_maxs = {}

        # Initialize with theoretical ranges if available
        for f in self.features:
            min_val, max_val = f.expected_range
            self._observed_mins[f.name] = min_val
            self._observed_maxs[f.name] = max_val

    def extract(
        self,
        input: Any,
        output: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> FeatureVector:
        """Extract and normalize features for an output.

        Args:
            input: The input/prompt that generated this output
            output: The generated output/solution to characterize
            context: Additional context (evaluation results, metadata, etc.)

        Returns:
            Normalized FeatureVector in [0, 1]^n space
        """
        ctx = context or {}
        raw_values = {}

        # Extract raw features
        for f in self.features:
            try:
                raw_values[f.name] = f.extract(input, output, ctx)
            except Exception as e:
                # Graceful degradation: use 0.5 (middle) if extraction fails
                raw_values[f.name] = 0.5
                ctx.setdefault('extraction_errors', []).append(
                    f"Feature {f.name} failed: {e}"
                )

        # Update normalization statistics
        for name, value in raw_values.items():
            if not np.isfinite(value):
                # Handle inf/nan gracefully
                raw_values[name] = 0.5
                continue

            current_min = self._observed_mins.get(name, float('inf'))
            current_max = self._observed_maxs.get(name, float('-inf'))

            self._observed_mins[name] = min(current_min, value)
            self._observed_maxs[name] = max(current_max, value)

        # Normalize to [0, 1]
        normalized = []
        for name in self.feature_names:
            raw = raw_values[name]
            min_val = self._observed_mins[name]
            max_val = self._observed_maxs[name]

            if max_val > min_val + 1e-9:
                norm = (raw - min_val) / (max_val - min_val)
            else:
                # All observed values are identical - use middle of range
                norm = 0.5

            # Clamp to [0, 1] with small tolerance
            norm = max(0.0, min(1.0, norm))
            normalized.append(norm)

        return FeatureVector(
            values=np.array(normalized),
            names=self.feature_names,
            raw_values=raw_values,
            metadata=ctx,
        )

    def dimension(self) -> int:
        """Number of features in the behavioral characterization."""
        return len(self.features)

    def reset_normalization(self):
        """Reset observed statistics (use when starting new archive)."""
        self._observed_mins = {}
        self._observed_maxs = {}
        for f in self.features:
            min_val, max_val = f.expected_range
            self._observed_mins[f.name] = min_val
            self._observed_maxs[f.name] = max_val


# ============================================================================
# Generic Output Features (applicable to text outputs)
# ============================================================================

class OutputLengthFeature(FeatureFunction):
    """Character length of the output."""

    @property
    def name(self) -> str:
        return "output_length"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if isinstance(output, str):
            return float(len(output))
        return 0.0

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 10000.0)  # Reasonable for most text outputs


class OutputLineCountFeature(FeatureFunction):
    """Number of lines in the output."""

    @property
    def name(self) -> str:
        return "output_lines"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if isinstance(output, str):
            return float(len(output.splitlines()))
        return 0.0

    @property
    def expected_range(self) -> tuple[float, float]:
        return (1.0, 500.0)


class OutputTokenCountFeature(FeatureFunction):
    """Approximate token count (whitespace split)."""

    @property
    def name(self) -> str:
        return "output_tokens"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if isinstance(output, str):
            return float(len(output.split()))
        return 0.0

    @property
    def expected_range(self) -> tuple[float, float]:
        return (1.0, 5000.0)


# ============================================================================
# Evaluation-Derived Features (from evaluator ensemble)
# ============================================================================

class EvaluatorDiversityFeature(FeatureFunction):
    """Evaluator diversity = disagreement among judges.

    High diversity means the output is on a quality boundary
    (some judges like it, others don't). These are often the
    most interesting candidates for exploration.
    """

    @property
    def name(self) -> str:
        return "eval_diversity"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        eval_result = context.get('evaluation_result')
        if eval_result and hasattr(eval_result, 'diversity'):
            return float(eval_result.diversity)
        # No evaluation available - use neutral value
        return 0.5

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


class EvaluatorConsensusFeature(FeatureFunction):
    """Absolute consensus magnitude (ignoring sign).

    High consensus = clear quality signal, low = controversial.
    """

    @property
    def name(self) -> str:
        return "eval_consensus"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        eval_result = context.get('evaluation_result')
        if eval_result and hasattr(eval_result, 'consensus'):
            # Map [-1, 1] -> [0, 1] using absolute value
            return float(abs(eval_result.consensus))
        return 0.5

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


# ============================================================================
# Code-Specific Features (for code generation tasks)
# ============================================================================

class CodeComplexityFeature(FeatureFunction):
    """Cyclomatic complexity proxy (count of control flow keywords)."""

    @property
    def name(self) -> str:
        return "code_complexity"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.0

        # Count control flow keywords
        keywords = ['if', 'elif', 'else', 'for', 'while', 'try', 'except',
                    'switch', 'case', 'catch', 'finally']

        count = sum(output.lower().count(kw) for kw in keywords)
        return float(count)

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 50.0)


class CodeFunctionCountFeature(FeatureFunction):
    """Number of function definitions."""

    @property
    def name(self) -> str:
        return "code_functions"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.0

        # Count function definitions (rough heuristic)
        count = output.count('def ') + output.count('function ')
        return float(count)

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 20.0)


class CodeCommentRatioFeature(FeatureFunction):
    """Ratio of comment lines to total lines."""

    @property
    def name(self) -> str:
        return "code_comment_ratio"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.0

        lines = output.splitlines()
        if not lines:
            return 0.0

        # Count lines with comments (rough heuristic)
        comment_count = sum(1 for line in lines
                            if line.strip().startswith(('#', '//', '/*', '*')))

        return comment_count / len(lines)

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


# ============================================================================
# Docstring-Specific Features
# ============================================================================

class DocstringClarityFeature(FeatureFunction):
    """Measures docstring clarity via sentence complexity.

    Short sentences + concrete language = high clarity.
    """

    @property
    def name(self) -> str:
        return "docstring_clarity"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.5

        # Split into sentences
        sentences = [s.strip() for s in output.split('.') if s.strip()]
        if not sentences:
            return 0.5

        # Average words per sentence (clarity inversely related to length)
        word_counts = [len(s.split()) for s in sentences]
        avg_words = sum(word_counts) / len(word_counts)

        # Map to [0, 1]: shorter = clearer (up to a point)
        # Sweet spot: 10-15 words per sentence
        # Below 10: might be too terse
        # Above 20: getting complex
        if avg_words < 10:
            clarity = 0.7 + (avg_words / 10) * 0.3  # 0.7-1.0
        elif avg_words < 20:
            clarity = 1.0 - ((avg_words - 10) / 10) * 0.3  # 1.0-0.7
        else:
            clarity = 0.7 - min((avg_words - 20) / 20, 0.7)  # 0.7-0.0

        return max(0.0, min(1.0, clarity))

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


class DocstringCompletenessFeature(FeatureFunction):
    """Measures docstring completeness via structural elements.

    Complete docstrings have: summary, args, returns, examples.
    """

    @property
    def name(self) -> str:
        return "docstring_completeness"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.0

        output_lower = output.lower()

        # Check for common docstring sections
        has_args = 'args:' in output_lower or 'parameters:' in output_lower or 'param ' in output_lower
        has_returns = 'returns:' in output_lower or 'return:' in output_lower
        has_example = 'example' in output_lower or '>>>' in output
        has_raises = 'raises:' in output_lower or 'raise ' in output_lower

        # Score based on presence of sections
        score = 0.25  # Base score for existing
        if has_args:
            score += 0.25
        if has_returns:
            score += 0.25
        if has_example or has_raises:
            score += 0.25

        return score

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


class DocstringKeywordDensityFeature(FeatureFunction):
    """Measures technical keyword density in docstring."""

    @property
    def name(self) -> str:
        return "docstring_keyword_density"

    def extract(self, input: Any, output: Any, context: Dict[str, Any]) -> float:
        if not isinstance(output, str):
            return 0.0

        # Technical keywords common in good docstrings
        keywords = [
            'function', 'method', 'class', 'object', 'parameter',
            'returns', 'raises', 'example', 'note', 'warning',
            'optional', 'required', 'default', 'type', 'value',
        ]

        words = output.lower().split()
        if not words:
            return 0.0

        keyword_count = sum(1 for word in words if any(kw in word for kw in keywords))
        density = keyword_count / len(words)

        # Normalize: good docstrings have ~5-15% keyword density
        if density < 0.05:
            return density / 0.05  # Scale 0-0.05 -> 0-1
        elif density < 0.15:
            return 1.0  # Sweet spot
        else:
            return max(0.0, 1.0 - (density - 0.15) / 0.15)  # Decline after 15%

    @property
    def expected_range(self) -> tuple[float, float]:
        return (0.0, 1.0)


# ============================================================================
# Factory Functions
# ============================================================================

def create_code_output_extractor() -> OutputFeatureExtractor:
    """Create feature extractor for code generation outputs.

    Focuses on behavioral characteristics: complexity, structure,
    and evaluation-derived quality boundaries.
    """
    return OutputFeatureExtractor([
        OutputLineCountFeature(),
        CodeComplexityFeature(),
        CodeFunctionCountFeature(),
        CodeCommentRatioFeature(),
        EvaluatorDiversityFeature(),
        EvaluatorConsensusFeature(),
    ])


def create_docstring_output_extractor() -> OutputFeatureExtractor:
    """Create feature extractor for docstring generation outputs.

    Focuses on docstring-specific qualities: clarity, completeness,
    and technical keyword usage.
    """
    return OutputFeatureExtractor([
        OutputLineCountFeature(),
        DocstringClarityFeature(),
        DocstringCompletenessFeature(),
        DocstringKeywordDensityFeature(),
        EvaluatorDiversityFeature(),
        EvaluatorConsensusFeature(),
    ])


def create_generic_output_extractor() -> OutputFeatureExtractor:
    """Create minimal feature extractor for testing/prototyping."""
    return OutputFeatureExtractor([
        OutputLengthFeature(),
        OutputTokenCountFeature(),
        EvaluatorDiversityFeature(),
    ])


# ============================================================================
# Feature Extractor Registry
# ============================================================================

from typing import Callable

_FEATURE_EXTRACTOR_REGISTRY: Dict[str, Callable[[], OutputFeatureExtractor]] = {
    "code": create_code_output_extractor,
    "docstring": create_docstring_output_extractor,
    "text": create_generic_output_extractor,
    "generic": create_generic_output_extractor,
}


def get_feature_extractor(domain: str) -> OutputFeatureExtractor:
    """Get feature extractor for a specific domain.

    Args:
        domain: Domain name ("code", "docstring", "text", "generic")

    Returns:
        Configured OutputFeatureExtractor for the domain

    Raises:
        ValueError: If domain is not registered
    """
    factory = _FEATURE_EXTRACTOR_REGISTRY.get(domain)
    if not factory:
        available = ", ".join(_FEATURE_EXTRACTOR_REGISTRY.keys())
        raise ValueError(f"Unknown domain: {domain}. Available: {available}")
    return factory()


def register_feature_extractor(
    domain: str,
    factory: Callable[[], OutputFeatureExtractor]
):
    """Register a custom feature extractor factory.

    Args:
        domain: Domain name (will override existing if duplicate)
        factory: Callable that returns an OutputFeatureExtractor
    """
    _FEATURE_EXTRACTOR_REGISTRY[domain] = factory


def list_available_domains() -> List[str]:
    """List all registered feature extractor domains."""
    return list(_FEATURE_EXTRACTOR_REGISTRY.keys())


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Test with sample code outputs
    extractor = create_code_output_extractor()

    outputs = [
        "def hello(): return 'world'",
        """
def factorial(n):
    # Base case
    if n <= 1:
        return 1
    # Recursive case
    else:
        return n * factorial(n - 1)
""",
        """
# Complex multi-function implementation
def helper1(x):
    if x > 0:
        return x * 2
    return 0

def helper2(y):
    for i in range(y):
        if i % 2 == 0:
            yield i

def main(args):
    try:
        result = helper1(args[0])
        for val in helper2(result):
            print(val)
    except Exception as e:
        print(f"Error: {e}")
"""
    ]

    print("Feature names:", extractor.feature_names)
    print()

    for i, output in enumerate(outputs):
        fvec = extractor.extract(
            input=f"Write function {i}",
            output=output,
            context={}
        )
        print(f"Output {i}:")
        print(f"  Raw values: {fvec.raw_values}")
        print(f"  Normalized: {fvec.values}")
        print()
