#!/usr/bin/env python3
"""Research arithmetic on a pre-consolidated, single-currency portfolio.

This is not an account ledger, provenance authenticator, or trading engine.
See research/phase2-4-cashflow-core.md for the deliberately narrower input.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
import math
import re


class ContractError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ContractError(code)


def number(value):
    require(isinstance(value, str) and len(value) <= 128
            and re.fullmatch(r"-?\d+(?:\.\d+)?", value) is not None,
            "INVALID_DECIMAL")
    result = Decimal(value)
    require(result.is_finite(), "INVALID_DECIMAL")
    return result


def instant(value, daily):
    require(isinstance(value, str), "INVALID_TIME")
    try:
        if daily:
            require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
                    "INVALID_DATE")
            return date.fromisoformat(value)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None and result.utcoffset() is not None,
                "TIMEZONE_REQUIRED")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("INVALID_TIME") from exc


def text_field(value):
    return isinstance(value, str) and bool(value.strip())


def parse(payload):
    require(isinstance(payload, dict), "INVALID_INPUT")
    require(payload.get("schema_version") == "cashflow-core-0.1", "INVALID_SCHEMA")
    require(set(payload) <= {"schema_version", "method", "currency", "scope_id",
                             "source_ref", "quality", "date_basis", "start", "end", "flows"},
            "UNSUPPORTED_FIELD")
    method = payload.get("method")
    require(method in ("twr", "dietz", "mwr"), "INVALID_METHOD")
    require(payload.get("currency") in ("KRW", "USD"), "INVALID_CURRENCY")
    require(text_field(payload.get("scope_id")), "MISSING_SCOPE")
    require(text_field(payload.get("source_ref")), "MISSING_SOURCE_REF")
    require(payload.get("quality") in ("actual_observed", "research_proxy", "synthetic_fixture"),
            "INVALID_QUALITY")
    if method == "mwr":
        require(text_field(payload.get("date_basis")), "MISSING_DATE_BASIS")
    points = []
    for key in ("start", "end"):
        item = payload.get(key)
        require(isinstance(item, dict), "INVALID_BOUNDARY")
        require(set(item) <= {"at", "nav"}, "UNSUPPORTED_FIELD")
        points.append((instant(item.get("at"), method == "mwr"), number(item.get("nav"))))
    (start, initial), (end, final) = points
    require(start < end, "INVALID_PERIOD")
    require(initial > 0 and final >= 0, "INVALID_NAV")
    records = payload.get("flows")
    require(isinstance(records, list), "INVALID_FLOWS")
    seen, flows, times = {}, [], set()
    for item in records:
        require(isinstance(item, dict), "INVALID_FLOW")
        allowed = {"id", "at", "amount", "kind"}
        if method == "twr":
            allowed |= {"before", "after"}
        require(set(item) <= allowed, "UNSUPPORTED_FIELD")
        identity = item.get("id")
        require(text_field(identity), "MISSING_EVENT_ID")
        if identity in seen:
            require(item == seen[identity], "DUPLICATE_CONFLICT")
            continue
        seen[identity] = item
        at = instant(item.get("at"), method == "mwr")
        amount = number(item.get("amount"))
        kind = item.get("kind")
        require((kind == "external_deposit" and amount > 0)
                or (kind == "external_withdrawal" and amount < 0), "INVALID_FLOW_KIND_OR_SIGN")
        require(start < at <= end, "FLOW_OUTSIDE_PERIOD")
        if method != "mwr":
            require(at not in times, "SIMULTANEOUS_FLOW_UNSUPPORTED")
        times.add(at)
        row = {"at": at, "amount": amount}
        if method == "twr":
            before, after = number(item.get("before")), number(item.get("after"))
            require(before >= 0 and after >= 0, "INVALID_NAV")
            require(before + amount == after, "FLOW_NAV_MISMATCH")
            require(at == end or after > 0, "SEGMENT_ENDED")
            row.update(before=before, after=after)
        flows.append(row)
    flows.sort(key=lambda row: row["at"])
    return method, start, end, initial, final, flows


def exact_twr(start, end, initial, final, flows):
    wealth, previous = Decimal(1), initial
    for row in flows:
        require(previous > 0, "SEGMENT_ENDED")
        require(row["before"] > 0 or row["at"] == end, "SEGMENT_ENDED")
        # A market wipeout followed by a deposit cannot restart the same segment.
        require(row["before"] > 0 or row["amount"] <= 0, "SEGMENT_ENDED")
        wealth *= row["before"] / previous
        previous = row["after"]
    if flows and flows[-1]["at"] == end:
        require(previous == final, "END_NAV_MISMATCH")
    else:
        require(previous > 0, "SEGMENT_ENDED")
        wealth *= final / previous
    return {"twr": str(wealth - 1), "approximation": False,
            "segment_closed": final == 0}


def dietz(start, end, initial, final, flows):
    def micros(delta):
        return Decimal((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
    duration = micros(end - start)
    total = sum((f["amount"] for f in flows), Decimal(0))
    capital = initial + sum((micros(end - f["at"]) / duration * f["amount"]
                             for f in flows), Decimal(0))
    require(capital > 0, "NONPOSITIVE_DIETZ_DENOMINATOR")
    return {"dietz": str((final - initial - total) / capital), "approximation": True}


def money_weighted(start, end, initial, final, flows):
    grouped = {start: -initial}
    for row in flows:
        grouped[row["at"]] = grouped.get(row["at"], Decimal(0)) - row["amount"]
    grouped[end] = grouped.get(end, Decimal(0)) + final
    entries = [(day, value) for day, value in sorted(grouped.items()) if value]
    signs = [value > 0 for _, value in entries]
    changes = sum(a != b for a, b in zip(signs, signs[1:]))
    require(changes != 0, "NO_SIGN_CHANGE")
    require(changes == 1, "AMBIGUOUS_CASHFLOW_PATTERN")
    scale = max(abs(value) for _, value in entries)
    terms = [((day - start).days / 365, float(value / scale)) for day, value in entries]
    require(all(value != 0 and math.isfinite(value) for _, value in terms), "NUMERIC_RANGE")

    def residual(y):
        # Scaled relative NPV avoids exponent overflow on long horizons.
        exponents = [-years * y for years, _ in terms]
        shift = max(exponents)
        values = [value * math.exp(exponent - shift)
                  for (_, value), exponent in zip(terms, exponents)]
        return math.fsum(values) / math.fsum(abs(value) for value in values)

    low, high = -32.0, 32.0
    fl, fh = residual(low), residual(high)
    require(fl * fh <= 0, "ROOT_NOT_BRACKETED")
    for iteration in range(1, 257):
        mid = (low + high) / 2
        fm = residual(mid)
        if abs(fm) <= 1e-12:
            break
        if fl * fm > 0:
            low, fl = mid, fm
        else:
            high = mid
    else:
        raise ContractError("NOT_CONVERGED")
    annual = math.expm1(mid)
    period = math.expm1(mid * (end - start).days / 365)
    require(math.isfinite(annual) and math.isfinite(period) and annual > -1, "NUMERIC_RANGE")
    return {"annualized_mwr": annual, "period_mwr": period,
            "primary_display": "period_mwr" if (end - start).days < 365 else "annualized_mwr",
            "days": (end - start).days, "day_count": "ACT/365F",
            "solver": {"method": "log_rate_bisection", "log_rate_bracket": [-32, 32],
                       "relative_npv_residual": fm, "tolerance": 1e-12,
                       "iterations": iteration, "max_iterations": 256}}


def calculate(payload):
    """Return a research result or a fail-closed diagnostic; never authorize trades."""
    boundary = {"policy_approval_granted": False, "evidence_authenticated": False,
                "scope": "preconsolidated_single_currency_arithmetic"}
    try:
        # Decimal input is bounded to 128 chars; preserve exact reconciliation sums.
        with localcontext() as ctx:
            ctx.prec = 300
            method, start, end, initial, final, flows = parse(payload)
            functions = {"twr": exact_twr, "dietz": dietz, "mwr": money_weighted}
            metrics = functions[method](start, end, initial, final, flows)
        return {**boundary, "status": "RESEARCH_ONLY", "method": method,
                "currency": payload["currency"], "scope_id": payload["scope_id"],
                "input_quality": payload["quality"], "source_ref": payload["source_ref"],
                "date_basis": payload.get("date_basis") if method == "mwr" else None,
                "unique_flow_count": len(flows), "metrics": metrics}
    except ContractError as exc:
        return {**boundary, "status": "BLOCKED", "reason": str(exc), "metrics": None}
    except (InvalidOperation, OverflowError, ZeroDivisionError):
        return {**boundary, "status": "BLOCKED", "reason": "NUMERIC_RANGE", "metrics": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="cashflow-core-0.1 JSON")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as handle:
            payload = json.load(handle)
        result = calculate(payload)
    except (OSError, ValueError):
        result = {"status": "BLOCKED", "reason": "INPUT_READ_ERROR", "metrics": None}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
