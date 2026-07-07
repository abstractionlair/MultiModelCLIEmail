import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from core_types import Candidate, Context, CallableEvaluator
from evaluator_ensemble import EvaluatorEnsemble, EnsembleConfig


def scorer_linear(weight_key: str):
    def _score(c: Candidate) -> float:
        return float(c.payload.get(weight_key, 0.0))
    return _score


class TestEvaluatorEnsemble(unittest.TestCase):
    def test_batch_evaluation(self):
        ctx = Context(id="ctx1", prompt="Do X", params={})
        A = Candidate(id="A", context=ctx, payload={"q": 1.0})
        B = Candidate(id="B", context=ctx, payload={"q": 0.5})
        C = Candidate(id="C", context=ctx, payload={"q": 0.1})

        e1 = CallableEvaluator("e1", scorer_linear("q"), confidence=0.9)
        e2 = CallableEvaluator("e2", scorer_linear("q"), confidence=0.8)
        ens = EvaluatorEnsemble([e1, e2], EnsembleConfig(judges_per_pair=2, rotate_judges=False))

        res = ens.evaluate_batch([A, B, C])
        self.assertEqual(res.ranking[0], "A")
        self.assertGreater(res.scores["A"], res.scores["B"])  # monotonicity
        self.assertGreaterEqual(res.consensus, 0.0)
        self.assertLessEqual(res.consensus, 1.0)


if __name__ == "__main__":
    unittest.main()
