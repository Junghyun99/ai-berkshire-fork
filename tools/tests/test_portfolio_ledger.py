import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_cashflow import calculate
from portfolio_ledger import normalize


def event(account, kind, amount, at="2025-01-02T00:00:00Z", **extra):
    return dict(account=account, id="local-1", kind=kind, amount=amount, at=at,
                source_ref="fixture", status="actual", currency="KRW") | extra


def pair():
    return [event("ISA", "transfer_out", "-20", transfer_id="T", counterparty="pension"),
            event("pension", "transfer_in", "20", "2025-01-03T09:00:00+09:00",
                  transfer_id="T", counterparty="ISA")]


def document(*rows):
    return dict(schema_version="account-ledger-0.1", accounts=["ISA", "pension", "general"],
                quality="synthetic_fixture", scope_id="s1", events=list(rows))


class LedgerTest(unittest.TestCase):
    def test_transfer_with_fee_and_external_deposit_enters_core(self):
        rows = pair() + [event("general", "deposit", "100", counterparty="external"),
                         event("ISA", "fee", "-1", id="fee")]
        out = normalize(document(*rows))
        self.assertEqual(len(out["external_flows"]["KRW"]), 1)
        transfer = out["transfers"][0]
        self.assertEqual((transfer["principal"], transfer["in_transit_from"], transfer["received_at"]),
                         ("20", "2025-01-02T00:00:00+00:00", "2025-01-03T00:00:00+00:00"))
        data = dict(schema_version="cashflow-core-0.1", scope_id="s1", source_ref="fixture",
                    quality="synthetic_fixture", currency="KRW", method="dietz",
                    start=dict(at="2025-01-01T00:00:00Z", nav="100"),
                    end=dict(at="2025-01-03T00:00:00Z", nav="199"),
                    flows=out["external_flows"]["KRW"])
        self.assertAlmostEqual(float(calculate(data)["metrics"]["dietz"]), -1/150)

    def test_currency_partition_and_income(self):
        rows = [event("ISA", "withdrawal", "-10", counterparty="external"),
                event("general", "deposit", "3", currency="USD", counterparty="external"),
                event("pension", "interest", "1"), event("ISA", "tax", "-1", id="tax")]
        out = normalize(document(*rows))
        self.assertEqual(out["external_flows"]["KRW"][0]["amount"], "-10")
        self.assertEqual(out["external_flows"]["USD"][0]["amount"], "3")
        self.assertEqual(len(out["events"]), 4)

    def test_order_and_retry(self):
        a, b = pair()
        self.assertEqual(normalize(document(b, a, a)), normalize(document(a, b)))
        self.assertEqual(normalize(document(a, b, dict(a, amount="-30")))["reason"], "EVENT_CONFLICT")

    def test_bad_pairs_block_all_outputs(self):
        a, b = pair()
        for rows in ([a], [b], [a, b, dict(b, id="extra")], [a, dict(b, amount="19")],
                     [a, dict(b, currency="USD")], [a, dict(b, counterparty="general")],
                     [a, dict(b, at="2024-12-31T15:00:00Z")]):
            with self.subTest(rows=rows):
                out = normalize(document(event("general", "deposit", "5", counterparty="external"), *rows))
                self.assertEqual(out["status"], "BLOCKED")
                self.assertNotIn("external_flows", out)

    def test_unresolved_or_planned_flow(self):
        deposit = event("general", "deposit", "5", counterparty="external")
        for mod in [dict(counterparty="ISA"), dict(counterparty=None), dict(status="planned"),
                    dict(amount="-5"), dict(amount=True), dict(at="2025-01-01"), dict(source_ref=""),
                    dict(account="unknown"), dict(kind="unknown")]:
            with self.subTest(mod=mod):
                self.assertEqual(normalize(document(deposit | mod))["status"], "BLOCKED")

    def test_precision(self):
        a, b = pair()
        amount = "123456789012345678901234567890123456.78"
        self.assertEqual(normalize(document(dict(a, amount="-"+amount),
                                            dict(b, amount=amount)))["status"], "RESEARCH_ONLY")
        self.assertEqual(normalize(document(dict(a, amount="-"+amount),
                                            dict(b, amount=amount[:-1]+"9")))["reason"],
                         "TRANSFER_AMOUNT_MISMATCH")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"ledger.json"
            for data, expected in [(document(*pair()), 0), (document(pair()[0]), 2)]:
                path.write_text(json.dumps(data))
                result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]
                                         / "portfolio_ledger.py"), "--input", str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertIn("status", json.loads(result.stdout))
