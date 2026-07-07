"""
demo_with_real_evaluator.py

Experimental QD search with real model evaluator (Gemini) + mock evaluators.

This demo validates:
1. BudgetController prevents cost blowup
2. CalibrationMonitor detects evaluator gaming
3. Mixed ensemble (real + mock) exposes different biases
4. Search behavior with heterogeneous evaluators

Expected outcomes:
- Hypothesis A: No exploits found (evaluators robust)
- Hypothesis B: Exploits found (valuable learning data)
"""

import sys
import os
import json
import random
from pathlib import Path

# Ensure local code/ modules are importable when running this script directly
sys.path.insert(0, os.path.dirname(__file__))


from evaluator_base import EvaluationResult, Evaluator, Judgment, Preference
from judge_pool import JudgePool
from simple_evaluator import LengthPreferenceEvaluator, KeywordPreferenceEvaluator
from budget_controller import BudgetController, estimate_cost
from calibration_monitor import CalibrationMonitor, CanaryTest
from demo_docstring_generation import (
    DocstringContext, DocstringMutator, 
    DocstringEvaluatorAdapter, SimpleFeatureExtractor,
    SimpleQDArchive
)


# ============================================================================
# Gemini Evaluator with Budget Control
# ============================================================================




# ============================================================================
# Canary Tests for Docstrings
# ============================================================================

def create_docstring_canaries(test_function: str) -> list:
    """Create adversarial docstrings (as strings) that should score poorly."""
    
    # Generate canary docstrings from bad contexts
    ctx_empty = DocstringContext("", "formal", "brief")
    ctx_gibberish = DocstringContext("asdfqwer", "casual", "moderate")
    ctx_misleading = DocstringContext(
        "This function does the opposite of what it actually does",
        "technical", "verbose"
    )
    
    canaries = [
        CanaryTest(
            id="empty",
            context=ctx_empty.generate(test_function),
            expected_max_score=-0.3,
            description="Empty template should generate poor docstring"
        ),
        CanaryTest(
            id="gibberish_style",
            context=ctx_gibberish.generate(test_function),
            expected_max_score=-0.2,
            description="Gibberish template should be rejected"
        ),
        CanaryTest(
            id="misleading",
            context=ctx_misleading.generate(test_function),
            expected_max_score=-0.1,
            description="Misleading docstring should score low"
        ),
    ]
    
    return canaries


# ============================================================================
# Main Experiment
# ============================================================================

