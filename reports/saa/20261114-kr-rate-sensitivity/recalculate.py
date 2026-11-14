"""Reproduce five-asset metrics with archived Korean rates. Research sensitivity."""
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

def shift(month, offset):
    y, m = map(int, month[:7].split("-"))
    i = y * 12 + m - 1 + offset
    return f"{i // 12:04d}-{i % 12 + 1:02d}"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--experiment", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    sys.path.insert(0, str(Path(args.repo) / "tools"))
    from saa_backtest import performance, candidates, model_weights
    experiment = Path(args.experiment)
    full = json.loads((experiment / "results-full.json").read_text())["universes"]["five_asset"]
    months = [shift(full["input_start"], i) for i in range(full["input_months"])]
    evaluation = months[62:]
    original_rf = {r["month"]: float(r["krw_rf_proxy"]) for r in csv.DictReader((experiment / "inputs/rates.csv").open())}
    cached = {r["vintage_date"]: r for r in json.loads(Path(args.evidence).read_text())["records"]}
    cache = Path(args.cache)
    cache.mkdir(exist_ok=True, parents=True)
    sid = "IR3TIB01KRM156N"
    def fetch(month):
        cutoff = (date.fromisoformat(month + "-01") - timedelta(days=2)).isoformat()
        if cutoff in cached:
            record = cached[cutoff]
        else:
            path = cache / (cutoff + ".csv")
            url = f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&vintage_date={cutoff}"
            if not path.exists():
                for attempt in range(3):
                    try:
                        with urlopen(url, timeout=20) as response:
                            data = response.read()
                        lines = list(csv.reader(io.StringIO(data.decode())))
                        if lines[0] != ["observation_date", sid + "_" + cutoff.replace("-", "")]:
                            raise ValueError("unexpected archive header")
                        path.write_bytes(data)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
            data = path.read_bytes()
            header = list(csv.reader(io.StringIO(data.decode())))[0]
            if header != ["observation_date", sid + "_" + cutoff.replace("-", "")]:
                raise ValueError("cached archive header mismatch")
            record = dict(vintage_date=cutoff, url=url, sha256=hashlib.sha256(data).hexdigest(),
                          observations=dict(list(csv.reader(io.StringIO(data.decode())))[1:]))
        target = shift(month, -3) + "-01"
        valid = {k: float(v) for k, v in record["observations"].items() if k <= target and v not in ("", ".")}
        if not valid:
            raise ValueError("no rate at cutoff " + cutoff)
        selected = max(valid)
        return dict(month=month, cutoff=cutoff, target=target, selected=selected,
                    rate=valid[selected] / 1200, original_rate=original_rf[month],
                    source=record)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(fetch, evaluation))
    rates = [r["rate"] for r in rows]
    results = {}
    for name, original in full["strategies"].items():
        old = performance(original["gross_returns"], original["turnover"], 10,
                          [original_rf[m] for m in evaluation])
        for k in ("cagr", "mdd", "sharpe_rf_proxy", "sortino_rf_proxy"):
            assert abs(old[k] - original[k]) < 1e-10
        new = performance(original["gross_returns"], original["turnover"], 10, rates)
        results[name] = dict(original=old, revised=new, delta={k: new[k]-old[k] for k in ("cagr","mdd","sharpe_rf_proxy","sortino_rf_proxy")})
    assets = full["assets"]
    panel_map = {(r["month"],r["asset_id"]): float(r["return_krw"]) for r in csv.DictReader((experiment / "inputs/monthly_returns.csv").open())}
    grid = candidates(len(assets), 17, 2500)
    checks = []
    for t in range(62, len(months), 12):
        month = months[t]
        vintage = next(r["source"]["observations"] for r in rows if r["month"] == month)
        train = [[panel_map[(m,a)] for a in assets] for m in months[t-62:t-2]]
        train_rf = [float(vintage[shift(m,-3)+"-01"])/1200 for m in months[t-62:t-2]]
        old_weights = model_weights(train,"max_sharpe",grid,[original_rf[m] for m in months[t-62:t-2]])
        new_weights = model_weights(train,"max_sharpe",grid,train_rf)
        archived = full["strategies"]["max_sharpe"]["rebalance_targets"][(t-62)//12]["target"]
        assert all(abs(old_weights[i]-archived[a])<1e-12 for i,a in enumerate(assets))
        checks.append(dict(month=month,old=old_weights,new=new_weights,changed=old_weights!=new_weights))
    if any(check["changed"] for check in checks):
        raise ValueError("allocation changes require a full-path rerun")
    for row in rows:
        row["source"] = {**row["source"], "observations": {
            key: row["source"]["observations"].get(key)
            for key in {row["target"], row["selected"]}}}
    output = dict(calculated_at=datetime.now(timezone.utc).isoformat(), scope="KR_RF_only_fixed_return_paths",initial_cost_included=False,
                  quality="research_proxy",cutoff_rule="two calendar days before evaluation month",
                  missing_rule="most recent observation no later than lag-3 target",
                  results=results,allocation_checks=checks,monthly_evidence=rows,
                  input_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [experiment/"results-full.json",experiment/"inputs/rates.csv",experiment/"inputs/monthly_returns.csv"]})
    Path(args.output).write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(dict(results=results,allocation_changes=sum(c["changed"] for c in checks),fallback_months=[r["month"] for r in rows if r["selected"]!=r["target"]]),indent=2))
if __name__ == "__main__":
    main()
