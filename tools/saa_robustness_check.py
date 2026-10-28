"""Matched-period sensitivity on the US assets that passed internal source QA.

KRW metrics; Korea's interbank cash-return proxy is retained. Conditional block
bootstrap resamples observed OOS outcomes, not new market observations.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from saa_independent_check import raw_months,reference_run,independent_metrics
from saa_source_gate import inspect_etf

STRATEGIES=('equal','minvar','shrink_minvar','max_sharpe','risk_parity')

def bootstrap_difference(net_a,net_b,rf,draws=1000):
    a=np.asarray(net_a)-rf;b=np.asarray(net_b)-rf;n=len(a);rng=np.random.default_rng(29)
    stats=[]
    for _ in range(draws):
        starts=rng.integers(0,n,size=(n+11)//12)
        idx=np.concatenate([(np.arange(12)+s)%n for s in starts])[:n]
        sharpe=lambda x:float(x.mean()/x.std(ddof=1)*np.sqrt(12))
        stats.append(sharpe(a[idx])-sharpe(b[idx]))
    return dict(zip(('p025','median','p975'),map(float,np.quantile(stats,[.025,.5,.975]))))


def run(root,out):
    for symbol in ('SPY','IEF'):
        j=json.loads((root/'raw/yahoo'/f'{symbol}.json').read_text())['chart']['result'][0]
        if inspect_etf(j)['status']!='INTERNAL_CHECK_PASS':raise ValueError('source gate failed')
    fx=raw_months(root,'DEXKOUS').pct_change(fill_method=None)
    levels={s:raw_months(root,s) for s in ('SPY','NASDAQXNDX','IEF')}
    frame=pd.DataFrame({s:(1+v.pct_change(fill_method=None))*(1+fx)-1 for s,v in levels.items()}).dropna().loc['2004-02':'2026-09']
    if len(frame)!=272:raise ValueError('unexpected common sample; update experiment explicitly')
    rates=raw_months(root,'IR3TIB01KRM156N')
    rf=np.array([rates[m-3]/1200 for m in frame.index])
    results={};paths={}
    def execute(key,cols,strategy,lookback=60,rebalance=12,fixed=None,start_offset=0):
        panel=frame[cols].to_numpy()[start_offset:];rate=rf[start_offset:]
        gross,turn,_=reference_run(panel,rate,strategy,lookback=lookback,rebalance=rebalance,fixed=fixed)
        net=(1+np.array(gross))*(1-np.array(turn)*.001)-1
        oos=frame.index[start_offset+lookback+2:]
        result={'assets':cols,'oos_start':str(oos[0]),'oos_end':str(oos[-1]),'lookback':lookback,'rebalance':rebalance,
                'metrics':independent_metrics(gross,turn,rate[lookback+2:],10),
                'cost_sensitivity':{str(c):independent_metrics(gross,turn,rate[lookback+2:],c) for c in (0,10,30)}}
        results[key]=result;paths[key]=(net,rate[lookback+2:])
    for name,cols in [('us_three',['SPY','NASDAQXNDX','IEF']),('no_nasdaq',['SPY','IEF'])]:
        for strategy in STRATEGIES:execute(name+'_'+strategy,cols,strategy)
    execute('fixed_60_40',['SPY','IEF'],'equal',fixed=[.6,.4])
    execute('fixed_two_thirds_equity',['SPY','IEF'],'equal',fixed=[2/3,1/3])
    for lb in (36,60,120):
        for strategy in STRATEGIES:execute(f'lb{lb}_{strategy}',['SPY','IEF'],strategy,lookback=lb,start_offset=120-lb)
    for rb in (3,6):
        for strategy in STRATEGIES:execute(f'rebalance{rb}_{strategy}',['SPY','IEF'],strategy,rebalance=rb)
    uncertainty={}
    for strategy in STRATEGIES[1:]:
        a,rates=paths['no_nasdaq_'+strategy];b,_=paths['no_nasdaq_equal']
        uncertainty[strategy]=bootstrap_difference(a,b,rates)
    payload={'status':'US_SUBSET_ONLY_PROVISIONAL','as_of':'2026-09-30',
             'excluded':'Korean ETF sources require month-end/dividend reconciliation; no Korean allocation conclusion',
             'bootstrap':'1000 paired circular 12-month blocks, seed 29; conditional OOS Sharpe difference vs equal, not refitted strategy or unseen holdout',
             'results':results,'bootstrap_sharpe_difference':uncertainty}
    out.write_text(json.dumps(payload,indent=2,allow_nan=False));print('completed',len(results),'configurations')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.output)
