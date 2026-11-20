"""Paired input sensitivity against the archived Korean-rebuilt baseline."""
import argparse, csv, hashlib, json, sys
from pathlib import Path
ENGINE = Path(__file__).parent/"engine"
if not ENGINE.exists(): ENGINE = Path(__file__).resolve().parents[3]/"tools"
sys.path.insert(0,str(ENGINE))
from saa_backtest import backtest
METRICS=("cagr","mdd","sharpe_rf_proxy","sortino_rf_proxy","total_turnover")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(korea,rebuilt,output):
    source=korea/"experiment"
    old=json.loads((source/"results-full.json").read_text())["universes"]["five_asset"]
    assets=old["assets"]
    rows=list(csv.DictReader((source/"inputs/monthly_returns.csv").open()))
    rates={r["month"]:float(r["krw_rf_proxy"]) for r in csv.DictReader((source/"inputs/rates.csv").open())}
    indexed={a:{r["month"]:r for r in rows if r["asset_id"]==a} for a in assets}
    months=sorted(set(rates).intersection(*(set(indexed[a]) for a in assets)))
    candidate=json.loads(rebuilt.read_text())["symbols"]
    mapping={"US_SP500":"SPY","US_TREASURY7_10Y":"IEF"}
    results={}
    for variant in ("baseline","issuer_div_backward","issuer_div_ex_close"):
        panel=[]
        for m in months:
            row=[]
            for a in assets:
                original=indexed[a][m]
                value=float(original["return_krw"])
                if a in mapping:
                    series=candidate[mapping[a]]["monthly_returns"]
                    if abs(float(series["yahoo_adjclose"][m])-float(original["total_return_local"]))>1e-12:
                        raise ValueError("Local return baseline differs")
                    if variant!="baseline":
                        value=(1+float(series[variant][m]))*(1+float(original["fx_to_krw_return"]))-1
                row.append(value)
            panel.append(row)
        r=backtest(months,assets,panel,lookback=60,rebalance=12,cost_bps=10,
                   seed=17,grid_count=2500,risk_free=[rates[m] for m in months],
                   signal_lag=2,include_series=True,include_initial_cost=False)
        if variant=="baseline":
            diffs=[]
            for s,v in r["strategies"].items():
                for k in METRICS:diffs.append(abs(v[k]-old["strategies"][s][k]))
                diffs.extend(abs(a-b) for a,b in zip(v["gross_returns"],old["strategies"][s]["gross_returns"]))
                assert len(v["gross_returns"])==len(old["strategies"][s]["gross_returns"])
            if max(diffs)>1e-10:raise ValueError("Baseline reproduction failed")
            baseline_error=max(diffs)
            for s,v in r["strategies"].items():
                if v["rebalance_targets"] != old["strategies"][s]["rebalance_targets"]:
                    raise ValueError("Baseline target mismatch")
        results[variant]=r
        print(variant,r["oos_start"],r["oos_end"],flush=True)
    summary={"quality":"research_proxy","input_start":months[0],"input_end":months[-1],
             "input_months":len(months),"oos_start":r["oos_start"],"oos_end":r["oos_end"],
             "baseline_max_abs_error":baseline_error,
             "settings":{"lookback":60,"rebalance":12,"cost_bps":10,"seed":17,"grid_count":2500,
                         "signal_lag":2,"include_initial_cost":False,"rf":"archived Korean lag-3 proxy; not vintage-corrected"},
             "hashes":{str(p.relative_to(korea)):sha(p) for p in [source/"results-full.json",source/"inputs/monthly_returns.csv",source/"inputs/rates.csv"]},
             "engine_hashes":{p.name:sha(p) for p in (ENGINE/name for name in ("saa_backtest.py","saa_data_quality.py","saa_availability.py"))},
             "variants":{}}
    base=results["baseline"]["strategies"]
    for variant,r in results.items():
        entries={}
        for s,v in r["strategies"].items():
            b=base[s]
            targets=v["rebalance_targets"];bt=b["rebalance_targets"]
            assert len(targets)==len(bt)
            weightdiff=max(abs(t["target"][a]-u["target"][a]) for t,u in zip(targets,bt) for a in assets)
            entries[s]={"metrics":{k:v[k] for k in METRICS},
                        "delta":{k:v[k]-b[k] for k in METRICS},"max_target_weight_difference":weightdiff}
        summary["variants"][variant]={"strategies":entries,
            "rankings":{k:sorted(entries,key=lambda s:entries[s]["metrics"][k],reverse=True)
                        for k in ("cagr","sharpe_rf_proxy","sortino_rf_proxy")}}
    output.mkdir(parents=True,exist_ok=True)
    (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    (output/"full.json").write_text(json.dumps(results,indent=2,allow_nan=False)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--korea",type=Path,required=True)
    p.add_argument("--rebuilt",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();run(a.korea,a.rebuilt,a.output)
