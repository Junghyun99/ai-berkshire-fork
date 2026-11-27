import math
import unittest

from compare import evaluate, weights


class WeightComparisonTest(unittest.TestCase):
    def test_equal_groups_share_budget_within_each_group(self):
        rows = [{"ticker": t, "group": g} for t, g in zip("ABC", "XXY")]
        self.assertEqual(weights(rows, "group"), {"A": .25, "B": .25, "C": .5})

    def test_drawdown_and_annualized_ratios(self):
        cagr, mdd, sharpe, sortino = evaluate([1, 1.25, 1], 1)
        self.assertEqual(cagr, 0)
        self.assertAlmostEqual(mdd, -.2)
        self.assertAlmostEqual(sharpe, .025 * math.sqrt(252) / (.45 / math.sqrt(2)))
        self.assertAlmostEqual(sortino, .025 * math.sqrt(252) / (.2 / math.sqrt(2)))

    def test_flat_returns(self):
        self.assertEqual(evaluate([1, 1, 1], 1), (0, 0, None, None))
