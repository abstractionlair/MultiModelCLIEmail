"""
calibration_monitor.py

Calibration monitoring for evaluator ensembles.

Detects when evaluators are being gamed by the search process through:
1. Canary tests (known-bad contexts that should score poorly)
2. Holdout validation (contexts hidden from search)
3. Temporal drift detection (re-evaluation of old contexts)

This is the "meta-evaluator" that watches the evaluators.
"""

from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import statistics


@dataclass
class CanaryTest:
    """A test case that should fail - if it passes, evaluators are gamed.
    
    Canaries are adversarial examples designed to score poorly.
    If they start scoring well, the evaluators have been fooled.
    """
    id: str
    context: Any  # The context to evaluate
    expected_max_score: float  # Should score below this threshold
    description: str  # Human-readable description of why this is bad
    
    
@dataclass
class CalibrationWarning:
    """A warning about potential evaluator gaming."""
    warning_type: str  # "canary_failure", "holdout_gap", "temporal_drift"
    severity: float  # 0.0 = minor, 1.0 = critical
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CalibrationReport:
    """Results from a calibration check."""
    iteration: int
    warnings: List[CalibrationWarning]
    metrics: Dict[str, float]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def is_healthy(self) -> bool:
        """Check if calibration is healthy (no severe warnings)."""
        return not any(w.severity > 0.7 for w in self.warnings)


