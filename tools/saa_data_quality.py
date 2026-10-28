"""SAA monthly total-return panel validation and descriptive statistics.

Offline, standard-library-only. This does NOT fetch prices or estimate forward
capital-market expectations. Returns and covariance are descriptive only.
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

FIELDS = {"month", "asset_id", "total_return_local", "fx_to_krw_return",
          "source_id", "as_of", "available_at", "quality"}


def load_panel(path, minimum_months=2):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("D01: empty data")
    if not FIELDS.issubset(rows[0]):
        raise ValueError("D01: missing columns")
    values = {}
    by_month = defaultdict(set)
    universe = set()
    for row in rows:
        month = row["month"]
        asset = row["asset_id"].strip()
        if not asset or not month or date.fromisoformat(month + "-01").strftime("%Y-%m") != month:
            raise ValueError("D01: invalid month or asset")
        if row["quality"] != "verified" or not row["source_id"]:
            raise ValueError("D08: unverified or unsourced data")
        observed = date.fromisoformat(row["as_of"])
        available = date.fromisoformat(row["available_at"])
        if observed.strftime("%Y-%m") != month or available < observed:
            raise ValueError("D05: dates inconsistent")
        key = (month, asset)
        if key in values:
            raise ValueError("D01: duplicate month/asset")
        local, fx = float(row["total_return_local"]), float(row["fx_to_krw_return"])
        if not all(math.isfinite(v) and v >= -1 for v in (local, fx)):
            raise ValueError("D02: invalid return")
        values[key] = (1 + local) * (1 + fx) - 1
        by_month[month].add(asset)
        universe.add(asset)
    months = sorted(by_month)
    if len(months) < minimum_months:
        raise ValueError("D07: insufficient sample")
    if any(by_month[m] != universe for m in months):
        raise ValueError("D01: unbalanced monthly panel")
    # Prevent treating missing interior months as continuous observations.
    for previous, current in zip(months, months[1:]):
        y, m = map(int, previous.split("-"))
        expected = f"{y + (m == 12):04d}-{(m % 12) + 1:02d}"
        if current != expected:
            raise ValueError("D01: missing calendar month")
    assets = sorted(universe)
    return months, assets, [[values[(month, asset)] for asset in assets] for month in months]


def statistics(months, assets, panel):
    n = len(months)
    if n < 2:
        raise ValueError("D07: sample covariance needs >=2 months")
    columns = list(zip(*panel))
    mus = [mean(col) for col in columns]
    cov = [[12 * sum((a - mu_a) * (b - mu_b) for a, b in zip(col_a, col_b)) / (n - 1)
            for col_b, mu_b in zip(columns, mus)] for col_a, mu_a in zip(columns, mus)]
    corr = [[(cov[i][j] / math.sqrt(cov[i][i] * cov[j][j])
              if cov[i][i] > 0 and cov[j][j] > 0 else None)
             for j in range(len(assets))] for i in range(len(assets))]
    return {"frequency": "monthly", "currency": "KRW", "months": n, "start": months[0], "end": months[-1],
            "assets": assets, "annualized_arithmetic_historical_mean": dict(zip(assets, [12*x for x in mus])),
            "annualized_sample_covariance": cov, "sample_correlation": corr,
            "note": "Historical descriptive statistics; not forward expected returns."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--min-months", type=int, default=60)
    args = p.parse_args()
    try:
        months, assets, panel = load_panel(args.input, args.min_months)
        print(json.dumps({"status": "PASS", "statistics": statistics(months, assets, panel)}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
