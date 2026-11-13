"""Consolidate retrospective KRW/USD account valuations and matched transfers."""
import argparse
import json
from decimal import Decimal, localcontext

if __package__:
    from .portfolio_cashflow import ContractError, instant, number, require, text_field
    from .portfolio_ledger import normalize
else:
    from portfolio_cashflow import ContractError, instant, number, require, text_field
    from portfolio_ledger import normalize


CURRENCIES = ("KRW", "USD")
QUALITIES = ("actual_observed", "research_proxy", "synthetic_fixture")


def fields(row, keys):
    require(isinstance(row, dict) and set(row) == set(keys.split()), "INVALID_FIELDS")


def evidence(row):
    require(text_field(row["source_ref"]), "MISSING_SOURCE")
    require(row["quality"] in QUALITIES, "INVALID_QUALITY")


def fx_rate(quote, at):
    fields(quote, "pair rate observed_at available_at max_age_seconds source_ref quality")
    evidence(quote)
    require(quote["pair"] == "KRW_per_USD", "INVALID_FX_DIRECTION")
    rate = number(quote["rate"])
    require(rate > 0, "INVALID_FX_RATE")
    observed = instant(quote["observed_at"], False)
    available = instant(quote["available_at"], False)
    require(observed <= available <= at, "FX_TIME_MISMATCH")
    limit = quote["max_age_seconds"]
    require(type(limit) is int and limit >= 0, "INVALID_MAX_AGE")
    require((at - observed).total_seconds() <= limit, "STALE_FX")
    return rate


def reconcile_accounts(rows, accounts, active, at):
    require(isinstance(rows, list), "INVALID_SNAPSHOTS")
    seen, booked, sources = set(), set(), {}
    totals = dict.fromkeys(CURRENCIES, Decimal(0))
    for row in rows:
        fields(row, "account at net_by_currency booked_transit source_ref quality")
        evidence(row)
        account = row["account"]
        require(text_field(account) and account in accounts and account not in seen,
                "UNKNOWN_OR_DUPLICATE_ACCOUNT")
        seen.add(account)
        sources[account] = row["source_ref"]
        require(instant(row["at"], False) == at, "SNAPSHOT_TIME_MISMATCH")
        net = row["net_by_currency"]
        require(isinstance(net, dict) and net and set(net) <= set(CURRENCIES), "INVALID_NET")
        for currency, value in net.items():
            totals[currency] += number(value)
        entries = row["booked_transit"]
        require(isinstance(entries, dict), "INVALID_BOOKED_TRANSIT")
        for key, amount in entries.items():
            require(key in active and key not in booked, "UNKNOWN_OR_DUPLICATE_RECEIVABLE")
            transfer = active[key]
            require(account in (transfer["from_account"], transfer["to_account"])
                    and transfer["currency"] in net, "RECEIVABLE_SCOPE_MISMATCH")
            require(number(amount) == number(transfer["principal"]), "RECEIVABLE_AMOUNT_MISMATCH")
            booked.add(key)
    require(seen == set(accounts), "MISSING_ACCOUNT")
    return totals, booked, sources


def _value(data):
    fields(data, "schema_version scope_id at ledger snapshots fx")
    require(data["schema_version"] == "portfolio-nav-0.1", "INVALID_SCHEMA")
    at = instant(data["at"], False)
    ledger = normalize(data["ledger"])
    require(ledger["status"] == "RESEARCH_ONLY", ledger.get("reason", "INVALID_LEDGER"))
    require(data["scope_id"] == ledger["scope_id"], "SCOPE_MISMATCH")
    active = {t["transfer_id"]: t for t in ledger["transfers"]
              if instant(t["in_transit_from"], False) <= at < instant(t["received_at"], False)}
    rate = fx_rate(data["fx"], at)
    totals, booked, sources = reconcile_accounts(data["snapshots"], ledger["accounts"], active, at)
    adjustments = dict.fromkeys(CURRENCIES, Decimal(0))
    for key, transfer in active.items():
        if key not in booked:
            adjustments[transfer["currency"]] += number(transfer["principal"])
    native = {c: totals[c] + adjustments[c] for c in CURRENCIES}
    krw = native["KRW"] + native["USD"] * rate
    with localcontext() as division:
        division.prec = 34
        usd = krw / rate
    qualities = [ledger["quality"], data["fx"]["quality"]] + [r["quality"] for r in data["snapshots"]]
    def strings(values):
        return {c: format(x, "f") for c, x in values.items()}
    return {"status": "RESEARCH_ONLY", "scope_id": ledger["scope_id"], "at": at.isoformat(),
            "quality": max(qualities, key=QUALITIES.index), "evidence_authenticated": False,
            "account_net": strings(totals), "transit_adjustment": strings(adjustments),
            "active_transfers": sorted(active), "already_booked": sorted(booked),
            "net_by_currency": strings(native), "nav": strings({"KRW": krw, "USD": usd}),
            "snapshot_sources": sources, "fx": dict(data["fx"])}


def value(data):
    try:
        with localcontext() as ctx:
            ctx.prec = 600
            return _value(data)
    except ContractError as error:
        return {"status": "BLOCKED", "reason": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as handle:
            result = value(json.load(handle))
    except (OSError, ValueError):
        result = {"status": "BLOCKED", "reason": "INPUT_READ_ERROR"}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
