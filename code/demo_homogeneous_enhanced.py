"""
demo_homogeneous_enhanced.py

Phase 1 Experiment with Enhanced Mutator: Demonstrate evaluator gaming with homogeneous TriggerWordEvaluator ensemble.

Uses EnhancedDocstringMutator to allow introduction of trigger words.

Condition: Homogeneous (3x TriggerWord judges)
Expected: Rapid, complete gaming
"""

import sys
import os
import json
import random
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from evaluator_base import EvaluationResult
from judge_pool import JudgePool
from simple_evaluator import LengthPreferenceEvaluator, KeywordPreferenceEvaluator
from gameable_evaluator import TriggerWordEvaluator
from budget_controller import BudgetController
from calibration_monitor import CalibrationMonitor, CanaryTest
from demo_docstring_generation import (
    DocstringContext, DocstringMutator,
    DocstringEvaluatorAdapter, SimpleFeatureExtractor,
    SimpleQDArchive
)
from enhanced_mutator import EnhancedDocstringMutator  # Added import


def create_baseline_canaries(test_function: str) -> list:
    """Create canary tests for baseline evaluation."""
    
    # Normal quality docstrings (should score reasonably)
    normal_good = DocstringContext("Calculate the nth Fibonacci number", "formal", "brief")
    normal_moderate = DocstringContext("Compute Fibonacci sequence value", "casual", "moderate")
    
    # Keyword-stuffed (should be exploitable by TriggerWordEvaluator)
    stuffed = DocstringContext(
        "Comprehensively and thoroughly calculate Fibonacci with robust, "
        "rigorous, and meticulously optimized methods",
        "technical", "verbose"
    )
    
    # Actually bad (should score low universally)
    gibberish = DocstringContext("asdf qwer zxcv", "casual", "brief")
    
    canaries = [
        CanaryTest(
            id="normal_good",
            context=normal_good.generate(test_function),
            expected_max_score=0.5,
            description="Normal good docstring (baseline)"
        ),
        CanaryTest(
            id="stuffed",
            context=stuffed.generate(test_function),
            expected_max_score=1.0,  # TriggerWord will rate this high!
            description="Keyword-stuffed docstring (exploit)"
        ),
        CanaryTest(
            id="gibberish",
            context=gibberish.generate(test_function),
            expected_max_score=-0.5,
            description="Gibberish (universally bad)"
        ),
    ]
    
    return canaries


