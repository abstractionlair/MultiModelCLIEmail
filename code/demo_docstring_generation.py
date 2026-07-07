"""
demo_docstring_generation.py

End-to-end demo: Evolve diverse docstrings for Python functions.

This demo validates the integration of:
- Grok's evaluation framework (judge_pool, evaluators)
- Gemini's QD search (quality-diversity archive)
- Context mutation operators (style transforms)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from evaluator_base import EvaluationResult
from judge_pool import JudgePool
from simple_evaluator import LengthPreferenceEvaluator, KeywordPreferenceEvaluator
import random


# ============================================================================
# Demo Components
# ============================================================================

class DocstringContext:
    """Represents a context for generating docstrings."""
    
    def __init__(self, template: str, style: str, detail_level: str):
        """Initialize docstring context.
        
        Args:
            template: Base docstring template
            style: Style marker (formal/casual/technical)
            detail_level: Level of detail (brief/moderate/verbose)
        """
        self.template = template
        self.style = style
        self.detail_level = detail_level
    
    def generate(self, function_code: str) -> str:
        """Generate docstring from context.
        
        For this demo, we'll use simple template substitution.
        In a real system, this would call an LLM.
        """
        # Extract function name (simple heuristic)
        lines = function_code.strip().split('\n')
        first_line = lines[0] if lines else ""
        
        if 'def ' in first_line:
            func_name = first_line.split('def ')[1].split('(')[0]
        else:
            func_name = "function"
        
        # Apply style
        if self.style == "formal":
            intro = f"This method"
        elif self.style == "casual":
            intro = f"This function"
        else:  # technical
            intro = f"Implementation of"
        
        # Apply detail level
        if self.detail_level == "brief":
            doc = f'"""{intro} {func_name}."""'
        elif self.detail_level == "moderate":
            doc = f'"""{intro} {func_name}.\n\nProvides core functionality.\n"""'
        else:  # verbose
            doc = f'''"""{intro} {func_name}.
    
    Provides core functionality for the application.
    
    Returns:
        Result of the operation.
    
    Example:
        >>> {func_name}()
        result
    """'''
        
        return doc
    
    def __str__(self):
        return f"DocstringContext(style={self.style}, detail={self.detail_level})"


class DocstringMutator:
    """Mutates docstring contexts to create variations."""
    
    STYLES = ["formal", "casual", "technical"]
    DETAILS = ["brief", "moderate", "verbose"]
    TRIGGERS = ["comprehensive", "robust", "thoroughly", "state-of-the-art", "cutting-edge"]

    def mutate(self, context: DocstringContext) -> DocstringContext:
        """Create a mutated version of the context."""
        r = random.random()
        # With small probability, inject a trigger word into the template
        if r < 0.3:
            trigger = random.choice(self.TRIGGERS)
            new_template = (context.template + " " + trigger).strip()
            return DocstringContext(new_template, context.style, context.detail_level)
        # Otherwise, mutate style or detail level
        if r < 0.65:
            # Mutate style
            new_style = random.choice([s for s in self.STYLES if s != context.style])
            return DocstringContext(context.template, new_style, context.detail_level)
        else:
            # Mutate detail level
            new_detail = random.choice([d for d in self.DETAILS if d != context.detail_level])
            return DocstringContext(context.template, context.style, new_detail)


class DocstringEvaluatorAdapter:
    """Adapts JudgePool to work as QD evaluator."""
    
    def __init__(self, judge_pool: JudgePool, test_function: str):
        """Initialize adapter.
        
        Args:
            judge_pool: Ensemble of evaluators
            test_function: Function code to document
        """
        self.judge_pool = judge_pool
        self.test_function = test_function
        self.reference_doc = '"""Basic docstring."""'  # Reference for comparison
    
    def evaluate(self, context: DocstringContext) -> EvaluationResult:
        """Evaluate a docstring context.
        
        Compares generated docstring against reference.
        
        Returns:
            EvaluationResult with consensus and diversity
        """
        generated_doc = context.generate(self.test_function)
        
        # Evaluate against reference
        result = self.judge_pool.evaluate_pair(
            a=generated_doc,
            b=self.reference_doc
        )
        
        return result


class SimpleFeatureExtractor:
    """Extracts features from docstring contexts."""
    
    def extract(self, context: DocstringContext) -> 'list[float]':
        """Extract feature vector from context.
        
        Features:
        - Style encoded as number (0=formal, 1=casual, 2=technical)
        - Detail level encoded as number (0=brief, 1=moderate, 2=verbose)
        
        Returns:
            Feature vector [style_idx, detail_idx]
        """
        style_map = {"formal": 0.0, "casual": 1.0, "technical": 2.0}
        detail_map = {"brief": 0.0, "moderate": 1.0, "verbose": 2.0}
        
        return [
            style_map[context.style],
            detail_map[context.detail_level]
        ]


# ============================================================================
# Simplified QD Archive (for demo)
# ============================================================================

class SimpleQDArchive:
    """Simplified quality-diversity archive for demo."""
    
    def __init__(self, niche_size: float = 0.5):
        """Initialize archive.
        
        Args:
            niche_size: Granularity of niches
        """
        self.archive = {}
        self.niche_size = niche_size
    
    def add(self, context: DocstringContext, quality: float, 
            features: 'list[float]', diversity: float):
        """Add context to archive if it's the best in its niche.
        
        Args:
            context: DocstringContext to add
            quality: Quality score (consensus)
            features: Feature vector
            diversity: Evaluator diversity metric
        """
        # Include diversity in features for niche calculation
        full_features = features + [diversity]
        niche_key = self._get_niche_key(full_features)
        
        if niche_key not in self.archive or quality > self.archive[niche_key]['quality']:
            self.archive[niche_key] = {
                'context': context,
                'quality': quality,
                'features': features,
                'diversity': diversity
            }
    
    def _get_niche_key(self, features: 'list[float]') -> tuple:
        """Compute niche key by quantizing features."""
        return tuple(int(f / self.niche_size) for f in features)
    
    def sample_parent(self) -> DocstringContext:
        """Sample a parent context from archive."""
        if not self.archive:
            # Return default if archive empty
            return DocstringContext("default", "formal", "moderate")
        return random.choice(list(self.archive.values()))['context']
    
    def get_stats(self) -> dict:
        """Get archive statistics."""
        if not self.archive:
            return {'size': 0, 'avg_quality': 0.0, 'avg_diversity': 0.0}
        
        qualities = [item['quality'] for item in self.archive.values()]
        diversities = [item['diversity'] for item in self.archive.values()]
        
        return {
            'size': len(self.archive),
            'avg_quality': sum(qualities) / len(qualities),
            'avg_diversity': sum(diversities) / len(diversities),
            'max_quality': max(qualities),
            'min_quality': min(qualities),
        }


# ============================================================================
# Main Demo
# ============================================================================

def run_demo(num_iterations: int = 50):
    """Run end-to-end QD search demo."""
    
    print("=" * 70)
    print("Docstring Generation QD Search Demo")
    print("=" * 70)
    print()
    
    # Test function to document
    test_function = """def calculate_fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b"""
    
    print("Function to document:")
    print(test_function)
    print()
    
    # Set up evaluators
    print("Setting up evaluation ensemble...")
    evaluators = [
        LengthPreferenceEvaluator("length-eval"),
        KeywordPreferenceEvaluator("keyword-eval-1", 
                                  keywords=["method", "function", "returns", "example"]),
        KeywordPreferenceEvaluator("keyword-eval-2",
                                  keywords=["provides", "functionality", "implementation"]),
    ]
    judge_pool = JudgePool(evaluators, default_n_judges=3)
    print(f"  - {len(evaluators)} evaluators in pool")
    print()
    
    # Set up QD components
    print("Initializing QD search components...")
    mutator = DocstringMutator()
    evaluator = DocstringEvaluatorAdapter(judge_pool, test_function)
    feature_extractor = SimpleFeatureExtractor()
    archive = SimpleQDArchive(niche_size=0.5)
    print()
    
    # Seed initial population
    print("Seeding initial population...")
    seed_contexts = [
        DocstringContext("default", "formal", "brief"),
        DocstringContext("default", "casual", "moderate"),
        DocstringContext("default", "technical", "verbose"),
    ]
    
    for ctx in seed_contexts:
        result = evaluator.evaluate(ctx)
        features = feature_extractor.extract(ctx)
        archive.add(ctx, result.consensus, features, result.diversity)
        print(f"  - Seeded: {ctx}")
    
    print(f"  - Initial archive size: {archive.get_stats()['size']}")
    print()
    
    # Run QD search
    print(f"Running {num_iterations} iterations of QD search...")
    print("-" * 70)
    
    for iteration in range(num_iterations):
        # Select parent
        parent = archive.sample_parent()
        
        # Mutate
        child = mutator.mutate(parent)
        
        # Evaluate
        result = evaluator.evaluate(child)
        features = feature_extractor.extract(child)
        
        # Add to archive
        archive.add(child, result.consensus, features, result.diversity)
        
        # Log progress
        if (iteration + 1) % 10 == 0:
            stats = archive.get_stats()
            print(f"Iteration {iteration + 1:3d}: "
                  f"Archive size = {stats['size']:2d}, "
                  f"Avg quality = {stats['avg_quality']:+.3f}, "
                  f"Avg diversity = {stats['avg_diversity']:.3f}")
    
    print("-" * 70)
    print()
    
    # Final results
    print("Final Results:")
    print("=" * 70)
    stats = archive.get_stats()
    for key, value in stats.items():
        print(f"  {key:15s}: {value}")
    print()
    
    # Show sample entries from archive
    print("Sample Archive Entries:")
    print("-" * 70)
    for i, (niche, entry) in enumerate(list(archive.archive.items())[:5]):
        print(f"\nNiche {niche}:")
        print(f"  Context: {entry['context']}")
        print(f"  Quality: {entry['quality']:+.3f}")
        print(f"  Diversity: {entry['diversity']:.3f}")
        print(f"  Generated:")
        doc = entry['context'].generate(test_function)
        print(f"    {doc[:100]}...")
    
    print()
    print("=" * 70)
    print("Demo complete!")
    print("=" * 70)
    
    return archive


if __name__ == '__main__':
    import sys
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    random.seed(42)  # Reproducibility
    archive = run_demo(n_iter)
