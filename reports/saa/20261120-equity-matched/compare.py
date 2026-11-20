"""Match risk-parity equity weight at rebalance; ex-post controlled comparison."""
import argparse,csv,hashlib,json,math,sys
from pathlib import Path
EQUITY={"KR_EQUITY","US_SP500","US_NASDAQ100"}
METRICS=("cagr","mdd","volatility","sharpe_rf_proxy","sortino_rf_proxy","total_turnover")
def matched(target):
    equity=sum(v for a,v in target.items() if a in EQUITY)
    ne=sum(a in EQUITY for a in target);nb=len(target)-ne
    if not ne or not nb or abs(sum(target.values())-1)>1e-10 or any(not math.isfinite(v) or v<0 for v in target.values()):
        raise ValueError("Invalid targets")
    return {a:equity/ne if a in EQUITY else (1-equity)/nb for a in target}
def replay(months,assets,panel,targets):
    if len(months)!=len(panel) or not months or months!=sorted(set(months)):
        raise ValueError("Invalid panel dates")
    if any(len(row)!=len(assets) or any(not math.isfinite(v) or v<=-1 for v in row) for row in panel):
        raise ValueError("Invalid return panel")
    current=None;gross=[];turnover=[];exposure=[]
    for m,row in zip(months,panel):
        change=0.
        if m in targets:
            target=[targets[m][a] for a in assets]
            if abs(sum(target)-1)>1e-10 or any(not math.isfinite(v) or v<0 for v in target):
                raise ValueError("Invalid weights")
            change=0. if current is None else sum(abs(a-b) for a,b in zip(target,current))
            current=target
        if current is None:raise ValueError("Missing first target")
        exposure.append(sum(w for a,w in zip(assets,current) if a in EQUITY))
        r=sum(w*v for w,v in zip(current,row))
        gross.append(r);turnover.append(change)
        current=[w*(1+v)/(1+r) for w,v in zip(current,row)]
    return gross,turnover,exposure
def run(korea,rebuilt,comparison,tools_dir,output):
    sys.path.insert(0,str(tools_dir))
    from saa_backtest import performance
    source=json.loads(comparison.read_text())
    data=json.loads(rebuilt.read_text())["symbols"]
    rows=list(csv.DictReader((korea/"experiment/inputs/monthly_returns.csv").open()))
    indexed={(r["month"],r["asset_id"]):r for r in rows}
    rates={r["month"]:float(r["krw_rf_proxy"]) for r in csv.DictReader((korea/"experiment/inputs/rates.csv").open())}
    output_data={"quality":"research_proxy","matching":"equity target at rebalance only",
      "hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (rebuilt,comparison,tools_dir/"saa_backtest.py")},
      "variants":{}}
    for variant in ("baseline","issuer_div_backward","issuer_div_ex_close"):
        r=source[variant];assets=r["assets"]
        months=[m for m in sorted(rates) if r["oos_start"]<=m<=r["oos_end"]]
        panel=[]
        for m in months:
            row=[]
            for a in assets:
                x=indexed[m,a];v=float(x["return_krw"])
                if variant!="baseline" and a in ("US_SP500","US_TREASURY7_10Y"):
                    symbol="SPY" if a=="US_SP500" else "IEF"
                    v=(1+float(data[symbol]["monthly_returns"][variant][m]))*(1+float(x["fx_to_krw_return"]))-1
                row.append(v)
            panel.append(row)
        original=r["strategies"]["risk_parity"]
        targets={t["month"]:t["target"] for t in original["rebalance_targets"]}
        g,t,e=replay(months,assets,panel,targets)
        err=max(abs(a-b) for a,b in zip(g,original["gross_returns"]))
        err=max(err,max(abs(a-b) for a,b in zip(t,original["turnover"])))
        if err>1e-12:raise ValueError("Replay differs from original risk parity")
        simple={m:matched(v) for m,v in targets.items()}
        gg,tt,ee=replay(months,assets,panel,simple)
        rf=[rates[m] for m in months]
        perf=performance(gg,tt,10,rf)
        rp={k:original[k] for k in METRICS}
        eq={k:r["strategies"]["equal"][k] for k in METRICS}
        rolling={k:0 for k in ("cagr","mdd","sharpe_rf_proxy","sortino_rf_proxy")}
        for end in range(36,len(months)+1):
            start=end-36
            a=performance(g[start:end],t[start:end],10,rf[start:end])
            b=performance(gg[start:end],tt[start:end],10,rf[start:end])
            for k in rolling:rolling[k]+=int(a[k]>b[k])
        output_data["variants"][variant]={"risk_parity":rp,"matched_simple":{k:perf[k] for k in METRICS},"equal":eq,
          "rp_minus_matched":{k:rp[k]-perf[k] for k in METRICS},
          "rolling36_rp_wins_vs_matched":rolling,"rolling_windows":len(months)-35,
          "replay_error":err,"oos_start":months[0],"oos_end":months[-1],
          "rebalance_targets":simple,"rp_equity_target_range":[min(sum(v[a] for a in v if a in EQUITY) for v in targets.values()),max(sum(v[a] for a in v if a in EQUITY) for v in targets.values())],
          "max_month_start_equity_weight_gap":max(abs(a-b) for a,b in zip(e,ee)),
          "mean_month_start_equity_weight":{"risk_parity":sum(e)/len(e),"matched":sum(ee)/len(ee)}}
    output.write_text(json.dumps(output_data,indent=2,allow_nan=False)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for a in ("korea","rebuilt","comparison","tools-dir","output"):p.add_argument("--"+a,type=Path,required=True)
    a=p.parse_args();run(a.korea,a.rebuilt,a.comparison,a.tools_dir,a.output)
