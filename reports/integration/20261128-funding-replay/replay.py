"""동일 신규 후보의 추가 3% 편입을 어떤 기존 종목에서 조달할지 비교한다."""
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TICKERS = ("AAPL", "MSFT", "NVDA", "GOOGL", "META")
GROUP = dict.fromkeys(TICKERS[:3], "Technology") | dict.fromkeys(TICKERS[3:], "Communication Services")


def read(path):
    with (ROOT / path).open() as f:
        return list(csv.DictReader(f))


def cost_adjusted_spread(new_return, sold_returns, fee):
    if not sold_returns:
        return 0.0
    return 3 * (new_return - st.mean(sold_returns) - 2 * fee)


def evaluate(start, end, donors, fee):
    gains = {t: end[t] / start[t] - 1 for t in TICKERS}
    return {n: {rule: cost_adjusted_spread(gains[n], [gains[t] for t in sales], fee)
                for rule, sales in rules.items()} for n, rules in donors.items()}


def rules_for(n):
    old = [t for t in TICKERS if t != n]
    return {"cash": [], "proportional": old, "sector": [t for t in old if GROUP[t] == GROUP[n]],
            "ad_demand": [t for t in old if {n, t} == {"GOOGL", "META"}]}


def weekly(horizon=26, offset=0, fee=0.0025):
    rows = read("data/cross_asset_10y_2016-2026.csv")
    assert all(a["date"] < b["date"] for a, b in zip(rows, rows[1:]))
    prices = [{t: float(r[t]) for t in TICKERS} for r in rows]
    assert all(p > 0 for row in prices for p in row.values())
    periods = []
    for i in range(53 + offset, len(rows) - horizon, horizon):
        history = {t: [prices[k][t] / prices[k-1][t] - 1 for k in range(i-52, i)]
                   for t in TICKERS}
        donors = {n: rules_for(n) for n in TICKERS}
        for n, rules in donors.items():
            rules["correlation"] = [max(rules["proportional"],
                                        key=lambda t: st.correlation(history[t], history[n]))]
        effects = evaluate(prices[i], prices[i+horizon], donors, fee)
        periods.append((rows[i]["date"], rows[i+horizon]["date"], effects))
    return periods


def valuation(fee=0.0025):
    snapshot = {r["ticker"]: r for r in read("data/morningstar_fair_value_20260519.csv")}
    start = {t: float(snapshot[t]["close_price"]) for t in TICKERS}
    end = {r["티커"]: float(r["기록시점가"]) for r in read("reports/decision-ledger.csv")
           if r["티커"] in TICKERS and r["기록일"] == "2026-11-20" and r["스킬"] == "investment-team"}
    ratios = {t: float(snapshot[t]["fair_value"]) / start[t] for t in TICKERS}
    donors = {n: rules_for(n) for n in TICKERS}
    for n, rules in donors.items():
        lowest = min(rules["proportional"], key=ratios.get)
        rules["overvalued"] = [lowest] if ratios[lowest] < 1 else []
        rules["relative_value"] = [lowest] if ratios[n] > ratios[lowest] else []
    return donors, evaluate(start, end, donors, fee)


if __name__ == "__main__":
    for horizon, offset in [(26, 0), (26, 13), (13, 0), (52, 0)]:
        periods = weekly(horizon, offset)
        print("horizon, offset, windows, first, last:", horizon, offset, len(periods), periods[0][0], periods[-1][1])
        for method in ("proportional", "sector", "correlation"):
            effects = [st.mean(case[method] for case in window.values()) for _, _, window in periods]
            print(method, round(st.mean(effects), 4), sum(x > 0 for x in effects), "positive windows")
        if (horizon, offset) == (26, 0):
            for n in TICKERS:
                print(n, [round(st.mean(w[n][m] for _, _, w in periods), 4)
                          for m in ("proportional", "sector", "correlation")])
    donors, scores = valuation()
    for n in TICKERS:
        print(n, donors[n]["overvalued"], {k: round(v, 4) for k, v in scores[n].items()})
