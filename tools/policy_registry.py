"""Local append-only IPS version registry (stdlib). No order execution.

MVP: single-writer filesystem; does not authenticate human identity or guarantee
transactional consistency under concurrent processes. Do not use as a live
order authorization service.
"""
import argparse
import hashlib
import json
from pathlib import Path

from policy_validator import check_policy


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def register(draft, event, directory):
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
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    archive = root / ("policy-" + version + ".json")
    # Exclusive write prevents overwriting a previously archived version.
    with archive.open("x", encoding="utf-8") as f:
        json.dump(policy, f, ensure_ascii=False, indent=2)
    with (root / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    tmp = root / "active.json.tmp"
    tmp.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(root / "active.json")
    return policy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("register", "show"))
    ap.add_argument("--registry", required=True)
    ap.add_argument("--policy")
    ap.add_argument("--approval-event")
    args = ap.parse_args()
    if args.action == "show":
        print((Path(args.registry) / "active.json").read_text(encoding="utf-8"))
        return
    if not args.policy or not args.approval_event:
        ap.error("register requires --policy and --approval-event")
    with open(args.policy, encoding="utf-8") as f:
        draft = json.load(f)
    with open(args.approval_event, encoding="utf-8") as f:
        event = json.load(f)
    result = register(draft, event, args.registry)
    print(json.dumps({"registered": True, "version": result["version"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
