"""Independent NumPy/Pandas check; does not import the production SAA engine.

Run against a private raw snapshot and its full results. Numeric agreement does
not certify source correctness or historical point-in-time availability.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path
import numpy as np
import pandas as pd

ASSETS={'KR_EQUITY':('069500.KS','KRW'),'US_SP500':('SPY','USD'),
        'US_NASDAQ100':('NASDAQXNDX','USD'),'KR_TREASURY10Y':('148070.KS','KRW'),
        'US_TREASURY7_10Y':('IEF','USD')}


def raw_months(root, symbol):
    if symbol in ('NASDAQXNDX','DEXKOUS','IR3TIB01KRM156N','DGS3MO'):
        frame=pd.read_csv(root/'raw/fred'/f'{symbol}.csv')
        series=pd.Series(pd.to_numeric(frame[symbol],errors='coerce').to_numpy(),index=pd.to_datetime(frame['observation_date'])).dropna()
    else:
        j=json.loads((root/'raw/yahoo'/f'{symbol}.json').read_text())['chart']['result'][0]
        dates=pd.to_datetime(j['timestamp'],unit='s',utc=True).tz_convert(j['meta']['exchangeTimezoneName']).tz_localize(None).normalize()
        series=pd.Series(j['indicators']['adjclose'][0]['adjclose'],index=dates).dropna()
    monthly=series.groupby(series.index.to_period('M')).last()
    if symbol not in ('IR3TIB01KRM156N','DGS3MO'):
        last=pd.Series(series.index,index=series.index).groupby(series.index.to_period('M')).last()
        valid=[(p.to_timestamp(how='end').normalize()-last[p]).days<=7 for p in monthly.index]
        monthly=monthly.loc[valid]
    return monthly[monthly.index<=pd.Period('2026-09')]


def independent_metrics(gross, turn, rf, cost):
    net=(1+np.asarray(gross))*(1-np.asarray(turn)*cost/10000)-1
    nav=np.cumprod(1+net); wealth=np.r_[1.,nav]
    excess=net-np.asarray(rf)
    result={'cagr':float(nav[-1]**(12/len(net))-1),
            'mdd':float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
            'volatility':float(np.std(net,ddof=1)*np.sqrt(12)),
            'sharpe_rf0':float(np.mean(net)/np.std(net,ddof=1)*np.sqrt(12)),
            'sortino_mar0':float(np.mean(net)/np.sqrt(np.mean(np.minimum(net,0)**2))*np.sqrt(12)),
            'sharpe_rf_proxy':float(np.mean(excess)/np.std(excess,ddof=1)*np.sqrt(12)),
            'sortino_rf_proxy':float(np.mean(excess)/np.sqrt(np.mean(np.minimum(excess,0)**2))*np.sqrt(12)),
            'total_turnover':float(sum(turn))}
    return result


def reference_candidates(n):
    grid=[[1/n]*n]+np.eye(n).tolist()
    for a in range(n):
        for b in range(a+1,n):
            for p in range(1,10):
                row=[0.]*n;row[a]=p/10;row[b]=1-p/10;grid.append(row)
    rng=random.Random(17)
    for _ in range(2500):
        row=[rng.gammavariate(1,1) for _ in range(n)];grid.append([v/sum(row) for v in row])
    return np.asarray(grid)


def reference_run(panel, rf, strategy, lookback=60, lag=2, rebalance=12, grid=None, fixed=None):
    n=panel.shape[1];grid=reference_candidates(n) if grid is None else grid
    w=None;gross=[];turn=[];targets=[]
    for t in range(lookback+lag,len(panel)):
        turnover=0.
        if (t-lookback-lag)%rebalance==0:
            train=panel[t-lag-lookback:t-lag]
            cov=np.cov(train,rowvar=False,ddof=1)
            if fixed is not None: target=np.asarray(fixed)
            elif strategy=='equal':target=np.ones(n)/n
            else:
                if strategy=='shrink_minvar':cov=.5*cov+.5*np.diag(np.diag(cov))
                var=np.maximum(np.einsum('ij,jk,ik->i',grid,cov,grid),0)
                if strategy in ('minvar','shrink_minvar'):score=-var
                elif strategy=='max_sharpe':score=(grid@train.mean(axis=0)-np.mean(rf[t-lag-lookback:t-lag]))/np.maximum(np.sqrt(var),1e-8)
                elif strategy=='risk_parity':
                    rc=grid*(grid@cov);total=rc.sum(axis=1)
                    score=np.full(len(grid),-1e9);valid=total>1e-14
                    score[valid]=-((rc[valid]/total[valid,None]-1/n)**2).sum(axis=1)
                else:raise ValueError(strategy)
                target=grid[np.argmax(score)].copy()
            turnover=0. if w is None else float(np.abs(target-w).sum())
            w=target.copy();targets.append(w.tolist())
        r=float(w@panel[t]);gross.append(r);turn.append(turnover)
        w=w*(1+panel[t])/(1+r)
    return gross,turn,targets


def check(root, full, output):
    levels={s:raw_months(root,s) for s in [*[s for s,c in ASSETS.values()],'DEXKOUS','IR3TIB01KRM156N','DGS3MO']}
    returns={}
    for a,(s,currency) in ASSETS.items():
        # Reindex before pct_change so missing months cannot become multi-month returns.
        lv=levels[s].reindex(pd.period_range(levels[s].index.min(),levels[s].index.max(),freq='M'))
        r=lv.pct_change(fill_method=None)
        if currency=='USD':r=(1+r)*(1+levels['DEXKOUS'].pct_change(fill_method=None))-1
        returns[a]=r.dropna()
    panel_csv=pd.read_csv(root/'processed/monthly_returns.csv')
    max_panel_error=0.
    for row in panel_csv.itertuples():
        max_panel_error=max(max_panel_error,abs(float(returns[row.asset_id][pd.Period(row.month)])-row.return_krw))
    assert max_panel_error<1e-12
    results=json.loads(full.read_text());max_metric_error=0.;max_path_error=0.;count=0
    for name,record in results['universes'].items():
        frame=pd.DataFrame({a:returns[a] for a in record['assets']}).dropna().loc[record['input_start']:record['input_end']]
        rates=np.array([levels['IR3TIB01KRM156N'][m-3]/1200 for m in frame.index])
        for strategy,v in record['strategies'].items():
            gross,turn,targets=reference_run(frame.to_numpy(),rates,strategy)
            error=max(float(np.max(np.abs(np.array(gross)-v['gross_returns']))),float(np.max(np.abs(np.array(turn)-v['turnover']))))
            max_path_error=max(max_path_error,error)
            expected=np.array([[t['target'][a] for a in record['assets']] for t in v['rebalance_targets']])
            assert np.max(np.abs(expected-targets))<1e-10
            metrics=independent_metrics(gross,turn,rates[62:],10)
            for k,value in metrics.items():max_metric_error=max(max_metric_error,abs(value-v[k]));count+=1
    assert max_metric_error<1e-10 and max_path_error<1e-10
    adjustment_checks={}
    for symbol in ('SPY','IEF','069500.KS','148070.KS'):
        j=json.loads((root/'raw/yahoo'/f'{symbol}.json').read_text())['chart']['result'][0]
        timezone=j['meta']['exchangeTimezoneName']
        date_key=lambda t:pd.Timestamp(t,unit='s',tz='UTC').tz_convert(timezone).date().isoformat()
        div={date_key(d['date']):d['amount'] for d in j.get('events',{}).get('dividends',{}).values()}
        prev=None;errors=[];events=0
        for t,close,adj in zip(j['timestamp'],j['indicators']['quote'][0]['close'],j['indicators']['adjclose'][0]['adjclose']):
            if close is None or adj is None:continue
            d=date_key(t);ratio=adj/close
            if prev:
                distribution=div.get(d,0);events+=int(distribution!=0)
                expected=1/(1-distribution/prev[1]);actual=ratio/prev[2]
                if abs(actual-expected)>5e-5:errors.append({'date':d,'factor_difference':actual-expected,'dividend':distribution})
            prev=(d,close,ratio)
        adjustment_checks[symbol]={'event_count':events,'factor_anomalies':errors,
                                   'scope':'same-vendor internal consistency; not independent source verification'}
    result={'status':'NUMERICAL_REFERENCE_PASS','source_snapshot_manifest_sha256':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
            'numpy_version':np.__version__,'pandas_version':pd.__version__,
            'metric_comparisons':count,'max_panel_error':max_panel_error,'max_path_error':max_path_error,
            'max_metric_error':max_metric_error,'dividend_adjustment_checks':adjustment_checks,
            'source_verification':'PARTIAL; annual issuer spot checks only, full historical official reconciliation unresolved'}
    output.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--full-results',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();check(a.root,a.full_results,a.output)
