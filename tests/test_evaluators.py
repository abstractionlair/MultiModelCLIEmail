"""
test_evaluators.py

Unit tests for the evaluation framework.
Tests core abstractions, judge pool, and simple evaluators.
"""

import sys
sys.path.insert(0, '~/projects/MultiModelCLIEmail/code')

import unittest
from evaluator_base import Evaluator, Judgment, Preference, EvaluationResult
from judge_pool import JudgePool
from simple_evaluator import (
    MockEvaluator, 
    LengthPreferenceEvaluator,
    KeywordPreferenceEvaluator,
    RandomEvaluator
)


class TestJudgment(unittest.TestCase):
    """Test Judgment dataclass."""
    
    def test_valid_judgment(self):
        """Test creating valid judgments."""
        j = Judgment(preferred=Preference.A, confidence=0.8)
        self.assertEqual(j.preferred, Preference.A)
        self.assertEqual(j.confidence, 0.8)
        self.assertIsNone(j.reasoning)
    
    def test_judgment_with_reasoning(self):
        """Test judgment with reasoning."""
        j = Judgment(
            preferred=Preference.B,
            confidence=0.9,
            reasoning="B is more concise"
        )
        self.assertEqual(j.reasoning, "B is more concise")
    
    def test_invalid_confidence(self):
        """Test that invalid confidence raises error."""
        with self.assertRaises(ValueError):
            Judgment(preferred=Preference.A, confidence=1.5)
        
        with self.assertRaises(ValueError):
            Judgment(preferred=Preference.A, confidence=-0.1)


class TestEvaluationResult(unittest.TestCase):
    """Test EvaluationResult dataclass."""
    
    def test_consensus_unanimous_a(self):
        """Test consensus with unanimous preference for A."""
        judgments = [
            Judgment(Preference.A, 0.8),
            Judgment(Preference.A, 0.9),
            Judgment(Preference.A, 0.7),
        ]
        result = EvaluationResult(judgments=judgments)
        
        # Should be positive (favoring A)
        self.assertGreater(result.consensus, 0.7)
        # Low diversity (all agree)
        self.assertLess(result.diversity, 0.3)
    
    def test_consensus_unanimous_b(self):
        """Test consensus with unanimous preference for B."""
        judgments = [
            Judgment(Preference.B, 0.8),
            Judgment(Preference.B, 0.9),
            Judgment(Preference.B, 0.7),
        ]
        result = EvaluationResult(judgments=judgments)
        
        # Should be negative (favoring B)
        self.assertLess(result.consensus, -0.7)
        # Low diversity (all agree)
        self.assertLess(result.diversity, 0.3)
    
    def test_consensus_split(self):
        """Test consensus with split decision."""
        judgments = [
            Judgment(Preference.A, 0.8),
            Judgment(Preference.B, 0.8),
        ]
        result = EvaluationResult(judgments=judgments)
        
        # Should be near zero (split)
        self.assertAlmostEqual(result.consensus, 0.0, places=1)
        # High diversity (disagreement)
        self.assertGreater(result.diversity, 0.5)
    
    def test_diversity_calculation(self):
        """Test diversity metric calculation."""
        # Perfect agreement
        unanimous = EvaluationResult(judgments=[
            Judgment(Preference.A, 0.8),
            Judgment(Preference.A, 0.8),
            Judgment(Preference.A, 0.8),
        ])
        self.assertAlmostEqual(unanimous.diversity, 0.0, places=2)
        
        # Maximum disagreement (equal split)
        split = EvaluationResult(judgments=[
            Judgment(Preference.A, 0.8),
            Judgment(Preference.B, 0.8),
            Judgment(Preference.NEITHER, 0.8),
        ])
        # Should be high diversity
        self.assertGreater(split.diversity, 0.8)


class TestMockEvaluator(unittest.TestCase):
    """Test MockEvaluator implementation."""
    
    def test_deterministic_behavior(self):
        """Test that same evaluator ID gives consistent results."""
        eval1 = MockEvaluator("test-eval")
        eval2 = MockEvaluator("test-eval")
        
        # Same inputs should give same judgments
        j1 = eval1.judge("candidate A", "candidate B")
        j2 = eval2.judge("candidate A", "candidate B")
        
        self.assertEqual(j1.preferred, j2.preferred)
        self.assertAlmostEqual(j1.confidence, j2.confidence, places=2)
    
    def test_bias_preference(self):
        """Test that bias influences judgments."""
        eval_bias_a = MockEvaluator("bias-a", preference_bias=Preference.A)
        
        # Should usually prefer A
        a_count = 0
        for i in range(10):
            j = eval_bias_a.judge(f"candidate {i}", f"other {i}")
            if j.preferred == Preference.A:
                a_count += 1
        
        # At least 70% should prefer A (80% bias - noise)
        self.assertGreaterEqual(a_count, 7)


class TestLengthPreferenceEvaluator(unittest.TestCase):
    """Test LengthPreferenceEvaluator."""
    
    def test_prefers_longer(self):
        """Test that evaluator prefers longer content."""
        evaluator = LengthPreferenceEvaluator("length-eval")
        
        short = "short"
        long = "this is a much longer piece of content"
        
        judgment = evaluator.judge(short, long)
        self.assertEqual(judgment.preferred, Preference.B)
    
    def test_similar_lengths_neither(self):
        """Test that similar lengths result in NEITHER."""
        evaluator = LengthPreferenceEvaluator("length-eval")
        
        j = evaluator.judge("test", "exam")
        self.assertEqual(j.preferred, Preference.NEITHER)


