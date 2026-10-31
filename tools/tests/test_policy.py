"""Offline tests for IPS policy validator and local registry."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_validator import check_policy, check_proposal
from policy_registry import register, digest


def example():
    p = {
        "policy_id": "example", "version": "1.0", "status": "active",
        "owner": "user1", "approved_by": "user1",
        "approved_at": "2026-10-28T10:00:00+09:00", "effective_at": "2026-10-28",
        "base_currency": "KRW", "investment_horizon": "10y",
        "objective": "long-term growth", "benchmark": "example",
        "risk_capacity": "moderate", "risk_willingness": "moderate",
        "cash_flow_needs": [], "eligible_assets": ["equity", "cash"],
        "prohibited_assets": ["derivatives"],
        "strategic_targets": {"equity": 70, "cash": 30},
        "allocation_bands": {"equity": {"min": 60, "max": 80},
                             "cash": {"min": 20, "max": 40}},
        "risk_limits": {"single_name_max_pct": 5, "weight_basis": "total_portfolio"},
        "rebalance_policy": {"frequency": "annual"},
        "approval_rules": {"owner_approval_required": True},
        "feasibility_review": {"result": "pass", "reviewer": "user1",
                               "reason": "cash flow and risk reviewed"}
    }
    # Synthetic complete contract; not a user's investment policy or approval.
    p.update(portfolio_ids=["test-portfolio"], policy_scope={"accounts": ["test-account"]},
             asset_rules={"leverage_allowed": False, "derivatives_allowed": False},
             expiry_rule="until_superseded",
             benchmark={"name": "test-index", "currency": "KRW", "evaluation_period": "annual", "return_basis": "total_return"},
             provenance={"policy_id": "example", "policy_version": "1.0", "sources": ["fixture:source"], "approval_ref": "fixture:approval", "revision_ref": "fixture:initial"},
             validation_sources={k: {"status": "available", "evidence_ref": "fixture:"+k, "as_of": "2026-10-28"} for k in ("prices", "fx", "holdings")})
    p["risk_limits"].update(sector_max_pct=25, liquidity_min_pct=10, gross_leverage_max=1,
                            measurement_method="fixture:whole-portfolio", currency="KRW", as_of="2026-10-28")
    p["approval_rules"].update(review_frequency="annual", amendment_rule="new-version-owner-approval")
    p["feasibility_review"].update(actor_type="user", evidence_ref="fixture:review", unresolved_conflicts=[],
                                  policy_id="example", policy_version="1.0", reviewed_at="2026-10-27")
    return p



class TestInvestmentPolicy(unittest.TestCase):
    def setUp(self):
        self.p = example()
        self.portfolio = {"snapshot_id": "s1", "policy_id": "example",
                          "policy_version": "1.0", "net_asset_value": 1000,
                          "base_currency": "KRW"}
        self.proposal = {"proposal_id": "p1", "portfolio_snapshot_id": "s1",
                         "policy_id": "example", "policy_version": "1.0",
                         "proposed_weight": 5, "weight_basis": "total_portfolio",
                         "policy_checks": {"leverage": "pass"}}

    def test_valid_policy(self):
        self.assertEqual(check_policy(self.p), [])

    def test_draft_policy_blocked(self):
        self.p["status"] = "draft"
        self.assertTrue(check_policy(self.p))

    def test_allocation_total(self):
        self.p["strategic_targets"]["cash"] = 20
        self.assertTrue(check_policy(self.p))

    def test_band(self):
        self.p["allocation_bands"]["equity"]["min"] = 80
        self.assertTrue(check_policy(self.p))

    def test_missing_capacity(self):
        del self.p["risk_capacity"]
        self.assertTrue(check_policy(self.p))

    def test_conflicting_assets(self):
        self.p["prohibited_assets"].append("equity")
        self.assertTrue(check_policy(self.p))

    def test_missing_risk_basis(self):
        self.p["risk_limits"].pop("weight_basis")
        self.assertTrue(check_policy(self.p))

    def test_human_feasibility(self):
        self.p.pop("feasibility_review")
        self.assertTrue(check_policy(self.p))

    def test_proposal_within_limit(self):
        self.assertEqual(check_proposal(self.p, self.portfolio, self.proposal), [])

    def test_exceed_policy_limit(self):
        self.proposal["proposed_weight"] = 10
        self.assertTrue(check_proposal(self.p, self.portfolio, self.proposal))

    def test_unknown_check(self):
        self.proposal["policy_checks"]["sector"] = "unknown"
        self.assertTrue(check_proposal(self.p, self.portfolio, self.proposal))

    def test_snapshot_mismatch(self):
        self.portfolio["snapshot_id"] = "changed"
        self.assertTrue(check_proposal(self.p, self.portfolio, self.proposal))

    def test_missing_weight_basis(self):
        del self.proposal["weight_basis"]
        self.assertTrue(check_proposal(self.p, self.portfolio, self.proposal))

    def test_invalid_number(self):
        self.proposal["proposed_weight"] = float("nan")
        self.assertTrue(check_proposal(self.p, self.portfolio, self.proposal))

    def test_missing_approval_event(self):
        draft = copy.deepcopy(self.p)
        draft["status"] = "draft"
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                register(draft, {}, d)

    def test_registry_immutable_archive(self):
        draft = copy.deepcopy(self.p)
        draft.update(status="draft", approved_by=None, approved_at=None)
        event = {"event_type": "POLICY_APPROVED", "actor_type": "user",
                 "actor_id": "user1", "policy_id": "example", "version": "1.0",
                 "approved_at": "2026-10-28T10:00:00+09:00",
                 "document_hash": digest(draft)}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(register(draft, event, d)["status"], "active")
            with self.assertRaises(FileExistsError):
                register(draft, event, d)

    def test_tampered_document(self):
        draft = copy.deepcopy(self.p)
        draft["status"] = "draft"
        event = {"event_type": "POLICY_APPROVED", "actor_type": "user",
                 "actor_id": "user1", "policy_id": "example", "version": "1.0",
                 "approved_at": "2026-10-28T10:00:00+09:00",
                 "document_hash": "invalid"}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                register(draft, event, d)


if __name__ == "__main__":
    unittest.main()