def run_experiment(
    num_iterations: int = 30,
    max_api_calls: int = 50,
    max_cost_usd: float = 2.0,
    calibration_interval: int = 10
):
    """Run QD search experiment with real + mock evaluators."""
    
    print("=" * 70)
    print("Experimental QD Search: Real Evaluator + Mocks")
    print("=" * 70)
    print()
    
    # Test function
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
    
    # Set up budget controller
    print("Setting up budget controller...")
    budget = BudgetController(
        max_calls=max_api_calls,
        max_cost_usd=max_cost_usd,
        enable_cache=True
    )
    print(f"  - Max API calls: {max_api_calls}")
    print(f"  - Max cost: ${max_cost_usd:.2f}")
    print()
    
    # Set up evaluators (toggle via DEMO_EVALUATORS=mock|real+mock|gameable)
    print("Setting up evaluation ensemble...")
    evaluators = []
    mode = os.getenv("DEMO_EVALUATORS", "mock").lower()
    try:
        # Prefer budget-wrapped Gemini if available
        from code.gemini_evaluator import GeminiEvaluator as _G
        if mode in ("real", "real+mock"):
            evaluators.append(_G("gemini-judge", model=os.getenv("GEMINI_MODEL", "gemini-pro"), budget_controller=budget))
    except Exception:
        pass

    # Always include mocks for baseline comparison
    evaluators.append(LengthPreferenceEvaluator("length-judge"))
    evaluators.append(
        KeywordPreferenceEvaluator(
            "keyword-judge",
            keywords=["function", "returns", "example", "provides"]
        )
    )

    if mode == "gameable":
        try:
            from simple_evaluator import TriggerWordEvaluator, AntiTriggerEvaluator
            evaluators.append(TriggerWordEvaluator("trigger-judge", weight=20.0))
            evaluators.append(AntiTriggerEvaluator("anti-trigger-judge", weight=10.0))
            print("    • Added Trigger/Anti-Trigger evaluators for selection pressure")
        except Exception as e:
            print(f"Warning: could not add gameable evaluators: {e}")

    # No explicit state to reset in this demo

    judge_pool = JudgePool(evaluators, default_n_judges=3)
    print(f"  - {len(evaluators)} evaluators in pool")
    print("    • 1x Gemini (real API or mock)")
    print("    • 1x LengthPreference (mock)")
    print("    • 1x KeywordPreference (mock)")
    print()
    
    # Set up calibration monitor
    print("Setting up calibration monitor...")
    canaries = create_docstring_canaries(test_function)
    monitor = CalibrationMonitor(
        evaluator_ensemble=judge_pool,
        canaries=canaries,
        holdout_set=[],  # Could add holdout contexts here
        canary_threshold=0.0  # Canaries should score negative
    )
    print(f"  - {len(canaries)} canary tests")
    print()
    
    # Run baseline calibration
    print("Running baseline calibration check...")
    baseline_report = monitor.check_calibration({}, iteration=0)
    print(f"  - Baseline healthy: {baseline_report.is_healthy()}")
    if baseline_report.warnings:
        print("  - Baseline warnings:")
        for w in baseline_report.warnings:
            print(f"    • {w.message}")
    print()
    
    # Set up QD components
    print("Initializing QD search...")
    mutator = DocstringMutator()
    evaluator = DocstringEvaluatorAdapter(judge_pool, test_function)
    feature_extractor = SimpleFeatureExtractor()
    archive = SimpleQDArchive(niche_size=0.5)
    print()
    
    # Seed population
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
        # Cache original scores for drift detection
        ctx_id = str((features, result.diversity))
        monitor.cache_original_score(ctx_id, result.consensus)
    
    print(f"  - Seeded {len(seed_contexts)} contexts")
    print()
    
    # Run QD search
    print(f"Running {num_iterations} iterations...")
    print("-" * 70)
    
    export_records = []  # for analysis export

    def _score_gameable(doc: str) -> float:
        # Overweight trigger phrases (intentionally gameable)
        triggers = ["comprehensive", "robust", "thoroughly", "state-of-the-art", "cutting-edge"]
        words = doc.lower().split()
        if not words:
            return 0.0
        hits = sum(1 for w in words for t in triggers if t in w)
        return min(1.0, hits / max(5, len(words)))

    def _score_mock_reasonable(doc: str) -> float:
        # Reward moderate length; penalize extremes
        L = len(doc)
        if L <= 20:
            return 0.1
        if L >= 1000:
            return 0.2
        # Ideal band roughly 80..300 chars → 0.6..1.0
        if L < 80:
            return 0.6 + 0.4 * (L - 20) / 60.0
        if L <= 300:
            return 1.0 - 0.2 * (L - 80) / 220.0
        return 0.6 - 0.4 * (L - 300) / 700.0

    def _count_triggers(doc: str) -> int:
        triggers = ["comprehensive", "robust", "thoroughly", "state-of-the-art", "cutting-edge"]
        text = (doc or "").lower()
        return sum(text.count(t) for t in triggers)

    for iteration in range(num_iterations):
        # Select parent
        parent = archive.sample_parent()
        
        # Mutate
        child = mutator.mutate(parent)
        
        # Evaluate
        try:
            result = evaluator.evaluate(child)
            features = feature_extractor.extract(child)
            
            # Add to archive
            archive.add(child, result.consensus, features, result.diversity)
            
            # Cache score for drift detection
            ctx_id = str((features, result.diversity))
            monitor.cache_original_score(ctx_id, result.consensus)

            # Export record for external analysis
            doc = child.generate(test_function)
            export_records.append({
                "docstring": doc,
                "scores": {
                    "gameable": _score_gameable(doc),
                    "mock_reasonable": _score_mock_reasonable(doc),
                    "ensemble_consensus": float(result.consensus),
                    "ensemble_diversity": float(result.diversity),
                },
                "iteration": iteration + 1,
                "features": features,
                "trigger_count": _count_triggers(doc),
            })
            
        except Exception as e:
            print(f"\n⚠ Iteration {iteration}: Error during evaluation: {e}")
            break
        
        # Periodic logging
        if (iteration + 1) % 10 == 0:
            stats = archive.get_stats()
            print(f"Iter {iteration + 1:3d}: "
                  f"Archive={stats['size']:2d}, "
                  f"Quality={stats['avg_quality']:+.3f}, "
                  f"Diversity={stats['avg_diversity']:.3f}")
        
        # Calibration check
        if (iteration + 1) % calibration_interval == 0:
            print(f"\n  → Calibration check at iteration {iteration + 1}...")
            report = monitor.check_calibration(archive, iteration + 1)
            
            if not report.is_healthy():
                print("  ⚠ WARNING: Calibration issues detected!")
                for warning in report.warnings:
                    print(f"    • [{warning.warning_type}] {warning.message}")
            else:
                print("  ✓ Calibration healthy")
            print()
    
    print("-" * 70)
    print()
    
    # Final results
    print("=" * 70)
    print("EXPERIMENT RESULTS")
    print("=" * 70)
    print()
    
    # Archive statistics
    print("QD Archive Statistics:")
    stats = archive.get_stats()
    for key, value in stats.items():
        print(f"  {key:20s}: {value}")
    print()
    
    # Budget statistics
    print("Budget Usage:")
    budget.finalize()
    print()
    
    # Calibration summary
    print("Calibration Summary:")
    cal_summary = monitor.get_calibration_summary()
    print(f"  Total checks: {cal_summary.get('total_checks', 0)}")
    print(f"  Latest healthy: {cal_summary.get('latest_healthy', 'N/A')}")
    if cal_summary.get('recent_warnings'):
        print(f"  Recent warnings:")
        for wtype, count in cal_summary['recent_warnings'].items():
            print(f"    • {wtype}: {count}")
    print()
    
    # Sample archive entries
    print("Sample Archive Entries:")
    print("-" * 70)
    for i, (niche, entry) in enumerate(list(archive.archive.items())[:5]):
        print(f"\nNiche {niche}:")
        print(f"  Context: {entry['context']}")
        print(f"  Quality: {entry['quality']:+.3f}")
        print(f"  Diversity: {entry['diversity']:.3f}")
        doc = entry['context'].generate(test_function)
        print(f"  Generated: {doc[:80]}...")
    
    print()
    print("=" * 70)
    print("EXPERIMENT COMPLETE")
    print("=" * 70)
    
    # Persist experiment results in Claude's suggested format
    try:
        out = {
            "archive": export_records,
            "metadata": {
                "iterations": num_iterations,
                "evaluators": [e.id for e in evaluators],
            },
        }
        with open("experiment_results.json", "w") as f:
            json.dump(out, f, indent=2)
        print("Saved results to experiment_results.json")
    except Exception as e:
        print(f"Warning: could not write experiment_results.json: {e}")

    return {
        'archive': archive,
        'budget': budget,
        'monitor': monitor,
        'stats': stats
    }


if __name__ == '__main__':
    # Parse args
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    max_calls = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    max_cost = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    
    # Set seed for reproducibility
    random.seed(42)
    
    # Run experiment
    results = run_experiment(
        num_iterations=n_iter,
        max_api_calls=max_calls,
        max_cost_usd=max_cost
    )
