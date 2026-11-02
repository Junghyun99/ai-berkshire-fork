"""Research-only IPS registry. Human authentication and operational activation unavailable."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from policy_validator import check_policy
from policy_registry_store import persist, inspect_registry


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def register(draft, event, directory, *, research_only=False):
    if research_only is not True:
        raise ValueError("authenticated approval unavailable; explicit research_only=True required")
    draft, event = copy.deepcopy(draft), copy.deepcopy(event)
    if not isinstance(draft, dict) or not isinstance(event, dict):
        raise ValueError("draft and approval event must be objects")
    if draft.get("status") != "draft":
        raise ValueError("only DRAFT may be registered")
    if event.get("event_type") != "POLICY_APPROVED" or event.get("actor_type") != "user":
        raise ValueError("explicit user approval event required")
    if event.get("policy_id") != draft.get("policy_id") or event.get("version") != draft.get("version"):
        raise ValueError("approval policy/version mismatch")
    if event.get("actor_id") != draft.get("owner") or not event.get("approved_at"):
        raise ValueError("approval actor/time mismatch")
    if event.get("document_hash") != digest(draft):
        raise ValueError("document changed after approval")
    policy = dict(draft)
    policy["status"] = "active"
    policy["approved_by"] = event["actor_id"]
    policy["approved_at"] = event["approved_at"]
    errors = check_policy(policy)
    if errors:
        raise ValueError("policy invalid: " + "; ".join(errors))
    version = policy["version"]
    if not isinstance(version, str) or not version or not all(c.isalnum() or c in "._-" for c in version):
        raise ValueError("unsafe version")
    policy.update(status="research_active", approval_authenticated=False,
                  operational_use_allowed=False)
    return persist(draft, event, policy, directory)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("register", "show", "audit", "recover"))
    ap.add_argument("--registry", required=True)
    ap.add_argument("--policy")
    ap.add_argument("--approval-event")
    ap.add_argument("--research-only", action="store_true")
    args = ap.parse_args()
    if args.action in ("show", "audit", "recover"):
        result = inspect_registry(args.registry, repair=args.action == "recover")
        if args.action == "show":
            if result["projection_errors"]:
                raise ValueError("projection mismatch; audit and recover first")
            result = result["current"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not args.policy or not args.approval_event:
        ap.error("register requires --policy and --approval-event")
    with open(args.policy, encoding="utf-8") as f:
        draft = json.load(f)
    with open(args.approval_event, encoding="utf-8") as f:
        event = json.load(f)
    result = register(draft, event, args.registry, research_only=args.research_only)
    print(json.dumps({"registered": True, "mode": "research_only", "approval_authenticated": False, "version": result["version"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
