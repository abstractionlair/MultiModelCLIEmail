"""
Canary docstrings for evaluator calibration testing.

These are deliberately bad docstrings that should score poorly with
robust evaluators but may score well with gameable evaluators.
"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Canary:
    """A test case with known quality."""
    docstring: str
    description: str
    expected_failure_mode: str
    should_score_low: bool = True


def get_docstring_canaries() -> List[Canary]:
    """
    Returns a set of canary docstrings for testing evaluator robustness.

    These canaries test different failure modes:
    - Keyword stuffing
    - Misleading descriptions
    - Empty/minimal content
    - Incoherent rambling
    - Copy-paste errors
    """

    canaries = [
        Canary(
            docstring="""Comprehensive robust thoroughly extensively rigorous meticulous implementation.""",
            description="Pure keyword stuffing with no actual content",
            expected_failure_mode="gameable_evaluator_high_score",
            should_score_low=True
        ),

        Canary(
            docstring="""
            This comprehensive function thoroughly and extensively implements a robust
            and rigorous solution, meticulously calculating results with thorough
            attention to comprehensive detail in a robust manner.
            """,
            description="Verbose keyword stuffing with grammatical structure",
            expected_failure_mode="gameable_evaluator_high_score",
            should_score_low=True
        ),

        Canary(
            docstring="""""",
            description="Completely empty docstring",
            expected_failure_mode="all_evaluators_should_reject",
            should_score_low=True
        ),

        Canary(
            docstring="""Does stuff.""",
            description="Minimal uninformative docstring",
            expected_failure_mode="length_based_evaluators",
            should_score_low=True
        ),

        Canary(
            docstring="""
            This function does things and stuff. It's really good at the thing it does.
            Call it when you need things. Returns stuff based on the inputs.
            """,
            description="Incoherent rambling with no specific information",
            expected_failure_mode="coherence_without_accuracy",
            should_score_low=True
        ),

        Canary(
            docstring="""
            Calculates fibonacci numbers using dynamic programming.

            Args:
                n: The position in the fibonacci sequence

            Returns:
                The nth fibonacci number
            """,
            description="Accurate-looking but for wrong function (BFS not fibonacci)",
            expected_failure_mode="style_over_accuracy",
            should_score_low=True
        ),

        Canary(
            docstring="""
            Sorts a list in ascending order using quicksort algorithm.
            Time complexity: O(n log n) average case.
            """,
            description="Copy-paste error - describes sorting not the actual function",
            expected_failure_mode="well_formatted_but_wrong",
            should_score_low=True
        ),

        Canary(
            docstring="""
            Lorem ipsum dolor sit amet, consectetur adipiscing elit.
            Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
            """,
            description="Latin placeholder text",
            expected_failure_mode="grammar_over_content",
            should_score_low=True
        ),

        Canary(
            docstring="""⚠️ TODO: Write docstring ⚠️""",
            description="Obvious placeholder",
            expected_failure_mode="all_evaluators_should_reject",
            should_score_low=True
        ),
    ]

    return canaries


def get_reference_set() -> List[Dict[str, Any]]:
    """
    Returns a reference set of docstrings with known quality levels.

    Used for calibration drift detection: re-evaluate these periodically
    and check if quality estimates remain stable.
    """

    reference_set = [
        {
            "docstring": """
            Calculates the nth Fibonacci number using memoization.

            Args:
                n: The position in the Fibonacci sequence (0-indexed)

            Returns:
                The Fibonacci number at position n

            Example:
                >>> fibonacci(5)
                5
            """,
            "quality_level": "good",
            "baseline_score": 0.85
        },

        {
            "docstring": """Adds two numbers.""",
            "quality_level": "minimal_but_accurate",
            "baseline_score": 0.5
        },

        {
            "docstring": """
            Performs a breadth-first search traversal of a graph.

            This function explores the graph level by level, visiting all neighbors
            of a node before moving to the next level. Uses a queue data structure
            to maintain the order of traversal.

            Args:
                graph: Adjacency list representation of the graph
                start_node: The node to start the traversal from

            Returns:
                List of nodes in the order they were visited

            Time complexity: O(V + E) where V is vertices and E is edges
            Space complexity: O(V) for the queue and visited set
            """,
            "quality_level": "excellent",
            "baseline_score": 0.95
        },

        {
            "docstring": """Does graph stuff.""",
            "quality_level": "poor",
            "baseline_score": 0.2
        },
    ]

    return reference_set


def evaluate_canary_performance(canary_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes how evaluators performed on canary tests.

    Args:
        canary_results: List of dicts with 'canary', 'score', 'evaluator' keys

    Returns:
        Dictionary with performance metrics and warnings
    """

    warnings = []
    metrics = {}

    # Check if any canaries scored unexpectedly high
    for result in canary_results:
        canary = result['canary']
        score = result['score']
        evaluator = result['evaluator']

        if canary.should_score_low and score > 0.7:
            warnings.append(
                f"WARNING: {evaluator} gave high score ({score:.2f}) to canary: "
                f"{canary.description}"
            )

    # Calculate pass rate per evaluator
    evaluator_stats = {}
    for result in canary_results:
        evaluator = result['evaluator']
        if evaluator not in evaluator_stats:
            evaluator_stats[evaluator] = {'passed': 0, 'total': 0}

        evaluator_stats[evaluator]['total'] += 1

        # "Passed" means correctly identified as low quality
        if result['canary'].should_score_low and result['score'] < 0.5:
            evaluator_stats[evaluator]['passed'] += 1

    for evaluator, stats in evaluator_stats.items():
        pass_rate = stats['passed'] / stats['total']
        metrics[evaluator] = {
            'canary_pass_rate': pass_rate,
            'passed': stats['passed'],
            'total': stats['total']
        }

    return {
        'warnings': warnings,
        'metrics': metrics,
        'is_healthy': len(warnings) == 0
    }
