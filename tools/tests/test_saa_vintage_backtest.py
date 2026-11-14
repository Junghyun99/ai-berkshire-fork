"""Synthetic training vintages and deliberately different realized returns."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_backtest import backtest, vintage_training_window


class VintageBacktestTest(unittest.TestCase):
    def setUp(self):
        self.months = [f"{2020 + i // 12}-{i % 12 + 1:02}" for i in range(26)]
        self.assets = ["A", "B"]
        self.panel = [[0.02, -0.01]] * 26
        self.manifest = dict(decision_times={}, observations={}, records=[], rf_series_id="RF")
        for i, month in enumerate(self.months):
            stamp = month + "-28T09:00:00+09:00"
            self.manifest["decision_times"][month] = month + "-01T00:00:00+09:00"
            self.manifest["observations"][month] = dict.fromkeys(["A", "B", "RF"], stamp)
            for name, value in zip(["A", "B", "RF"], [0.01 * (i % 2), 0.001, 0.003]):
                self.manifest["records"].append(dict(series_id=name, value=value,
                    observation_at=stamp, available_at=stamp, vintage_at=stamp, vintage_id="v1",
                    retrieval_at="2024-01-01T00:00:00Z", source_url="fixture", evidence_ref="fixture"))

    def run_model(self):
        return backtest(self.months, self.assets, self.panel, lookback=24, rebalance=1,
                        grid_count=5, risk_free=[0.] * 26, training_vintages=self.manifest)

    def test_train_on_selected_values_score_on_realized_panel(self):
        train, rf, _ = vintage_training_window(self.manifest, self.months[24],
                                                self.months[:24], self.assets, True)
        self.assertEqual(train[:2], [[0., 0.001], [0.01, 0.001]])
        self.assertEqual(rf, [0.003] * 24)
        result = self.run_model()
        revised = dict(self.manifest["records"][3], value=0.8, vintage_id="v2",
                       available_at="2022-01-15T00:00:00Z", vintage_at="2022-01-15T00:00:00Z")
        self.manifest["records"].append(revised)
        updated = self.run_model()
        self.assertEqual(updated["training_vintage_audit"]["2022-01"]["selected"],
                         result["training_vintage_audit"]["2022-01"]["selected"])
        self.assertIn(revised, updated["training_vintage_audit"]["2022-02"]["selected"])
        self.assertEqual(updated["strategies"]["minvar"]["rebalance_targets"][0]["target"],
                         {"A": 0., "B": 1.})

    def test_missing_rf_blocks_at_second_decision(self):
        self.manifest["records"].pop(24 * 3 + 2)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.run_model()

    def test_decision_inside_return_month_blocks(self):
        self.manifest["decision_times"]["2022-01"] = "2022-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "after the start"):
            self.run_model()