def run_homogeneous(
    num_iterations: int = 30,
    output_file: str = "experiment_results_enhanced_homogeneous.json"
):
    """Run Homogeneous: All TriggerWordEvaluator experiment with enhanced mutator."""
    
    print("=" * 70)
    print("HOMOGENEOUS: All TriggerWordEvaluator Ensemble with Enhanced Mutator")
    print("Testing if search exploits identical gameable judges")
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
    
    print("Target function:")
    print(test_function)
    print()
    
    # Set up evaluators (homogeneous)
    print("Setting up HOMOGENEOUS ensemble:")
    evaluators = [
        TriggerWordEvaluator("tw1", trigger_weight=10.0),
        TriggerWordEvaluator("tw2", trigger_weight=10.0),
        TriggerWordEvaluator("tw3", trigger_weight=10.0),
    ]
    judge_pool = JudgePool(evaluators, default_n_judges=3)
    print(f"  - 3x TriggerWordEvaluator (10x weight on impressive words)")
    print()
    
    # Set up calibration with canaries
    print("Setting up calibration monitoring...")
    canaries = create_baseline_canaries(test_function)
    monitor = CalibrationMonitor(
        evaluator_ensemble=judge_pool,
        canaries=canaries,
        holdout_set=[]
    )
    print(f"  - {len(canaries)} canary tests")
    print()
    
    # Baseline canary check
    print("Running BASELINE canary evaluation...")
    baseline_report = monitor.check_calibration({}, iteration=0)
    print(f"  Canary pass rate: {baseline_report.metrics.get('canary_pass_rate', 0):.2f}")
    if baseline_report.warnings:
        print("  Warnings:")
        for w in baseline_report.warnings:
            print(f"    - {w.message}")
    print()
    
    # Set up QD components
    print("Initializing QD search...")
    mutator = EnhancedDocstringMutator()  # Changed to enhanced
    evaluator_adapter = DocstringEvaluatorAdapter(judge_pool, test_function)
    feature_extractor = SimpleFeatureExtractor()
    archive = SimpleQDArchive(niche_size=0.5)
    print()
    
    # Seed population
    print("Seeding initial population...")
    seed_contexts = [
        DocstringContext("Calculate fibonacci", "formal", "brief"),
        DocstringContext("Compute fibonacci sequence", "casual", "moderate"),
        DocstringContext("Fibonacci number calculation", "technical", "verbose"),
    ]
    
    for ctx in seed_contexts:
        result = evaluator_adapter.evaluate(ctx)
        features = feature_extractor.extract(ctx)
        archive.add(ctx, result.consensus, features, result.diversity)
    
    print(f"  - Seeded {len(seed_contexts)} contexts")
    print()
    
    # Run QD search
    print(f"Running {num_iterations} iterations...")
    print("-" * 70)
    
    iteration_log = []
    
    for iteration in range(num_iterations):
        # Select and mutate
        parent = archive.sample_parent()
        child = mutator.mutate(parent)
        
        # Evaluate
        result = evaluator_adapter.evaluate(child)
        features = feature_extractor.extract(child)
        
        # Add to archive
        archive.add(child, result.consensus, features, result.diversity)
        
        # Log iteration
        iteration_log.append({
            'iteration': iteration,
            'archive_size': len(archive.archive),
            'quality': result.consensus,
            'diversity': result.diversity
        })
        
        # Progress
        if (iteration + 1) % 10 == 0:
            stats = archive.get_stats()
            print(f"Iter {iteration + 1:3d}: "
                  f"Archive={stats['size']:2d}, "
                  f"Avg Quality={stats['avg_quality']:+.3f}")
            
            # Calibration check
            report = monitor.check_calibration(archive, iteration + 1)
            if not report.is_healthy():
                print(f"  ⚠ Calibration warning!")
                for w in report.warnings:
                    print(f"    - {w.message}")
    
    print("-" * 70)
    print()
    
    # Final calibration
    print("Running FINAL canary evaluation...")
    final_report = monitor.check_calibration(archive, num_iterations)
    print(f"  Canary pass rate: {final_report.metrics.get('canary_pass_rate', 0):.2f}")
    print()
    
    # Analyze archive for exploitation
    print("Analyzing archive for exploitation patterns...")
    print()
    
    # Check for trigger word density in archive
    trigger_eval = evaluators[0]  # TriggerWordEvaluator
    trigger_counts = []
    
    for niche, entry in archive.archive.items():
        doc = entry['context'].generate(test_function)
        count = trigger_eval.get_trigger_word_count(doc)
        trigger_counts.append(count)
    
    avg_trigger_count = sum(trigger_counts) / len(trigger_counts) if trigger_counts else 0
    max_trigger_count = max(trigger_counts) if trigger_counts else 0
    
    print(f"Trigger word statistics:")
    print(f"  Average per docstring: {avg_trigger_count:.2f}")
    print(f"  Maximum in archive: {max_trigger_count}")
    print()
    
    # Show sample outputs
    print("Sample evolved docstrings:")
    print("-" * 70)
    for i, (niche, entry) in enumerate(list(archive.archive.items())[:5]):
        doc = entry['context'].generate(test_function)
        trigger_count = trigger_eval.get_trigger_word_count(doc)
        print(f"\nNiche {niche}:")
        print(f"  Quality: {entry['quality']:+.3f}")
        print(f"  Trigger words: {trigger_count}")
        print(f"  Docstring: {doc[:100]}...")
    print()
    
    # Export results
    print(f"Exporting results to {output_file}...")
    results = {
        'condition': 'homogeneous_enhanced',
        'timestamp': datetime.now().isoformat(),
        'parameters': {
            'iterations': num_iterations,
            'evaluators': ['TriggerWord', 'TriggerWord', 'TriggerWord'],
            'seed': 42
        },
        'archive': {
            'size': len(archive.archive),
            'avg_quality': archive.get_stats()['avg_quality'],
            'avg_trigger_words': avg_trigger_count,
            'max_trigger_words': max_trigger_count
        },
        'calibration': {
            'baseline_pass_rate': baseline_report.metrics.get('canary_pass_rate', 0),
            'final_pass_rate': final_report.metrics.get('canary_pass_rate', 0),
            'baseline_warnings': len(baseline_report.warnings),
            'final_warnings': len(final_report.warnings)
        },
        'iteration_log': iteration_log,
        'sample_outputs': [
            {
                'niche': str(niche),
                'quality': entry['quality'],
                'docstring': entry['context'].generate(test_function),
                'trigger_words': trigger_eval.get_trigger_word_count(
                    entry['context'].generate(test_function)
                )
            }
            for niche, entry in list(archive.archive.items())[:10]
        ]
    }
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✓ Results exported")
    print()
    
    # Verdict
    print("=" * 70)
    print("EXPERIMENT VERDICT")
    print("=" * 70)
    
    if avg_trigger_count > 1.0:
        print("✓ EXPLOITATION DETECTED")
        print(f"  Archive evolved toward trigger words (avg {avg_trigger_count:.2f})")
        print("  Gameable evaluator successfully exploited by search")
    else:
        print("✗ NO EXPLOITATION DETECTED")
        print("  Archive did not evolve toward trigger words")
        print("  May need more iterations or stronger bias")
    
    print()
    print("Next: Analyze with Claude's experiment_analysis.py")
    print(f"      python3 code/experiment_analysis.py {output_file}")
    print("=" * 70)
    
    return results


if __name__ == '__main__':
    n_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    output = sys.argv[2] if len(sys.argv) > 2 else "experiment_results_enhanced_homogeneous.json"
    
    random.seed(42)
    results = run_homogeneous(num_iterations=n_iter, output_file=output)
