"""Phase 2-3: deterministic long-only SAA walk-forward research backtester.

Uses validated monthly KRW total-return panel from saa_data_quality.
Candidate-grid APPROXIMATION, not a mathematical optimizer. Research only.
"""
import argparse
import json
import math
import random
from saa_data_quality import load_panel


def candidates(n, seed=17, count=2500):
    if n < 2:
        raise ValueError("need at least two asset classes")
    if n > 12:
        raise ValueError("grid research supports up to 12 assets")
    out = [[1 / n] * n]
    out += [[float(i == j) for i in range(n)] for j in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            for pct in range(1, 10):
                w = [0.] * n
                w[a], w[b] = pct / 10, 1 - pct / 10
                out.append(w)
    rng = random.Random(seed)
    for _ in range(count):
        x = [rng.gammavariate(1, 1) for _ in range(n)]
        s = sum(x)
        out.append([v / s for v in x])
    return out


def model_weights(train, strategy, grid):
    n = len(train[0])
    if strategy == "equal":
        return [1 / n] * n
    cols = list(zip(*train))
    means = [sum(c) / len(c) for c in cols]
    cov = [[sum((a - means[i]) * (b - means[j]) for a, b in zip(cols[i], cols[j])) / (len(train) - 1)
            for j in range(n)] for i in range(n)]
    # 50% diagonal covariance shrinkage as an explicit heuristic,
    # NOT a fitted Ledoit-Wolf estimator or a formal robust bound.
    shrunk = [[(cov[i][j] + (cov[i][i] if i == j else 0)) / 2 for j in range(n)] for i in range(n)]
    matrix = shrunk if strategy == "shrink_minvar" else cov

    def variance(w):
        return max(0., sum(w[i] * matrix[i][j] * w[j] for i in range(n) for j in range(n)))

    def score(w):
        v = variance(w)
        if strategy in ("minvar", "shrink_minvar"):
            return -v
        if strategy == "max_sharpe":
            # In-sample zero risk-free return is a heuristic only.
            return sum(x * y for x, y in zip(w, means)) / max(math.sqrt(v), 1e-8)
        if strategy == "risk_parity":
            contributions = [w[i] * sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
            total = sum(contributions)
            if total <= 1e-14:
                return -1e9
            return -sum((c / total - 1 / n) ** 2 for c in contributions)
        raise ValueError("unknown strategy: " + strategy)

    return max(grid, key=score)


def performance(returns, turnover, cost_bps):
    nav, peak, mdd = 1., 1., 0.
    net = []
    for r, t in zip(returns, turnover):
        value = (1 + r) * (1 - t * cost_bps / 10000)
        if value <= 0:
            raise ValueError("invalid net portfolio wealth")
        net_r = value - 1
        net.append(net_r)
        nav *= value
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
    years = len(net) / 12
    avg = sum(net) / len(net)
    var = sum((x - avg) ** 2 for x in net) / max(1, len(net) - 1)
    vol = math.sqrt(var)
    downside = math.sqrt(sum(min(0., r) ** 2 for r in net) / len(net))
    return {"cagr": nav ** (1 / years) - 1, "mdd": mdd,
            "volatility": vol * math.sqrt(12),
            "sharpe_rf0": avg / vol * math.sqrt(12) if vol else None,
            "sortino_mar0": avg / downside * math.sqrt(12) if downside else None,
            "total_turnover": sum(turnover), "months": len(net)}


def backtest(months, assets, panel, lookback=60, rebalance=12, cost_bps=10, seed=17, grid_count=2500):
    if len(months) <= lookback or lookback < 24 or rebalance < 1 or cost_bps < 0:
        raise ValueError("invalid lookback/rebalance/cost or too few months")
    grid = candidates(len(assets), seed, grid_count)
    strategies = ("equal", "minvar", "shrink_minvar", "max_sharpe", "risk_parity")
    records = {s: {"returns": [], "turnover": [], "weights": []} for s in strategies}
    current = {}
    for t in range(lookback, len(months)):
        if (t - lookback) % rebalance == 0:
            train = panel[t - lookback:t]  # No future return leakage.
            for s in strategies:
                target = model_weights(train, s, grid)
                prior = current.get(s, [0.] * len(assets))
                # Turnover approximates buys/sells. First investment excluded.
                change = 0 if s not in current else sum(abs(a - b) for a, b in zip(target, prior))
                current[s] = target[:]
                records[s]["turnover"].append(change)
                records[s]["weights"].append({"month": months[t], "target": dict(zip(assets, target))})
        else:
            for s in strategies:
                records[s]["turnover"].append(0.)
        for s in strategies:
            w = current[s]
            gross = sum(x * r for x, r in zip(w, panel[t]))
            records[s]["returns"].append(gross)
            # Drift weights after asset returns until next rebalance.
            total = 1 + gross
            if total <= 0:
                raise ValueError("portfolio loss >=100%")
            current[s] = [x * (1 + r) / total for x, r in zip(w, panel[t])]
    return {"status": "RESEARCH_ONLY", "assets": assets, "oos_start": months[lookback],
            "oos_end": months[-1], "lookback_months": lookback, "rebalance_months": rebalance,
            "round_trip_cost_bps_per_unit_turnover": cost_bps, "candidate_grid_count": len(grid),
            "strategies": {s: {**performance(v["returns"], v["turnover"], cost_bps),
                               "rebalance_targets": v["weights"]} for s, v in records.items()},
            "limitations": ["historical return mean is not forward CMA",
                            "candidate-grid approximate solutions, not exact global optimum",
                            "RF=0 and MAR=0 metrics; no taxes or account restrictions",
                            "no leverage/ETF daily-reset or cashflow simulation"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--lookback", type=int, default=60)
    p.add_argument("--rebalance", type=int, default=12)
    p.add_argument("--cost-bps", type=float, default=10.)
    p.add_argument("--grid-count", type=int, default=2500)
    p.add_argument("--min-months", type=int, default=84)
    args = p.parse_args()
    try:
        m, a, panel = load_panel(args.input, max(args.min_months, args.lookback + 1))
        result = backtest(m, a, panel, args.lookback, args.rebalance, args.cost_bps, grid_count=args.grid_count)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
