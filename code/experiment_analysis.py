"""
Post-experiment analysis tools for evaluator robustness experiments.

Analyzes results from QD search experiments to detect:
- Evaluator gaming
- Score divergence
- Calibration drift
- Exploit patterns
"""

import json
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import statistics


@dataclass
class ArchiveEntry:
    """An entry in the QD search archive."""
    docstring: str
    scores: Dict[str, float]  # evaluator_name -> score
    iteration: int
    features: List[float]


class ExperimentAnalyzer:
    """Analyzes results from evaluator robustness experiments."""

    def __init__(self, archive: List[ArchiveEntry], metadata: Dict[str, Any]):
        self.archive = archive
        self.metadata = metadata

    def compute_score_divergence(self) -> Dict[str, Any]:
        """
        Measures divergence between gameable and ground-truth evaluators.

        If search is gaming evaluators, we expect:
        - High scores from gameable evaluator
        - Low scores from ground-truth evaluators
        - Negative correlation between the two
        """

        if not self.archive:
            return {"error": "Empty archive"}

        # Identify evaluator types
        evaluator_names = list(self.archive[0].scores.keys())

        if len(evaluator_names) < 2:
            return {"error": "Need at least 2 evaluators"}

        results = {}

        # For each pair of evaluators, compute correlation
        for i, eval_a in enumerate(evaluator_names):
            for eval_b in evaluator_names[i+1:]:
                scores_a = [entry.scores[eval_a] for entry in self.archive]
                scores_b = [entry.scores[eval_b] for entry in self.archive]

                correlation = self._pearson_correlation(scores_a, scores_b)

                pair_name = f"{eval_a}_vs_{eval_b}"
                results[pair_name] = {
                    'correlation': correlation,
                    'mean_diff': statistics.mean([a - b for a, b in zip(scores_a, scores_b)]),
                    'interpretation': self._interpret_correlation(correlation)
                }

        return results

    def detect_keyword_stuffing(self) -> Dict[str, Any]:
        """
        Detects if archive contains keyword-stuffed docstrings.

        Looks for:
        - High frequency of trigger words
        - Unusual repetition patterns
        - Low information density
        """

        trigger_words = ["comprehensive", "robust", "thoroughly",
                        "extensively", "rigorously", "meticulously"]

        stuffing_scores = []
        examples = []

        for entry in self.archive:
            text = entry.docstring.lower()
            trigger_count = sum(1 for word in trigger_words if word in text)

            # Calculate trigger word density (triggers per 100 words)
            word_count = len(text.split())
            if word_count == 0:
                density = 0
            else:
                density = (trigger_count / word_count) * 100

            stuffing_score = {
                'docstring_preview': entry.docstring[:100],
                'trigger_count': trigger_count,
                'word_count': word_count,
                'density': density,
                'scores': entry.scores
            }

            stuffing_scores.append(stuffing_score)

            # Flag high-density examples
            if density > 5.0:  # More than 5% trigger words
                examples.append(stuffing_score)

        return {
            'mean_density': statistics.mean([s['density'] for s in stuffing_scores]),
            'max_density': max([s['density'] for s in stuffing_scores]),
            'flagged_count': len(examples),
            'flagged_examples': examples[:5],  # Top 5
            'is_gaming_detected': len(examples) > len(self.archive) * 0.2  # More than 20%
        }

    def analyze_temporal_drift(self) -> Dict[str, Any]:
        """
        Analyzes how scores change over iterations.

        If evaluators are being gamed, we expect:
        - Increasing scores from gameable evaluator
        - Stable or decreasing scores from ground-truth evaluators
        """

        if not self.archive:
            return {"error": "Empty archive"}

        # Group by iteration
        by_iteration = {}
        for entry in self.archive:
            iter_num = entry.iteration
            if iter_num not in by_iteration:
                by_iteration[iter_num] = []
            by_iteration[iter_num].append(entry)

        # Calculate average scores per iteration per evaluator
        evaluator_names = list(self.archive[0].scores.keys())

        temporal_data = {eval_name: [] for eval_name in evaluator_names}

        for iter_num in sorted(by_iteration.keys()):
            entries = by_iteration[iter_num]
            for eval_name in evaluator_names:
                avg_score = statistics.mean([e.scores[eval_name] for e in entries])
                temporal_data[eval_name].append({
                    'iteration': iter_num,
                    'avg_score': avg_score
                })

        # Compute trends (increasing/decreasing/stable)
        trends = {}
        for eval_name, data_points in temporal_data.items():
            scores = [d['avg_score'] for d in data_points]
            if len(scores) < 2:
                trends[eval_name] = "insufficient_data"
            else:
                first_half = statistics.mean(scores[:len(scores)//2])
                second_half = statistics.mean(scores[len(scores)//2:])
                diff = second_half - first_half

                if abs(diff) < 0.05:
                    trends[eval_name] = "stable"
                elif diff > 0:
                    trends[eval_name] = "increasing"
                else:
                    trends[eval_name] = "decreasing"

        return {
            'temporal_data': temporal_data,
            'trends': trends,
            'calibration_drift_detected': self._detect_divergent_trends(trends)
        }

    def generate_report(self) -> str:
        """Generates a human-readable analysis report."""

        lines = []
        lines.append("=" * 80)
        lines.append("EVALUATOR ROBUSTNESS EXPERIMENT ANALYSIS")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Archive size: {len(self.archive)} entries")
        lines.append(f"Iterations: {self.metadata.get('iterations', 'unknown')}")
        lines.append("")

        # Score divergence
        lines.append("## Score Divergence Analysis")
        lines.append("-" * 40)
        divergence = self.compute_score_divergence()
        for pair, data in divergence.items():
            if 'correlation' in data:
                lines.append(f"{pair}:")
                lines.append(f"  Correlation: {data['correlation']:.3f}")
                lines.append(f"  Interpretation: {data['interpretation']}")
                lines.append(f"  Mean difference: {data['mean_diff']:.3f}")
        lines.append("")

        # Keyword stuffing
        lines.append("## Keyword Stuffing Detection")
        lines.append("-" * 40)
        stuffing = self.detect_keyword_stuffing()
        lines.append(f"Mean trigger word density: {stuffing['mean_density']:.2f}%")
        lines.append(f"Max density: {stuffing['max_density']:.2f}%")
        lines.append(f"Flagged examples: {stuffing['flagged_count']}")
        lines.append(f"Gaming detected: {stuffing['is_gaming_detected']}")
        if stuffing['flagged_examples']:
            lines.append("\nTop flagged examples:")
            for ex in stuffing['flagged_examples']:
                lines.append(f"  - {ex['docstring_preview']}...")
                lines.append(f"    Density: {ex['density']:.1f}%, Scores: {ex['scores']}")
        lines.append("")

        # Temporal drift
        lines.append("## Temporal Drift Analysis")
        lines.append("-" * 40)
        drift = self.analyze_temporal_drift()
        if 'trends' in drift:
            for eval_name, trend in drift['trends'].items():
                lines.append(f"{eval_name}: {trend}")
            lines.append(f"\nCalibration drift detected: {drift['calibration_drift_detected']}")
        lines.append("")

        # Summary
        lines.append("## SUMMARY")
        lines.append("-" * 40)
        issues = []

        if stuffing['is_gaming_detected']:
            issues.append("⚠️  Keyword stuffing detected")

        if drift.get('calibration_drift_detected'):
            issues.append("⚠️  Evaluator scores diverging over time")

        # Check for negative correlations
        for pair, data in divergence.items():
            if isinstance(data, dict) and 'correlation' in data:
                if data['correlation'] < -0.3:
                    issues.append(f"⚠️  Negative correlation between evaluators: {pair}")

        if issues:
            lines.append("ISSUES FOUND:")
            for issue in issues:
                lines.append(f"  {issue}")
        else:
            lines.append("✓ No significant issues detected")

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """Computes Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) == 0:
            return 0.0

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = sum((xi - mean_x) ** 2 for xi in x)
        denom_y = sum((yi - mean_y) ** 2 for yi in y)

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y) ** 0.5

    def _interpret_correlation(self, corr: float) -> str:
        """Interprets correlation value."""
        if corr > 0.7:
            return "Strong positive (evaluators agree)"
        elif corr > 0.3:
            return "Moderate positive"
        elif corr > -0.3:
            return "Weak or no correlation"
        elif corr > -0.7:
            return "Moderate negative (evaluators disagree)"
        else:
            return "Strong negative (evaluators strongly disagree)"

    def _detect_divergent_trends(self, trends: Dict[str, str]) -> bool:
        """Detects if evaluator trends are diverging (sign of gaming)."""
        trend_values = list(trends.values())

        # If some evaluators are increasing while others are decreasing, flag it
        has_increasing = "increasing" in trend_values
        has_decreasing = "decreasing" in trend_values

        return has_increasing and has_decreasing


def load_experiment_results(results_file: str) -> Tuple[List[ArchiveEntry], Dict[str, Any]]:
    """Loads experiment results from JSON file."""

    with open(results_file, 'r') as f:
        data = json.load(f)

    archive = [
        ArchiveEntry(
            docstring=entry['docstring'],
            scores=entry['scores'],
            iteration=entry['iteration'],
            features=entry.get('features', [])
        )
        for entry in data['archive']
    ]

    metadata = data.get('metadata', {})

    return archive, metadata


if __name__ == "__main__":
    # Example usage
    print("Experiment Analysis Framework")
    print("Usage: Load experiment results and call analyzer.generate_report()")
