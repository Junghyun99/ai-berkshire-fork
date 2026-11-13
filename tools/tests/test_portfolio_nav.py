import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_nav import value


def fixture(day=2):
    at = f"2025-01-{day:02d}T00:00:00Z"
    sent, received = "2025-01-02T00:00:00Z", "2025-01-03T00:00:00Z"
    evidence = {"source_ref": "fixture", "quality": "synthetic_fixture"}
    common = dict(id="1", status="actual", source_ref="fixture", currency="USD", transfer_id="T")
    events = [dict(common, account="A", counterparty="B", kind="transfer_out", amount="-2", at=sent),
              dict(common, account="B", counterparty="A", kind="transfer_in", amount="2", at=received)]
    rows = [dict(evidence, account="A", at=at, net_by_currency={"USD": "10" if day < 2 else "8"},
                 booked_transit={}),
            dict(evidence, account="B", at=at, net_by_currency={"KRW": "1000", "USD": "2" if day >= 3 else "0"},
                 booked_transit={})]
    return dict(schema_version="portfolio-nav-0.1", scope_id="fixture", at=at,
                ledger=dict(schema_version="account-ledger-0.1", scope_id="fixture", accounts=["A", "B"],
                            quality="synthetic_fixture", events=events), snapshots=rows,
                fx=dict(evidence, pair="KRW_per_USD", rate="1000", observed_at=at,
                        available_at=at, max_age_seconds=0))


class NavTest(unittest.TestCase):
    def test_value_conserved_across_transfer_boundaries(self):
        for day, adjustment in [(1, "0"), (2, "2"), (3, "0")]:
            out = value(fixture(day))
            self.assertEqual(out["transit_adjustment"]["USD"], adjustment)
            self.assertEqual(out["nav"], {"KRW": "11000", "USD": "11"})

    def test_receivable_in_snapshot(self):
        data = fixture()
        data["snapshots"][0].update(net_by_currency={"USD": "10"}, booked_transit={"T": "2"})
        out = value(data)
        self.assertEqual(out["nav"]["KRW"], "11000")
        self.assertEqual(out["already_booked"], ["T"])
        data["snapshots"][1]["booked_transit"] = {"T": "2"}
        self.assertEqual(value(data)["reason"], "UNKNOWN_OR_DUPLICATE_RECEIVABLE")

    def test_inactive_or_partial_receivable(self):
        for day, amount in [(3, "2"), (2, "1")]:
            data = fixture(day)
            data["snapshots"][0]["booked_transit"] = {"T": amount}
            self.assertEqual(value(data)["status"], "BLOCKED")

    def test_fx_changes_valuation(self):
        data = fixture()
        data["fx"]["rate"] = "1250"
        out = value(data)
        self.assertEqual(out["nav"], {"KRW": "13500", "USD": "10.8"})
        self.assertEqual(out["net_by_currency"], {"KRW": "1000", "USD": "10"})

    def test_missing_duplicate_or_stale_snapshot(self):
        for mode in ["missing", "duplicate", "old"]:
            data = fixture()
            if mode == "missing":
                data["snapshots"].pop()
            elif mode == "duplicate":
                data["snapshots"].append(data["snapshots"][0])
            else:
                data["snapshots"][0]["at"] = "2025-01-01T00:00:00Z"
            self.assertNotIn("nav", value(data))

    def test_timezone_and_quality(self):
        data = fixture()
        data["snapshots"][0]["at"] = "2025-01-02T09:00:00+09:00"
        data["fx"]["quality"] = "actual_observed"
        self.assertEqual(value(data)["quality"], "synthetic_fixture")

    def test_fx_validation(self):
        for change in [dict(rate="0"), dict(rate=True), dict(pair="USD_per_KRW"),
                       dict(observed_at="2025-01-01T00:00:00Z"),
                       dict(available_at="2025-01-03T00:00:00Z"), dict(source_ref="")]:
            data = fixture()
            data["fx"].update(change)
            self.assertEqual(value(data)["status"], "BLOCKED", change)

    def test_incomplete_ledger_or_scope(self):
        data = fixture()
        changed = copy.deepcopy(data)
        changed["ledger"]["events"].pop()
        self.assertEqual(value(changed)["status"], "BLOCKED")
        data["scope_id"] = "different"
        self.assertEqual(value(data)["reason"], "SCOPE_MISMATCH")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"fixture.json"
            for payload, code in [(fixture(), 0), ({}, 2)]:
                path.write_text(json.dumps(payload))
                result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                                         "portfolio_nav.py"), "--input", str(path)], capture_output=True)
                self.assertEqual(result.returncode, code)
                self.assertIn("status", json.loads(result.stdout))
