"""
Gaming Dynamics Analyzer

Tools for understanding ensemble evaluator resistance to Goodhart's law.
Implements the theoretical framework from docs/gaming_dynamics_analysis.md
"""

from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np
from collections import defaultdict
import json

from evaluator_base import Judgment, EvaluationResult


@dataclass
class GamingMetrics:
    """Metrics capturing gaming dynamics over time."""

    # Core measurements
    judge_correlations: np.ndarray  # n_judges × n_judges correlation matrix
    gaming_success_rate: float      # [0, 1] how much gaming occurred
    ensemble_robustness: float      # [0, 1] resilience to individual judge failure

    # Detailed statistics
    bias_score_mean: float          # Average bias feature in archive
    bias_score_change: float        # Δ from initial to final
    bias_saturation: float          # % of archive at max bias

    # Temporal dynamics
    gaming_intensity: float         # Rate of gaming (Gemini's metric)
    convergence_iteration: Optional[int]  # When gaming plateaued

    # Per-judge statistics
    judge_agreement_rates: dict[str, float]  # How often each judge agrees with consensus
    judge_bias_affinity: dict[str, float]    # Correlation with bias feature


class GamingAnalyzer:
    """Analyze evaluator gaming dynamics from experimental results."""

    def __init__(self, bias_detector: Callable[[str], float]):
        """
        Args:
            bias_detector: Function mapping output -> bias_score
                          (e.g., count of trigger words)
        """
        self.bias_detector = bias_detector

    def analyze_experiment(
        self,
        history: list[dict],  # QD search history
        canary_labels: Optional[dict[str, str]] = None
    ) -> GamingMetrics:
        """
        Comprehensive analysis of a QD search experiment.

        Args:
            history: List of iteration snapshots with:
                - archive: Current population
                - evaluations: EvaluationResults for each candidate
                - iteration: Iteration number
            canary_labels: Optional ground truth for robustness calculation

        Returns:
            GamingMetrics with all computed statistics
        """
        # Extract evaluation results over time
        all_evaluations = []
        bias_scores_over_time = []

        for snapshot in history:
            evaluations = snapshot.get('evaluations', [])
            all_evaluations.extend(evaluations)

            # Compute bias scores for this iteration's archive
            archive = snapshot.get('archive', [])
            bias_scores = [self.bias_detector(item['output']) for item in archive]
            bias_scores_over_time.append(bias_scores)

        # Compute judge correlation matrix
        judge_correlations = self._compute_judge_correlations(all_evaluations)

        # Measure gaming success
        gaming_stats = self._measure_gaming_success(bias_scores_over_time)

        # Compute ensemble robustness
        robustness = self._compute_robustness(all_evaluations, canary_labels)

        # Calculate per-judge statistics
        judge_stats = self._compute_judge_statistics(all_evaluations, history)

        # Measure gaming intensity (rate of change)
        gaming_intensity = self._compute_gaming_intensity(bias_scores_over_time)

        # Find convergence point
        convergence = self._find_convergence(bias_scores_over_time)

        return GamingMetrics(
            judge_correlations=judge_correlations,
            gaming_success_rate=gaming_stats['success_rate'],
            ensemble_robustness=robustness,
            bias_score_mean=gaming_stats['final_mean'],
            bias_score_change=gaming_stats['change'],
            bias_saturation=gaming_stats['saturation'],
            gaming_intensity=gaming_intensity,
            convergence_iteration=convergence,
            judge_agreement_rates=judge_stats['agreement_rates'],
            judge_bias_affinity=judge_stats['bias_affinity']
        )

    def _compute_judge_correlations(
        self,
        evaluations: list[EvaluationResult]
    ) -> np.ndarray:
        """
        Compute pairwise correlation matrix for judge preferences.

        For each pair of judges, measure how often they agree on A vs B.
        Positive correlation = judges agree
        Negative correlation = judges anti-correlate (adversarial)
        """
        # Extract judge names
        if not evaluations:
            return np.array([[]])

        judge_names = list({j.judge_id for e in evaluations for j in e.judgments})
        n_judges = len(judge_names)
        judge_to_idx = {name: i for i, name in enumerate(judge_names)}

        # Build preference matrix: judges × evaluations
        # Value: +1 for A, -1 for B, 0 for neither
        preference_matrix = np.zeros((n_judges, len(evaluations)))

        for eval_idx, evaluation in enumerate(evaluations):
            for judgment in evaluation.judgments:
                judge_idx = judge_to_idx[judgment.judge_id]
                if judgment.preferred == 'A':
                    preference_matrix[judge_idx, eval_idx] = 1
                elif judgment.preferred == 'B':
                    preference_matrix[judge_idx, eval_idx] = -1
                # neither = 0 (already initialized)

        # Compute correlation matrix
        # Handle case where all values are the same (zero variance)
        correlations = np.corrcoef(preference_matrix)
        correlations = np.nan_to_num(correlations, nan=0.0)

        return correlations

    def _measure_gaming_success(
        self,
        bias_scores_over_time: list[list[float]]
    ) -> dict:
        """
        Quantify how successfully the system was gamed.

        Returns dict with:
            - success_rate: [0, 1] normalized gaming achievement
            - final_mean: Mean bias score in final population
            - change: Δ from initial to final
            - saturation: Fraction of population at maximum bias
        """
        if not bias_scores_over_time:
            return {
                'success_rate': 0.0,
                'final_mean': 0.0,
                'change': 0.0,
                'saturation': 0.0
            }

        initial_scores = bias_scores_over_time[0]
        final_scores = bias_scores_over_time[-1]

        initial_mean = np.mean(initial_scores) if initial_scores else 0.0
        final_mean = np.mean(final_scores) if final_scores else 0.0

        change = final_mean - initial_mean

        # Compute maximum observed bias across all iterations
        all_scores = [s for iteration in bias_scores_over_time for s in iteration]
        max_bias = max(all_scores) if all_scores else 1.0

        # Saturation: what fraction of final population is at >90% of max bias?
        saturation = 0.0
        if final_scores and max_bias > 0:
            threshold = 0.9 * max_bias
            saturation = sum(1 for s in final_scores if s >= threshold) / len(final_scores)

        # Success rate: normalized change (0 = no change, 1 = full saturation)
        success_rate = min(1.0, change / max_bias) if max_bias > 0 else 0.0

        return {
            'success_rate': success_rate,
            'final_mean': final_mean,
            'change': change,
            'saturation': saturation
        }

    def _compute_robustness(
        self,
        evaluations: list[EvaluationResult],
        canary_labels: Optional[dict[str, str]]
    ) -> float:
        """
        Ensemble robustness via leave-one-out analysis.

        For each judge, compute what consensus would be without that judge.
        Measure accuracy on canaries (if provided).
        Return minimum accuracy across all leave-one-out tests.

        If no canaries, use internal consistency as proxy.
        """
        if not evaluations or not canary_labels:
            # Fallback: measure consensus stability under leave-one-out
            return self._consensus_stability(evaluations)

        # TODO: Implement full canary-based robustness when canary tracking is available
        return self._consensus_stability(evaluations)

    def _consensus_stability(self, evaluations: list[EvaluationResult]) -> float:
        """
        Measure how stable consensus is when removing individual judges.

        Returns: Fraction of evaluations where consensus doesn't change
                 under any single judge removal.
        """
        if not evaluations:
            return 0.0

        stable_count = 0

        for evaluation in evaluations:
            judgments = evaluation.judgments
            if len(judgments) <= 1:
                continue

            # Original consensus (majority vote)
            original_consensus = self._majority_vote(judgments)

            # Test each leave-one-out
            all_stable = True
            for i in range(len(judgments)):
                remaining = judgments[:i] + judgments[i+1:]
                loo_consensus = self._majority_vote(remaining)
                if loo_consensus != original_consensus:
                    all_stable = False
                    break

            if all_stable:
                stable_count += 1

        return stable_count / len(evaluations)

    def _majority_vote(self, judgments: list[Judgment]) -> str:
        """Simple majority vote over judgments."""
        if not judgments:
            return 'neither'

        votes = defaultdict(int)
        for j in judgments:
            votes[j.preferred] += 1

        return max(votes.items(), key=lambda x: x[1])[0]

    def _compute_judge_statistics(
        self,
        evaluations: list[EvaluationResult],
        history: list[dict]
    ) -> dict:
        """
        Per-judge agreement rates and bias affinity.

        Returns:
            - agreement_rates: How often each judge agrees with majority
            - bias_affinity: Correlation between judge preference and bias score
        """
        if not evaluations:
            return {'agreement_rates': {}, 'bias_affinity': {}}

        # Get judge names
        judge_names = list({j.judge_id for e in evaluations for j in e.judgments})

        # Agreement rates
        agreement_counts = {name: 0 for name in judge_names}
        total_counts = {name: 0 for name in judge_names}

        for evaluation in evaluations:
            consensus = self._majority_vote(evaluation.judgments)
            for judgment in evaluation.judgments:
                total_counts[judgment.judge_id] += 1
                if judgment.preferred == consensus:
                    agreement_counts[judgment.judge_id] += 1

        agreement_rates = {
            name: agreement_counts[name] / total_counts[name] if total_counts[name] > 0 else 0.0
            for name in judge_names
        }

        # Bias affinity (requires mapping evaluations to outputs)
        # For now, return placeholder - full implementation needs output tracking
        bias_affinity = {name: 0.0 for name in judge_names}

        return {
            'agreement_rates': agreement_rates,
            'bias_affinity': bias_affinity
        }

    def _compute_gaming_intensity(
        self,
        bias_scores_over_time: list[list[float]]
    ) -> float:
        """
        Rate of gaming: how fast is bias increasing?

        Gemini's metric: rate of increase of bias, normalized by
        overall rate of change in archive.

        Returns: Slope of bias score over iterations (robust to noise)
        """
        if len(bias_scores_over_time) < 2:
            return 0.0

        # Compute mean bias per iteration
        mean_bias_per_iteration = [
            np.mean(scores) if scores else 0.0
            for scores in bias_scores_over_time
        ]

        # Linear regression to get slope (robust to noise)
        x = np.arange(len(mean_bias_per_iteration))
        y = np.array(mean_bias_per_iteration)

        if len(x) < 2:
            return 0.0

        # Fit y = mx + b
        slope, _ = np.polyfit(x, y, 1)

        return float(slope)

    def _find_convergence(
        self,
        bias_scores_over_time: list[list[float]],
        window: int = 5,
        threshold: float = 0.01
    ) -> Optional[int]:
        """
        Find iteration where gaming converged (plateaued).

        Returns: First iteration where bias score stabilizes
                 (no significant change for `window` iterations)
        """
        if len(bias_scores_over_time) < window + 1:
            return None

        means = [np.mean(scores) if scores else 0.0 for scores in bias_scores_over_time]

        for i in range(len(means) - window):
            window_values = means[i:i+window]
            if max(window_values) - min(window_values) < threshold:
                return i

        return None

    def export_report(self, metrics: GamingMetrics, output_path: str):
        """Export analysis results as JSON."""
        report = {
            'gaming_success_rate': float(metrics.gaming_success_rate),
            'ensemble_robustness': float(metrics.ensemble_robustness),
            'bias_score_mean': float(metrics.bias_score_mean),
            'bias_score_change': float(metrics.bias_score_change),
            'bias_saturation': float(metrics.bias_saturation),
            'gaming_intensity': float(metrics.gaming_intensity),
            'convergence_iteration': metrics.convergence_iteration,
            'judge_agreement_rates': metrics.judge_agreement_rates,
            'judge_bias_affinity': metrics.judge_bias_affinity,
            'judge_correlations': metrics.judge_correlations.tolist()
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        return report


def trigger_word_detector(output: str) -> float:
    """
    Bias detector for TriggerWordEvaluator.

    Counts trigger words: comprehensive, robust, thoroughly, etc.
    """
    trigger_words = [
        'comprehensive', 'comprehensively',
        'robust', 'robustly',
        'thorough', 'thoroughly',
        'extensive', 'extensively',
        'rigorous', 'rigorously',
        'meticulous', 'meticulously'
    ]

    output_lower = output.lower()
    count = sum(1 for word in trigger_words if word in output_lower)
    return float(count)


# Example usage
if __name__ == '__main__':
    # Example: Analyze results from demo_gameable_experiment.py
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gaming_analyzer.py <experiment_results.json>")
        sys.exit(1)

    results_path = sys.argv[1]

    with open(results_path) as f:
        results = json.load(f)

    analyzer = GamingAnalyzer(bias_detector=trigger_word_detector)

    # Convert results to expected format
    # (Assumes results contain 'history' field with iteration snapshots)
    history = results.get('history', [])

    metrics = analyzer.analyze_experiment(history)

    # Export report
    output_path = results_path.replace('.json', '_analysis.json')
    analyzer.export_report(metrics, output_path)

    print(f"Gaming Analysis Report")
    print(f"=" * 60)
    print(f"Gaming Success Rate: {metrics.gaming_success_rate:.2%}")
    print(f"Ensemble Robustness: {metrics.ensemble_robustness:.2%}")
    print(f"Bias Score Change: {metrics.bias_score_change:+.2f}")
    print(f"Gaming Intensity: {metrics.gaming_intensity:+.3f}/iteration")
    print(f"Convergence: iteration {metrics.convergence_iteration}")
    print(f"\nJudge Agreement Rates:")
    for judge, rate in metrics.judge_agreement_rates.items():
        print(f"  {judge}: {rate:.2%}")
    print(f"\nReport exported to: {output_path}")