class CalibrationMonitor:
    """Monitors evaluator ensemble for signs of gaming/drift.
    
    The calibration monitor is a "meta-evaluator" that watches the
    evaluators themselves. It detects:
    
    1. Canary failures: Known-bad contexts scoring well
    2. Holdout gaps: Search-generated contexts overperforming holdout set
    3. Temporal drift: Old contexts scoring worse on re-evaluation
    
    Example:
        # Setup
        monitor = CalibrationMonitor(
            evaluator_ensemble=judge_pool,
            canaries=[...],
            holdout_set=[...]
        )
        
        # During QD search
        if iteration % 50 == 0:
            report = monitor.check_calibration(archive, iteration)
            if not report.is_healthy():
                print("WARNING: Evaluators may be gamed!")
                for warning in report.warnings:
                    print(f"  - {warning.message}")
    """
    
    def __init__(
        self,
        evaluator_ensemble: Any,  # EvaluatorEnsemble or JudgePool
        canaries: List[CanaryTest],
        holdout_set: Optional[List[Any]] = None,
        canary_threshold: float = 0.5,
        holdout_gap_threshold: float = 0.3,
        drift_threshold: float = 0.2
    ):
        """Initialize calibration monitor.
        
        Args:
            evaluator_ensemble: The ensemble to monitor
            canaries: List of known-bad test cases
            holdout_set: Contexts held out from search for validation
            canary_threshold: Max acceptable score for canaries
            holdout_gap_threshold: Max acceptable train/holdout gap
            drift_threshold: Max acceptable temporal drift
        """
        self.ensemble = evaluator_ensemble
        self.canaries = canaries
        self.holdout_set = holdout_set or []
        
        self.canary_threshold = canary_threshold
        self.holdout_gap_threshold = holdout_gap_threshold
        self.drift_threshold = drift_threshold
        
        # Track calibration history
        self.history: List[CalibrationReport] = []
        
        # Cache of original scores for drift detection
        self.original_scores: Dict[str, float] = {}
    
    def check_calibration(
        self,
        archive: Dict[Any, Dict[str, Any]],
        iteration: int
    ) -> CalibrationReport:
        """Run calibration checks and return report.
        
        Args:
            archive: QD search archive (niche -> {context, quality, ...})
            iteration: Current iteration number
            
        Returns:
            CalibrationReport with warnings and metrics
        """
        warnings = []
        metrics = {}
        
        # Check 1: Canary tests
        canary_warnings, canary_metrics = self._check_canaries()
        warnings.extend(canary_warnings)
        metrics.update(canary_metrics)
        
        # Check 2: Holdout comparison
        if self.holdout_set and len(archive) > 0:
            holdout_warnings, holdout_metrics = self._check_holdout_gap(archive)
            warnings.extend(holdout_warnings)
            metrics.update(holdout_metrics)
        
        # Check 3: Temporal drift
        if len(self.original_scores) > 0:
            drift_warnings, drift_metrics = self._check_temporal_drift(archive)
            warnings.extend(drift_warnings)
            metrics.update(drift_metrics)
        
        # Create report
        report = CalibrationReport(
            iteration=iteration,
            warnings=warnings,
            metrics=metrics
        )
        
        self.history.append(report)
        return report
    
    def _check_canaries(self) -> Tuple[List[CalibrationWarning], Dict[str, float]]:
        """Check if canary tests are passing (scoring low as expected).
        
        Returns:
            (warnings, metrics) tuple
        """
        warnings = []
        scores = []
        failures = []
        
        for canary in self.canaries:
            # Evaluate canary
            # NOTE: This assumes ensemble has evaluate() or evaluate_pair()
            # The actual interface depends on the evaluator implementation
            try:
                result = self._evaluate_context(canary.context)
                score = result.consensus if hasattr(result, 'consensus') else result
                scores.append(score)
                
                # Check if canary failed (scored too high)
                if score > canary.expected_max_score:
                    failures.append(canary)
                    warnings.append(CalibrationWarning(
                        warning_type="canary_failure",
                        severity=min(1.0, score / canary.expected_max_score),
                        message=f"Canary '{canary.id}' scored {score:.3f} (expected <{canary.expected_max_score:.3f})",
                        details={
                            "canary_id": canary.id,
                            "score": score,
                            "expected_max": canary.expected_max_score,
                            "description": canary.description
                        }
                    ))
            except Exception as e:
                print(f"Warning: Could not evaluate canary {canary.id}: {e}")
        
        # Metrics
        metrics = {
            "canary_pass_rate": 1.0 - (len(failures) / len(self.canaries)) if self.canaries else 1.0,
            "canary_avg_score": statistics.mean(scores) if scores else 0.0,
            "canary_failures": len(failures)
        }
        
        return warnings, metrics
    
    def _check_holdout_gap(
        self,
        archive: Dict[Any, Dict[str, Any]]
    ) -> Tuple[List[CalibrationWarning], Dict[str, float]]:
        """Check if archive contexts overperform holdout set.
        
        Large gap suggests evaluators are being gamed by search.
        
        Returns:
            (warnings, metrics) tuple
        """
        warnings = []
        
        # Sample from archive
        archive_contexts = [entry['context'] for entry in archive.values()]
        archive_sample = self._sample_random(archive_contexts, n=10)
        
        # Evaluate both sets
        archive_scores = [self._evaluate_context(ctx).consensus 
                         for ctx in archive_sample]
        holdout_scores = [self._evaluate_context(ctx).consensus 
                         for ctx in self._sample_random(self.holdout_set, n=10)]
        
        # Compare distributions
        archive_mean = statistics.mean(archive_scores) if archive_scores else 0.0
        holdout_mean = statistics.mean(holdout_scores) if holdout_scores else 0.0
        gap = archive_mean - holdout_mean
        
        # Check threshold
        if gap > self.holdout_gap_threshold:
            warnings.append(CalibrationWarning(
                warning_type="holdout_gap",
                severity=min(1.0, gap / self.holdout_gap_threshold),
                message=f"Archive overperforms holdout by {gap:.3f} (threshold: {self.holdout_gap_threshold:.3f})",
                details={
                    "archive_mean": archive_mean,
                    "holdout_mean": holdout_mean,
                    "gap": gap
                }
            ))
        
        metrics = {
            "archive_mean_quality": archive_mean,
            "holdout_mean_quality": holdout_mean,
            "train_holdout_gap": gap
        }
        
        return warnings, metrics
    
    def _check_temporal_drift(
        self,
        archive: Dict[Any, Dict[str, Any]]
    ) -> Tuple[List[CalibrationWarning], Dict[str, float]]:
        """Check if old contexts score worse on re-evaluation.
        
        Drift suggests evaluator responses have changed (due to gaming).
        
        Returns:
            (warnings, metrics) tuple
        """
        warnings = []
        
        # Re-evaluate contexts with cached original scores
        contexts_to_check = [
            (ctx_id, entry['context'], entry['quality'])
            for ctx_id, entry in archive.archive.items()
            if ctx_id in self.original_scores
        ]
        
        if not contexts_to_check:
            return [], {}
        
        # Sample and re-evaluate
        sample = self._sample_random(contexts_to_check, n=10)
        drifts = []
        
        for ctx_id, context, original_score in sample:
            new_result = self._evaluate_context(context)
            new_score = new_result.consensus
            drift = original_score - new_score  # Positive = degradation
            drifts.append(drift)
        
        # Aggregate drift
        avg_drift = statistics.mean(drifts) if drifts else 0.0
        
        if avg_drift > self.drift_threshold:
            warnings.append(CalibrationWarning(
                warning_type="temporal_drift",
                severity=min(1.0, avg_drift / self.drift_threshold),
                message=f"Old contexts degraded {avg_drift:.3f} on re-eval (threshold: {self.drift_threshold:.3f})",
                details={
                    "avg_drift": avg_drift,
                    "drifts": drifts
                }
            ))
        
        metrics = {
            "temporal_drift": avg_drift,
            "drift_samples": len(drifts)
        }
        
        return warnings, metrics
    
    def _evaluate_context(self, context: Any):
        """Evaluate a context using the ensemble.
        
        This is a wrapper that adapts to different ensemble interfaces.
        """
        # Try different evaluation interfaces
        if hasattr(self.ensemble, 'evaluate_pair'):
            # Pairwise evaluator - compare against a reference
            # For canaries, we compare against a minimal reference
            reference = self._get_reference_context()
            return self.ensemble.evaluate_pair(a=context, b=reference)
        elif hasattr(self.ensemble, 'evaluate'):
            return self.ensemble.evaluate(context)
        else:
            raise NotImplementedError(
                "Evaluator ensemble must implement evaluate() or evaluate_pair()"
            )
    
    def _get_reference_context(self):
        """Get a minimal reference context for pairwise comparison."""
        # This is domain-specific - for now, return a simple placeholder
        # In practice, this should be a known "minimal quality" context
        return "minimal reference"
    
    def _sample_random(self, items: List[Any], n: int) -> List[Any]:
        """Sample random items from list."""
        import random
        return random.sample(items, min(n, len(items)))
    
    def cache_original_score(self, context_id: str, score: float):
        """Cache original score for temporal drift detection.
        
        Args:
            context_id: Unique identifier for context
            score: Original quality score
        """
        self.original_scores[context_id] = score
    
    def get_calibration_summary(self) -> Dict[str, Any]:
        """Get summary of calibration history.
        
        Returns:
            Dictionary with calibration trends
        """
        if not self.history:
            return {"status": "no_data"}
        
        recent_reports = self.history[-5:]  # Last 5 checks
        
        # Count warnings by type
        warning_counts = {}
        for report in recent_reports:
            for warning in report.warnings:
                wtype = warning.warning_type
                warning_counts[wtype] = warning_counts.get(wtype, 0) + 1
        
        # Aggregate metrics
        all_metrics = {}
        for report in recent_reports:
            for key, value in report.metrics.items():
                if key not in all_metrics:
                    all_metrics[key] = []
                all_metrics[key].append(value)
        
        avg_metrics = {
            key: statistics.mean(values)
            for key, values in all_metrics.items()
        }
        
        return {
            "total_checks": len(self.history),
            "recent_warnings": warning_counts,
            "avg_metrics": avg_metrics,
            "latest_healthy": self.history[-1].is_healthy()
        }


def create_standard_canaries() -> List[CanaryTest]:
    """Create a standard set of canary tests for docstring generation.
    
    These are intentionally bad docstrings that should score poorly.
    """
    from code.demo_docstring_generation import DocstringContext
    
    canaries = [
        CanaryTest(
            id="empty",
            context=DocstringContext("", "formal", "brief"),
            expected_max_score=-0.5,
            description="Empty docstring should score poorly"
        ),
        CanaryTest(
            id="gibberish",
            context=DocstringContext("asdf qwer zxcv", "casual", "moderate"),
            expected_max_score=-0.3,
            description="Gibberish should score poorly"
        ),
        CanaryTest(
            id="wrong_language",
            context=DocstringContext("这是一个函数", "technical", "verbose"),
            expected_max_score=-0.2,
            description="Wrong language should score poorly"
        ),
    ]
    
    return canaries