class TestKeywordPreferenceEvaluator(unittest.TestCase):
    """Test KeywordPreferenceEvaluator."""
    
    def test_keyword_preference(self):
        """Test that evaluator prefers content with keywords."""
        evaluator = KeywordPreferenceEvaluator(
            "keyword-eval",
            keywords=["python", "testing", "quality"]
        )
        
        candidate_a = "This is about python testing and quality assurance"
        candidate_b = "This is about java programming"
        
        judgment = evaluator.judge(candidate_a, candidate_b)
        self.assertEqual(judgment.preferred, Preference.A)
        self.assertGreater(judgment.confidence, 0.7)


class TestJudgePool(unittest.TestCase):
    """Test JudgePool ensemble management."""
    
    def setUp(self):
        """Create test evaluators."""
        self.evaluators = [
            MockEvaluator("eval-1"),
            MockEvaluator("eval-2"),
            MockEvaluator("eval-3"),
            LengthPreferenceEvaluator("length-eval"),
        ]
        self.pool = JudgePool(self.evaluators, default_n_judges=3)
    
    def test_pool_initialization(self):
        """Test pool initialization."""
        self.assertEqual(len(self.pool.evaluators), 4)
        self.assertEqual(self.pool.default_n_judges, 3)
    
    def test_minimum_evaluators_required(self):
        """Test that pool requires at least 2 evaluators."""
        with self.assertRaises(ValueError):
            JudgePool([MockEvaluator("solo")])
    
    def test_judge_selection_excludes_author(self):
        """Test that author is excluded from judging."""
        judges = self.pool.select_judges(exclude_author_id="eval-1", n_judges=2)
        
        # Should get 2 judges
        self.assertEqual(len(judges), 2)
        
        # None should be eval-1
        for judge in judges:
            self.assertNotEqual(judge.id, "eval-1")
    
    def test_evaluate_pair_basic(self):
        """Test basic pairwise evaluation."""
        result = self.pool.evaluate_pair("candidate A", "candidate B")
        
        # Should have judgments from 3 evaluators (default)
        self.assertEqual(len(result.judgments), 3)
        
        # Should have consensus
        self.assertIsNotNone(result.consensus)
        self.assertIsInstance(result.consensus, float)
        
        # Should have diversity metric
        self.assertIsInstance(result.diversity, float)
        self.assertGreaterEqual(result.diversity, 0.0)
        self.assertLessEqual(result.diversity, 1.0)
    
    def test_evaluate_pair_with_author_exclusion(self):
        """Test that author is excluded from evaluation."""
        # Register eval-1 as author of candidate A
        self.pool.register_author("content-a", "eval-1")
        
        result = self.pool.evaluate_pair(
            "candidate A",
            "candidate B",
            candidate_a_id="content-a",
            n_judges=2
        )
        
        # Should have 2 judgments
        self.assertEqual(len(result.judgments), 2)
        
        # eval-1 should be excluded
        judges_used = result.metadata['judges_used']
        self.assertNotIn("eval-1", judges_used)
        self.assertEqual(result.metadata['excluded_author'], "eval-1")
    
    def test_evaluate_batch(self):
        """Test batch evaluation."""
        pairs = [
            ("A1", "B1"),
            ("A2", "B2"),
            ("A3", "B3"),
        ]
        
        results = self.pool.evaluate_batch(pairs, n_judges=2)
        
        # Should have 3 results
        self.assertEqual(len(results), 3)
        
        # Each should have 2 judgments
        for result in results:
            self.assertEqual(len(result.judgments), 2)
    
    def test_disagreement_detection(self):
        """Test that disagreement is properly detected."""
        # Create evaluators with opposing biases
        biased_evaluators = [
            MockEvaluator("prefer-a", preference_bias=Preference.A, confidence_level=0.9),
            MockEvaluator("prefer-b", preference_bias=Preference.B, confidence_level=0.9),
            MockEvaluator("prefer-neither", preference_bias=Preference.NEITHER),
        ]
        pool = JudgePool(biased_evaluators)
        
        result = pool.evaluate_pair("candidate A", "candidate B")
        
        # Should have high diversity (disagreement)
        self.assertGreater(result.diversity, 0.5)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for realistic scenarios."""
    
    def test_code_quality_evaluation(self):
        """Test evaluating code quality (length as proxy)."""
        # Simulate code snippets of different quality
        # (using length as a simple proxy)
        
        good_code = """
def fibonacci(n):
    '''Calculate nth Fibonacci number.'''
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b
"""
        
        poor_code = "def f(n): return n"
        
        evaluators = [
            LengthPreferenceEvaluator("eval-1"),
            LengthPreferenceEvaluator("eval-2"),
            LengthPreferenceEvaluator("eval-3"),
        ]
        pool = JudgePool(evaluators)
        
        result = pool.evaluate_pair(good_code, poor_code)
        
        # Should prefer good_code (longer, more complete)
        self.assertGreater(result.consensus, 0.5)
        
        # Should have low diversity (all agree)
        self.assertLess(result.diversity, 0.3)
    
    def test_style_vs_substance_disagreement(self):
        """Test disagreement when evaluators value different things."""
        verbose = "This is a very detailed and thorough explanation of the concept " * 5
        concise = "Clear, concise explanation."
        
        evaluators = [
            LengthPreferenceEvaluator("verbose-lover"),
            KeywordPreferenceEvaluator("keyword-eval", keywords=["clear", "concise"]),
        ]
        pool = JudgePool(evaluators)
        
        result = pool.evaluate_pair(verbose, concise)
        
        # Should have high diversity (different preferences)
        # One prefers length, other prefers keywords
        self.assertGreater(result.diversity, 0.3)


if __name__ == '__main__':
    unittest.main()
