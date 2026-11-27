"""고정 표본의 초기 비중과 완전한 일별 총수익지수 패널의 성과를 계산한다."""
import argparse
import csv
import math
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

START = date(2026, 11, 30)
COHORT = Path(__file__).with_name("cohort.csv")


def weights(rows, field):
    groups = {r["ticker"]: r[field] for r in rows}
    counts = Counter(groups.values())
    return {t: 1 / (len(counts) * counts[g]) for t, g in groups.items()}


def evaluate(nav, years):
    changes = [v / u - 1 for u, v in zip(nav, nav[1:])]
    peak = nav[0]
    mdd = 0
    for v in nav:
        peak = max(v, peak)
        mdd = min(mdd, v / peak - 1)
    vol = statistics.stdev(changes)
    downside = math.sqrt(statistics.mean(min(0, x) ** 2 for x in changes))
    annual = statistics.mean(changes) * math.sqrt(252)
    return (nav[-1] ** (1 / years) - 1, mdd,
            annual / vol if vol else None, annual / downside if downside else None)


def compare(panel, portfolios):
    tickers = set(portfolios["ticker"])
    with panel.open() as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if len(columns) != len(tickers) + 1 or set(columns) != tickers | {"date"}:
            raise ValueError("date와 고정 표본 44개 티커가 필요합니다")
        dates, observations = [], []
        for row in reader:
            day = date.fromisoformat(row["date"])
            if day.weekday() >= 5 or (dates and day <= dates[-1]):
                raise ValueError("거래일 순서를 확인하세요")
            prices = {t: float(row[t]) for t in tickers}
            if not all(math.isfinite(x) and x > 0 for x in prices.values()):
                raise ValueError("결측 또는 비정상 총수익지수")
            dates.append(day)
            observations.append(prices)
    if len(dates) < 3 or dates[0] != START:
        raise ValueError("11월 30일 종가와 이후 최소 두 거래일이 필요합니다")
    years = (dates[-1] - dates[0]).days / 365.2425
    for label, allocation in portfolios.items():
        nav = [sum(w * p[t] / observations[0][t] for t, w in allocation.items())
               for p in observations]
        print(label, dict(zip(("CAGR", "MDD", "Sharpe", "Sortino"), evaluate(nav, years))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path)
    args = parser.parse_args()
    with COHORT.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len({r["ticker"] for r in rows}) == 44
    portfolios = {field: weights(rows, field) for field in ("ticker", "sector", "group")}
    chips = [r["ticker"] for r in rows if r["group"] == "Semiconductors and equipment"]
    for name, allocation in portfolios.items():
        assert math.isclose(sum(allocation.values()), 1)
        print(name, "반도체 합계", sum(allocation[t] for t in chips),
              "단일종목 최대", max(allocation.values()))
    if args.panel:
        compare(args.panel, portfolios)
