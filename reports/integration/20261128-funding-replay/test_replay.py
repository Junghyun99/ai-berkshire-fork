import unittest

from replay import TICKERS, cost_adjusted_spread, rules_for, valuation, weekly


class ReplayTest(unittest.TestCase):
    def test_fees_and_unfunded_target(self):
        self.assertEqual(cost_adjusted_spread(1, [], .0025), 0)
        self.assertAlmostEqual(cost_adjusted_spread(.2, [.1, .1], .0025), .285)

    def test_no_self_sale_and_overlap(self):
        for n in TICKERS:
            for donors in rules_for(n).values():
                self.assertNotIn(n, donors)
        self.assertEqual(rules_for("META")["ad_demand"], ["GOOGL"])
        self.assertEqual(rules_for("MSFT")["ad_demand"], [])

    def test_zero_cost_rotation_identity(self):
        for _, _, window in weekly(fee=0):
            for method in ("proportional", "sector", "ad_demand"):
                self.assertAlmostEqual(sum(w[method] for w in window.values()), 0)

    def test_strict_valuation_rule(self):
        rules, _ = valuation()
        self.assertEqual(rules["AAPL"]["overvalued"], [])
        self.assertEqual(rules["META"]["overvalued"], ["AAPL"])
