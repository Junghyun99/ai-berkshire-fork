"""Offline smoke tests for SAA monthly-return panel validation."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_data_quality import load_panel, statistics

FIELDS = ["month", "asset_id", "total_return_local", "fx_to_krw_return",
          "source_id", "as_of", "available_at", "quality"]


def rows():
    return [{"month": m, "asset_id": a, "total_return_local": r, "fx_to_krw_return": f,
             "source_id": "synthetic", "as_of": m + "-28", "available_at": m + "-28",
             "quality": "verified"}
            for m, a, r, f in [
                ("2025-01", "KR", "0.01", "0"), ("2025-01", "US", "0.02", "0.01"),
                ("2025-02", "KR", "-0.01", "0"), ("2025-02", "US", "0.03", "-0.01"),
                ("2025-03", "KR", "0.02", "0"), ("2025-03", "US", "-0.02", "0.02")
            ]]


class TestSAAData(unittest.TestCase):
    def check(self, data, valid=True):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(data)
            if valid:
                months, assets, panel = load_panel(p, 3)
                self.assertEqual((len(months), assets), (3, ["KR", "US"]))
                return statistics(months, assets, panel)
            with self.assertRaises(ValueError):
                load_panel(p, 3)

    def test_valid_and_fx_compound(self):
        data = rows()
        s = self.check(data)
        self.assertAlmostEqual(s["annualized_arithmetic_historical_mean"]["KR"], 0.08)
        self.assertIsNotNone(s["sample_correlation"][0][1])

    def test_duplicate(self):
        data = rows()
        data.append(dict(data[0]))
        self.check(data, False)

    def test_missing_asset(self):
        self.check(rows()[:-1], False)

    def test_missing_calendar_month(self):
        data = rows()
        for r in data:
            if r["month"] == "2025-02":
                r["month"], r["as_of"], r["available_at"] = "2025-04", "2025-04-28", "2025-04-28"
        self.check(data, False)

    def test_unverified(self):
        data = rows()
        data[0]["quality"] = "illustrative"
        self.check(data, False)

    def test_invalid_return(self):
        data = rows()
        data[0]["total_return_local"] = "-1.1"
        self.check(data, False)

    def test_date_before_observation(self):
        data = rows()
        data[0]["available_at"] = "2025-01-01"
        self.check(data, False)


if __name__ == "__main__":
    unittest.main()
