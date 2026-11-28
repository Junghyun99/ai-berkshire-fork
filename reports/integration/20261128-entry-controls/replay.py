"""Compare one earmarked tranche per report over its frozen five sessions."""
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "20261128-first-five"
VERIFIED = {"ADBE", "017670"}
UNRESOLVED = {"035420", "014680"}


def read(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def pct(value, cost):
    return round(100 * (Decimal(value) / Decimal(cost) - 1), 4)


def eligible_entry(bars, level):
    for signal, following in zip(bars, bars[1:]):
        if Decimal(signal["close"]) <= level and Decimal(following["open"]) <= level:
            return following
    return None


def replay():
    by_ticker = defaultdict(list)
    for bar in read(SOURCE / "bars.csv"):
        by_ticker[bar["ticker"]].append(bar)
    output = []
    for decision in read(SOURCE / "results.csv"):
        if not decision["first_level"]:
            continue
        ticker = decision["id"].split("-")[3]
        bars = by_ticker[ticker]
        assert len(bars) == 5 and bars[0]["date"] == decision["start"]
        assert bars[-1]["date"] == decision["fifth"]
        level = Decimal(decision["first_level"])
        reachable = eligible_entry(bars, level)
        entry = reachable if ticker in VERIFIED else None
        end = Decimal(bars[-1]["close"])
        initial = bars[0]["open"]
        row = dict(id=decision["id"], initial_open=initial, final_close=end,
                   conditional_date=entry["date"] if entry else "",
                   conditional_open=entry["open"] if entry else "",
                   immediate_price_pct=pct(end, initial),
                   conditional_price_pct=pct(end, entry["open"]) if entry else 0,
                   cash_pct=0, immediate_with_dividend_pct="", conditional_with_dividend_pct="",
                   unresolved_if_cleared_pct="")
        if ticker in VERIFIED | UNRESOLVED:
            ex_date = "2026-11-27"
            immediate_dividend = 830 if ticker == "017670" and bars[0]["date"] < ex_date <= bars[-1]["date"] else 0
            conditional_dividend = immediate_dividend if entry and entry["date"] < ex_date else 0
            row["immediate_with_dividend_pct"] = pct(end + immediate_dividend, initial)
            row["conditional_with_dividend_pct"] = pct(end + conditional_dividend, entry["open"]) if entry else 0
        if ticker in UNRESOLVED:
            row["unresolved_if_cleared_pct"] = pct(end, reachable["open"]) if reachable else 0
        output.append(row)
    assert len(output) == 23
    with (HERE / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)


if __name__ == "__main__":
    replay()
