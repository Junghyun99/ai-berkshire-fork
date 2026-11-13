"""Normalize a retrospective account cash ledger and reconcile transfer principal."""
import argparse
from collections import defaultdict
import json

if __package__:
    from .portfolio_cashflow import ContractError, instant, number, require, text_field
else:
    from portfolio_cashflow import ContractError, instant, number, require, text_field


EXTERNAL = "external"
POSITIVE = {"deposit", "transfer_in", "dividend", "interest"}
NEGATIVE = {"withdrawal", "transfer_out", "fee", "tax"}
BASE = {"id", "account", "at", "currency", "amount", "kind", "source_ref", "status"}


def normalize(data):
    """Return complete reconciled results, or BLOCKED with no partial flows."""
    try:
        return _normalize(data)
    except ContractError as error:
        return {"status": "BLOCKED", "reason": str(error)}


def _normalize(data):
    require(isinstance(data, dict) and set(data) == {
        "schema_version", "scope_id", "accounts", "quality", "events"}, "INVALID_DOCUMENT")
    require(data["schema_version"] == "account-ledger-0.1", "INVALID_SCHEMA")
    require(text_field(data["scope_id"]), "MISSING_SCOPE")
    require(data["quality"] in ("actual_observed", "synthetic_fixture", "research_proxy"),
            "INVALID_QUALITY")
    accounts = data["accounts"]
    require(isinstance(accounts, list) and accounts and all(text_field(a) for a in accounts),
            "INVALID_ACCOUNTS")
    require(EXTERNAL not in accounts and len(set(accounts)) == len(accounts), "INVALID_ACCOUNTS")
    require(isinstance(data["events"], list), "INVALID_EVENTS")
    seen, normalized = {}, []
    transfers = defaultdict(list)
    external = defaultdict(list)
    for raw in data["events"]:
        require(isinstance(raw, dict), "INVALID_EVENT")
        kind = raw.get("kind")
        require(isinstance(kind, str) and kind in POSITIVE | NEGATIVE, "INVALID_KIND")
        internal = kind in ("transfer_in", "transfer_out")
        boundary = kind in ("deposit", "withdrawal")
        keys = BASE | ({"counterparty"} if internal or boundary else set())
        require(set(raw) == (keys | {"transfer_id"} if internal else keys), "INVALID_EVENT_FIELDS")
        require(text_field(raw["id"]) and text_field(raw["source_ref"]), "MISSING_ID_OR_SOURCE")
        require(raw["account"] in accounts, "UNKNOWN_ACCOUNT")
        require(raw["status"] == "actual", "UNPOSTED_EVENT")
        require(raw["currency"] in ("KRW", "USD"), "INVALID_CURRENCY")
        amount = number(raw["amount"])
        require(amount > 0 if kind in POSITIVE else amount < 0, "INVALID_SIGN")
        if boundary:
            require(raw["counterparty"] == EXTERNAL, "INVALID_EXTERNAL_BOUNDARY")
        if internal:
            require(text_field(raw["transfer_id"]), "MISSING_TRANSFER_ID")
            require(raw["counterparty"] in accounts and raw["counterparty"] != raw["account"],
                    "INVALID_COUNTERPARTY")
        row = dict(raw, at=instant(raw["at"], False).isoformat(), amount=format(amount, "f"))
        key = (row["account"], row["id"])
        if key in seen:
            require(seen[key] == row, "EVENT_CONFLICT")
            continue
        seen[key] = row
        normalized.append(row)
        if internal:
            transfers[row["transfer_id"]].append(row)
        if boundary:
            # Structured encoding keeps local event IDs distinct across accounts.
            external[row["currency"]].append({
                "id": json.dumps(key, ensure_ascii=False, separators=(",", ":")),
                "at": row["at"], "amount": row["amount"],
                "kind": "external_deposit" if kind == "deposit" else "external_withdrawal"})
    intervals = [_reconcile(key, transfers[key]) for key in sorted(transfers)]
    return {"status": "RESEARCH_ONLY", "scope_id": data["scope_id"], "quality": data["quality"],
            "accounts": sorted(accounts), "evidence_authenticated": False,
            "events": sorted(normalized, key=lambda e: (e["at"], e["account"], e["id"])),
            "external_flows": {c: sorted(rows, key=lambda e: (e["at"], e["id"]))
                               for c, rows in sorted(external.items())},
            "transfers": intervals}


def _reconcile(identity, legs):
    require(len(legs) == 2 and {r["kind"] for r in legs} == {"transfer_in", "transfer_out"},
            "TRANSFER_LEGS_INCOMPLETE_OR_DUPLICATE")
    sent, received = sorted(legs, key=lambda r: r["kind"] != "transfer_out")
    require(sent["counterparty"] == received["account"] and received["counterparty"] == sent["account"],
            "TRANSFER_ACCOUNTS_MISMATCH")
    require(sent["currency"] == received["currency"], "TRANSFER_REQUIRES_FX")
    require(number(sent["amount"]).copy_abs() == number(received["amount"]), "TRANSFER_AMOUNT_MISMATCH")
    require(instant(sent["at"], False) <= instant(received["at"], False), "TRANSFER_TIME_ORDER")
    return {"transfer_id": identity, "from_account": sent["account"], "to_account": received["account"],
            "out_event_id": sent["id"], "in_event_id": received["id"], "currency": sent["currency"],
            "principal": received["amount"], "in_transit_from": sent["at"],
            "received_at": received["at"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as handle:
            result = normalize(json.load(handle))
    except (OSError, ValueError):
        result = {"status": "BLOCKED", "reason": "INPUT_READ_ERROR"}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
