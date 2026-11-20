"""Training-only common volatility target, no leverage, cash RF proxy."""
import argparse,csv,hashlib,importlib.util,json,math,statistics,sys
from pathlib import Path
def scale_targets(weights,train,rf):
    if len(train)!=len(rf) or len(train)<2:raise ValueError("Training shape")
    vols={s:statistics.stdev([sum(w*x for w,x in zip(ws,row))-r for row,r in zip(train,rf)])*math.sqrt(12)
          for s,ws in weights.items()}
    if min(vols.values())<=0:raise ValueError("Zero training volatility")
    target=min(vols.values())
    scales={s:target/v for s,v in vols.items()}
    return {s:[w*scales[s] for w in ws]+[1-scales[s]] for s,ws in weights.items()},vols,target,scales
def simulate(months,panel,rf,targets):
    w=None;gross=[];turnover=[];cash=[]
    for m,row,r in zip(months,panel,rf):
        turn=0.
        if m in targets:
            nw=targets[m]
            if w is not None:turn=sum(abs(a-b) for a,b in zip(nw[:-1],w[:-1]))
            w=nw[:]
        if w is None:raise ValueError("Missing initial target")
        rr=row+[r];g=sum(a*b for a,b in zip(w,rr))
        if 1+g<=0:raise ValueError("Invalid wealth")
        cash.append(w[-1]);gross.append(g);turnover.append(turn)
        w=[a*(1+b)/(1+g) for a,b in zip(w,rr)]
    return gross,turnover,cash
def run(a):
    sys.path.insert(0,str(a.tools_dir))
    from saa_backtest import performance
    spec=importlib.util.spec_from_file_location("equity_matched",a.equity_dir/"compare.py")
    eq=importlib.util.module_from_spec(spec);spec.loader.exec_module(eq)
    raw=json.loads(a.comparison.read_text());rebuilt=json.loads(a.rebuilt.read_text())["symbols"]
    with (a.korea/"experiment/inputs/monthly_returns.csv").open() as f:rows=list(csv.DictReader(f))
    indexed={(r["month"],r["asset_id"]):r for r in rows}
    with (a.korea/"experiment/inputs/rates.csv").open() as f:rates={r["month"]:float(r["krw_rf_proxy"]) for r in csv.DictReader(f)}
    out={"quality":"research_proxy","method":"minimum training annual excess volatility of three target portfolios",
         "cash":"existing lag-3 KRW rate proxy, not an investable observed cash fund","initial_cost":False,
         "cash_transaction_cost":0,"training_months":60,"signal_lag":2,"variants":{},
         "hashes":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.comparison,a.rebuilt,a.tools_dir/"saa_backtest.py")}}
    for variant,old in raw.items():
        assets=old["assets"]
        months=sorted(set.intersection(*(set(m for m,x in indexed if x==asset) for asset in assets),set(rates)))
        panel=[]
        for m in months:
            row=[]
            for asset in assets:
                x=indexed[m,asset];v=float(x["return_krw"])
                if variant!="baseline" and asset in ("US_SP500","US_TREASURY7_10Y"):
                    symbol="SPY" if asset=="US_SP500" else "IEF"
                    v=(1+float(rebuilt[symbol]["monthly_returns"][variant][m]))*(1+float(x["fx_to_krw_return"]))-1
                row.append(v)
            panel.append(row)
        target_records=old["strategies"]["risk_parity"]["rebalance_targets"]
        target_map={s:{} for s in ("equal","risk_parity","matched")};audit=[]
        for record in target_records:
            m=record["month"];t=months.index(m)
            if t<62:raise ValueError("Insufficient training")
            train=panel[t-62:t-2];rf=[rates[x] for x in months[t-62:t-2]]
            weights={"equal":[1/len(assets)]*len(assets),
                     "risk_parity":[record["target"][x] for x in assets],
                     "matched":[eq.matched(record["target"])[x] for x in assets]}
            scaled,vols,target,scales=scale_targets(weights,train,rf)
            for s in scaled:target_map[s][m]=scaled[s]
            audit.append({"month":m,"train_start":months[t-62],"train_end":months[t-3],
                          "target_vol":target,"training_vol":vols,"scale":scales})
        start=months.index(old["oos_start"]);ms=months[start:];p=panel[start:];rf=[rates[m] for m in ms]
        strategies={}
        for s in target_map:
            g,tr,c=simulate(ms,p,rf,target_map[s])
            perf={str(cost):performance(g,tr,cost,rf) for cost in (0,10,30)}
            strategies[s]={"performance_by_cost":perf,"mean_cash_weight":sum(c)/len(c),
                           "max_cash_weight":max(c),"targets":target_map[s]}
        out["variants"][variant]={"oos_start":ms[0],"oos_end":ms[-1],"months":len(ms),
                                 "audit":audit,"strategies":strategies}
    a.output.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("korea","rebuilt","comparison","tools-dir","equity-dir","output"):
        p.add_argument("--"+name,type=Path,required=True)
    run(p.parse_args())
