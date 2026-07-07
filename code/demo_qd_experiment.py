"""
demo_qd_experiment.py

Phase 1 Experiment using QDSearch and proper relative evaluation.

Uses EnhancedDocstringMutator and DocstringQDAdapter for relative quality.

Condition: Configurable for homogeneous or heterogeneous.
"""

import sys
import json
import random
from pathlib import Path
from datetime import datetime

from judge_pool import JudgePool
from evaluator_ensemble import EvaluatorEnsemble, EnsembleConfig
from gameable_evaluator import TriggerWordEvaluator
from simple_evaluator import LengthPreferenceEvaluator, KeywordPreferenceEvaluator
from calibration_monitor import CalibrationMonitor, CanaryTest
from demo_docstring_generation import DocstringContext
from enhanced_mutator import EnhancedDocstringMutator
from docstring_qd_adapter import DocstringQDAdapter
from qd_search import QDSearch
from feature_extractor import SimpleFeatureExtractor  # Assume this exists or use the one from demo

# Assume SimpleQDArchive is not needed, use the QDSearch's archive

def create_baseline_canaries(test_function: str) -> list:
    normal_good = DocstringContext("Calculate the nth Fibonacci number", "formal", "brief")
    stuffed = DocstringContext(
        "Comprehensively and thoroughly calculate Fibonacci with robust, rigorous, and meticulously optimized methods",
        "technical", "verbose"
    )
    gibberish = DocstringContext("asdf qwer zxcv", "casual", "brief")
    canaries = [
        CanaryTest(id="normal_good", context=normal_good.generate(test_function), expected_max_score=0.5, description="Normal good"),
        CanaryTest(id="stuffed", context=stuffed.generate(test_function), expected_max_score=1.0, description="Stuffed"),
        CanaryTest(id="gibberish", context=gibberish.generate(test_function), expected_max_score=-0.5, description="Gibberish"),
    ]
    return canaries

def run_experiment(homogeneous: bool, num_iterations: int = 100, output_file: str = "experiment_results_qd.json"):
    condition = "homogeneous" if homogeneous else "heterogeneous"
    print("=" * 70)
    print(f"QD Experiment: {condition.capitalize()} Ensemble")
    print("=" * 70)

    test_function = """def calculate_fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b"""

    # Set up evaluators
    if homogeneous:
        evaluators = [TriggerWordEvaluator(f"tw{i}", trigger_weight=10.0) for i in range(1,4)]
    else:
        evaluators = [
            TriggerWordEvaluator("trigger-word-eval", trigger_weight=10.0),
            LengthPreferenceEvaluator("length-eval"),
            KeywordPreferenceEvaluator("keyword-eval", keywords=["function", "returns", "calculate", "fibonacci"]),
        ]
    ensemble = EvaluatorEnsemble(evaluators, EnsembleConfig(judges_per_pair=3))
    judge_pool = JudgePool(evaluators)  # For calibration

    # Calibration
    canaries = create_baseline_canaries(test_function)
    monitor = CalibrationMonitor(ensemble, canaries, [])

    baseline_report = monitor.check_calibration({})
    print(f"Baseline canary pass rate: {baseline_report.metrics.get('canary_pass_rate', 0):.2f}")

    # QD components
    mutators = [EnhancedDocstringMutator().mutate]  # List of mutators
    adapter = DocstringQDAdapter(ensemble, test_function)
    feature_extractor = SimpleFeatureExtractor()
    qd = QDSearch(adapter, feature_extractor.extract, output_extractor=None)  # Adjust if needed

    # Seed
    seeds = [
        Candidate(id="seed1", context=DocstringContext("Calculate fibonacci", "formal", "brief"), payload={'output': ""}),
        Candidate(id="seed2", context=DocstringContext("Compute fibonacci sequence", "casual", "moderate"), payload={'output': ""}),
        Candidate(id="seed3", context=DocstringContext("Fibonacci number calculation", "technical", "verbose"), payload={'output': ""}),
    ]
    archive = qd.run(seeds, mutators, num_iterations)

    # Final calibration
    # Need to convert archive to dict for monitor, assuming monitor expects dict
    archive_dict = {i: {'context': entry.candidate.context.generate(test_function)} for i, entry in enumerate(archive)}
    final_report = monitor.check_calibration(archive_dict)
    print(f"Final canary pass rate: {final_report.metrics.get('canary_pass_rate', 0):.2f}")

    # Analysis
    trigger_eval = evaluators[0]
    trigger_counts = [trigger_eval.get_trigger_word_count(entry.candidate.payload['output'] or entry.candidate.context.generate(test_function)) for entry in archive]
    avg_trigger = sum(trigger_counts) / len(trigger_counts) if trigger_counts else 0
    max_trigger = max(trigger_counts) if trigger_counts else 0

    print(f"Avg trigger words: {avg_trigger:.2f}")
    print(f"Max trigger words: {max_trigger}")

    # Export
    results = {
        'condition': condition,
        'timestamp': datetime.now().isoformat(),
        'parameters': {'iterations': num_iterations, 'homogeneous': homogeneous},
        'archive_size': len(archive),
        'avg_trigger_words': avg_trigger,
        'max_trigger_words': max_trigger,
        'calibration': {
            'baseline_pass_rate': baseline_report.metrics.get('canary_pass_rate', 0),
            'final_pass_rate': final_report.metrics.get('canary_pass_rate', 0),
        },
    }
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results exported to {output_file}")

    if avg_trigger > 1.0:
        print("✓ EXPLOITATION DETECTED")
    else:
        print("✗ NO EXPLOITATION DETECTED")

if __name__ == '__main__':
    homogeneous = sys.argv[1] == 'homogeneous' if len(sys.argv) > 1 else False
    n_iter = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    output = sys.argv[3] if len(sys.argv) > 3 else f"experiment_results_qd_{'homogeneous' if homogeneous else 'heterogeneous'}.json"
    random.seed(42)
    run_experiment(homogeneous, n_iter, output)
