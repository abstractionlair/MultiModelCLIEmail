import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from pairwise import bradley_terry_luce, agreement_metrics
from core_types import Judgment


class TestPairwiseAggregation(unittest.TestCase):
    def test_btl_simple(self):
        # Three candidates A,B,C with A>B, B>C, A>C
        js = [
            Judgment("j1", "A", "B", "A", 1.0),
            Judgment("j2", "B", "C", "B", 1.0),
            Judgment("j3", "A", "C", "A", 1.0),
        ]
        scores = bradley_terry_luce(js, ["A", "B", "C"])  # sums to 1
        self.assertGreater(scores["A"], scores["B"])  # A > B
        self.assertGreater(scores["B"], scores["C"])  # B > C
        self.assertAlmostEqual(sum(scores.values()), 1.0, places=6)

    def test_agreement(self):
        js = [
            Judgment("j1", "A", "B", "A", 1.0),
            Judgment("j2", "A", "B", "A", 1.0),
            Judgment("j3", "A", "B", "B", 1.0),
        ]
        avg, per = agreement_metrics(js)
        # 2 vs 1 should yield partial agreement
        self.assertGreater(avg, 0.0)
        self.assertLess(avg, 1.0)


if __name__ == "__main__":
    unittest.main()
