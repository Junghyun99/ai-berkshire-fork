"""Fail-closed investment policy and proposal validation (stdlib only)."""
import argparse
import json
from decimal import Decimal, InvalidOperation


def num(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing number")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid number")
    if not v.is_finite():
        raise ValueError("non-finite number")
    return v


def check_policy(p):
    errors = []
    if not isinstance(p, dict):
        return ["G00: policy object required"]
    required = ("policy_id", "version", "owner", "base_currency", "investment_horizon",
                "objective", "benchmark", "eligible_assets", "prohibited_assets",
                "strategic_targets", "allocation_bands", "risk_limits", "rebalance_policy",
                "approval_rules", "risk_capacity", "risk_willingness", "cash_flow_needs",
                "approved_by", "approved_at", "effective_at")
    for key in required:
        if p.get(key) is None or p.get(key) in ("", "TBD"):
            errors.append("G01: missing " + key)
    if p.get("status") != "active":
        errors.append("G09: policy not active")
    allowed, banned = p.get("eligible_assets"), p.get("prohibited_assets")
    if not isinstance(allowed, list) or not allowed or not isinstance(banned, list):
        errors.append("G05: asset lists invalid")
    elif set(allowed) & set(banned):
        errors.append("G05: allowed/prohibited assets overlap")
    targets, bands = p.get("strategic_targets"), p.get("allocation_bands")
    if not isinstance(targets, dict) or not targets:
        errors.append("G06: targets missing")
    else:
        try:
            if sum((num(v) for v in targets.values()), Decimal(0)) != 100:
                errors.append("G06: allocation must total 100")
            if not isinstance(bands, dict) or set(bands) != set(targets):
                errors.append("G06: bands must match targets")
            else:
                for k, value in targets.items():
                    b = bands[k]
                    if not 0 <= num(b["min"]) <= num(value) <= num(b["max"]) <= 100:
                        errors.append("G06: invalid band " + k)
        except (ValueError, KeyError, TypeError):
            errors.append("G06: invalid allocation numbers")
    limits = p.get("risk_limits")
    if not isinstance(limits, dict) or limits.get("weight_basis") != "total_portfolio":
        errors.append("G07: risk weight denominator required")
    else:
        try:
            if not 0 <= num(limits["single_name_max_pct"]) <= 100:
                errors.append("G04: bad single-name limit")
        except (KeyError, ValueError):
            errors.append("G04: missing/invalid single-name limit")
    if not isinstance(p.get("approval_rules"), dict) or p["approval_rules"].get("owner_approval_required") is not True:
        errors.append("G09: owner approval rule missing")
    if not isinstance(p.get("cash_flow_needs"), (dict, list)):
        errors.append("G03: structured cashflow required")
    review = p.get("feasibility_review")
    if not isinstance(review, dict) or review.get("result") != "pass" or not review.get("reviewer") or not review.get("reason"):
        errors.append("G12: documented human feasibility review required")
    return errors


def check_proposal(policy, portfolio, proposal):
    errors = check_policy(policy)
    if not isinstance(portfolio, dict) or not isinstance(proposal, dict):
        return errors + ["P00: portfolio/proposal object required"]
    for key in ("snapshot_id", "policy_id", "policy_version", "net_asset_value", "base_currency"):
        if portfolio.get(key) is None:
            errors.append("P01: missing portfolio " + key)
    for key in ("proposal_id", "portfolio_snapshot_id", "policy_id", "policy_version",
                "proposed_weight", "weight_basis", "policy_checks"):
        if proposal.get(key) is None:
            errors.append("P02: missing proposal " + key)
    if (portfolio.get("policy_id"), portfolio.get("policy_version")) != (policy.get("policy_id"), policy.get("version")) or (proposal.get("policy_id"), proposal.get("policy_version")) != (policy.get("policy_id"), policy.get("version")):
        errors.append("P03: policy version mismatch")
    if portfolio.get("snapshot_id") != proposal.get("portfolio_snapshot_id"):
        errors.append("P04: snapshot mismatch")
    if portfolio.get("base_currency") != policy.get("base_currency"):
        errors.append("P05: currency mismatch")
    if proposal.get("weight_basis") != "total_portfolio":
        errors.append("P06: unsupported weight denominator")
    try:
        weight = num(proposal.get("proposed_weight"))
        limit = num(policy["risk_limits"]["single_name_max_pct"])
        if not 0 <= weight <= 100:
            errors.append("P07: invalid percentage")
        if weight > limit:
            errors.append("P08: concentration limit exceeded")
        if num(portfolio.get("net_asset_value")) <= 0:
            errors.append("P09: NAV must be positive")
    except (ValueError, KeyError, TypeError):
        errors.append("P07: invalid numeric input")
    checks = proposal.get("policy_checks")
    if not isinstance(checks, dict) or not checks or any(v != "pass" for v in checks.values()):
        errors.append("P10: failed or unknown policy check")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=("policy", "proposal"))
    ap.add_argument("--policy", required=True)
    ap.add_argument("--portfolio")
    ap.add_argument("--proposal")
    a = ap.parse_args()
    with open(a.policy, encoding="utf-8") as f:
        p = json.load(f)
    if a.kind == "policy":
        errors = check_policy(p)
    else:
        if not a.portfolio or not a.proposal:
            ap.error("proposal requires --portfolio and --proposal")
        with open(a.portfolio, encoding="utf-8") as f:
            portfolio = json.load(f)
        with open(a.proposal, encoding="utf-8") as f:
            proposal = json.load(f)
        errors = check_proposal(p, portfolio, proposal)
    print(json.dumps({"result": "BLOCKED" if errors else "PASS", "errors": errors}, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
