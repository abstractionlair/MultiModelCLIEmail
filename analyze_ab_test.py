import json

def analyze_results(non_stateful_file, stateful_file):
    with open(non_stateful_file, 'r') as f:
        non_stateful_data = json.load(f)
    with open(stateful_file, 'r') as f:
        stateful_data = json.load(f)

    non_stateful_stats = non_stateful_data['metadata']
    stateful_stats = stateful_data['metadata']

    print("A/B Test Analysis: Stateful vs. Non-Stateful Evaluators")
    print("=" * 70)
    print(f"Non-Stateful Run:")
    print(f"  - Iterations: {non_stateful_stats['iterations']}")
    print(f"  - Evaluators: {non_stateful_stats['evaluators']}")
    print(f"  - Final Archive Size: {len(non_stateful_data['archive'])}")
    print(f"  - Final Average Quality: {non_stateful_data['archive'][-1]['scores']['ensemble_consensus']:.3f}")
    print("-" * 70)
    print(f"Stateful Run:")
    print(f"  - Iterations: {stateful_stats['iterations']}")
    print(f"  - Evaluators: {stateful_stats['evaluators']}")
    print(f"  - Final Archive Size: {len(stateful_data['archive'])}")
    print(f"  - Final Average Quality: {stateful_data['archive'][-1]['scores']['ensemble_consensus']:.3f}")
    print("=" * 70)

if __name__ == '__main__':
    analyze_results('experiment_results_non_stateful.json', 'experiment_results_stateful.json')
