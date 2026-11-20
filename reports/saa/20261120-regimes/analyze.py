"""Ex-post regime descriptions; no trading signals or refitting."""
import argparse,csv,hashlib,json,math,sys
from pathlib import Path
def regime(equity,bonds):
    return ("equity_up" if equity>=0 else "equity_down")+"_"+("bonds_up" if bonds>=0 else "bonds_down")
def net_returns(v,cost):
    if len(v["gross_returns"])!=len(v["turnover"]):raise ValueError("Lengths differ")
    return [(1+r)*(1-t*cost/10000)-1 for r,t in zip(v["gross_returns"],v["turnover"])]
def run(korea,rebuilt,comparison,tools_dir,output):
    sys.path.insert(0,str(tools_dir))
    from saa_backtest import performance
    payload=json.loads(comparison.read_text())
    data=json.loads(rebuilt.read_text())["symbols"]
    rows=list(csv.DictReader((korea/"experiment/inputs/monthly_returns.csv").open()))
    rates={r["month"]:float(r["krw_rf_proxy"]) for r in csv.DictReader((korea/"experiment/inputs/rates.csv").open())}
    indexed={(r["month"],r["asset_id"]):r for r in rows}
    result={"classification":"ex_post_descriptive_not_a_signal","window_months":36,
            "hashes":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (comparison,rebuilt)},
            "variants":{}}
    for variant in ("baseline","issuer_div_backward","issuer_div_ex_close"):
        r=payload[variant]
        months=[m for m in sorted(rates) if r["oos_start"]<=m<=r["oos_end"]]
        net={s:net_returns(v,10) for s,v in r["strategies"].items()}
        assert all(len(v)==len(months) for v in net.values())
        def asset(m,a):
            row=indexed[m,a]
            if variant!="baseline" and a in ("US_SP500","US_TREASURY7_10Y"):
                symbol="SPY" if a=="US_SP500" else "IEF"
                return (1+float(data[symbol]["monthly_returns"][variant][m]))*(1+float(row["fx_to_krw_return"]))-1
            return float(row["return_krw"])
        groups={}
        for i,m in enumerate(months):
            equity=sum(asset(m,a) for a in ("KR_EQUITY","US_SP500","US_NASDAQ100"))/3
            bonds=sum(asset(m,a) for a in ("KR_TREASURY10Y","US_TREASURY7_10Y"))/2
            groups.setdefault(regime(equity,bonds),[]).append(i)
        stats={}
        for label,indices in groups.items():
            stats[label]={"months":len(indices),"strategies":{}}
            for s in net:
                vals=[net[s][i] for i in indices]
                differences=[net[s][i]-net["equal"][i] for i in indices]
                stats[label]["strategies"][s]=dict(mean_monthly_return=sum(vals)/len(vals),
                    mean_delta_vs_equal=sum(differences)/len(vals),
                    worst_month_return=min(vals),positive_months=sum(v>0 for v in vals))
        rolling=[]
        for end in range(36,len(months)+1):
            start=end-36
            values={}
            for s,v in r["strategies"].items():
                values[s]=performance(v["gross_returns"][start:end],v["turnover"][start:end],10,
                                      [rates[m] for m in months[start:end]])
            rolling.append({"start":months[start],"end":months[end-1],"metrics":values})
        wins={}
        for s in net:
            wins[s]={k:sum(w["metrics"][s][k]>w["metrics"]["equal"][k] for w in rolling)
                     for k in ("cagr","mdd","sharpe_rf_proxy","sortino_rf_proxy")}
            wins[s]["joint_risk_adjusted_and_mdd"]=sum(all(w["metrics"][s][k]>w["metrics"]["equal"][k]
                           for k in ("mdd","sharpe_rf_proxy","sortino_rf_proxy")) for w in rolling)
        result["variants"][variant]={"oos_months":len(months),"regimes":stats,
            "rolling_windows":len(rolling),"rolling_wins_vs_equal":wins}
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for a in ("korea","rebuilt","comparison","tools-dir","output"):p.add_argument("--"+a,type=Path,required=True)
    a=p.parse_args();run(a.korea,a.rebuilt,a.comparison,a.tools_dir,a.output)
