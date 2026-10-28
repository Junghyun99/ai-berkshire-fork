"""Tests for deterministic SAA research walk-forward."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_backtest import backtest, candidates, performance


class TestSAABacktest(unittest.TestCase):
    def setUp(self):
        self.months = [f"{2020 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(84)]
        self.assets = ["KR", "US", "BONDS"]
        self.panel = [[.01 + .015 * (i % 3 == 0),
                       .015 - .04 * (i % 11 == 0),
                       .002 + .003 * (i % 7 == 0)] for i in range(84)]

    def test_reproducible(self):
        a = backtest(self.months, self.assets, self.panel, grid_count=100)
        b = backtest(self.months, self.assets, self.panel, grid_count=100)
        self.assertEqual(a, b)
        self.assertEqual(a["oos_start"], "2025-01")
        self.assertEqual(set(a["strategies"]), {"equal", "minvar", "shrink_minvar", "max_sharpe", "risk_parity"})

    def test_weights_nonnegative_sum_one(self):
        r = backtest(self.months, self.assets, self.panel, grid_count=100)
        for strategy in r["strategies"].values():
            for item in strategy["rebalance_targets"]:
                w = list(item["target"].values())
                self.assertAlmostEqual(sum(w), 1)
                self.assertTrue(all(0 <= x <= 1 for x in w))

    def test_no_future_leakage(self):
        a = backtest(self.months, self.assets, self.panel, grid_count=100)
        changed = [row[:] for row in self.panel]
        changed[-1] = [-.5, -.5, -.5]
        b = backtest(self.months, self.assets, changed, grid_count=100)
        # All target weights, including the last month's, are based on prior data only.
        for s in a["strategies"]:
            self.assertEqual(a["strategies"][s]["rebalance_targets"],
                             b["strategies"][s]["rebalance_targets"])

    def test_costs_reduce_return(self):
        a = performance([.01] * 12, [0.] * 11 + [1.], 0)
        b = performance([.01] * 12, [0.] * 11 + [1.], 100)
        self.assertLess(b["cagr"], a["cagr"])

    def test_insufficient_data(self):
        with self.assertRaises(ValueError):
            backtest(self.months[:24], self.assets, self.panel[:24], lookback=24)

    def test_candidates_deterministic(self):
        self.assertEqual(candidates(3, count=50), candidates(3, count=50))


if __name__ == "__main__":
    unittest.main()
