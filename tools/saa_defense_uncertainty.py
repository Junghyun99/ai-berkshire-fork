"""Paired circular-block uncertainty diagnostic of already realized proxy paths.

Not a new market history, refitted strategy, forecast, or policy approval.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def block_indices(n, block, reps, seed):
    import numpy as np
    if any(not isinstance(x, int) for x in (n, block, reps)) or n < 2 or not 1 <= block <= n or reps < 1:
        raise ValueError('invalid bootstrap dimensions')
    rng = np.random.default_rng(seed)
    starts = rng.integers(n, size=(reps, (n + block - 1)//block))
    return ((starts[..., None] + np.arange(block)) % n).reshape(reps, -1)[:, :n]


def ratios(excess):
    import numpy as np
    x = np.asarray(excess, dtype=float)
    mean = x.mean(axis=-1)
    std = x.std(axis=-1, ddof=1)
    down = np.sqrt(np.minimum(x, 0).__pow__(2).mean(axis=-1))
    return {name: np.divide(mean*np.sqrt(12), den, out=np.full_like(mean, np.nan), where=den > 1e-14)
            for name, den in (('sharpe_rf_proxy', std), ('sortino_rf_proxy', down))}


def paired_differences(left, right, rf, indices):
    import numpy as np
    a,b,f = [np.asarray(x,dtype=float) for x in (left,right,rf)]
    ix = np.asarray(indices)
    if a.ndim != 1 or a.shape != b.shape or a.shape != f.shape or len(a)<2:
        raise ValueError('unaligned monthly paths')
    if not all(np.isfinite(x).all() for x in (a,b,f)):
        raise ValueError('nonfinite monthly path')
    if ix.ndim != 2 or ix.shape[1] != len(a) or not np.issubdtype(ix.dtype,np.integer) or (ix<0).any() or (ix>=len(a)).any():
        raise ValueError('invalid paired indices')
    ra,rb = ratios((a-f)[ix]),ratios((b-f)[ix])
    return {key: ra[key]-rb[key] for key in ra}


def summarize(samples, observed):
    import numpy as np
    valid = np.asarray(samples)[np.isfinite(samples)]
    count = len(valid)
    usable = count >= .9*len(samples) and count > 0
    return dict(observed=float(observed), valid_replicates=count, invalid_replicates=len(samples)-count,
                percentile_95=[float(x) for x in np.quantile(valid,[.025,.975])] if usable else None,
                positive_fraction=float(np.mean(valid>0)) if usable else None,
                status='EXPLORATORY_POINTWISE_INTERVAL' if usable else 'INSUFFICIENT_VALID_REPLICATES')


def run(inputs, qa_path, baseline_path, output, reps=2000, seed=20261030):
    import numpy as np
    from saa_defensive_mix import ASSETS, WEIGHTS, fixed_path
    from saa_rebuilt_experiment import aligned_panel
    from saa_market_data import month_range
    from saa_independent_check import independent_metrics
    if output.exists():
        raise ValueError('refusing to overwrite output')
    qa=json.loads(qa_path.read_text()); baseline=json.loads(baseline_path.read_text())
    hashes={}
    for name in ('monthly_returns.csv','rates.csv'):
        hashes[name]=hashlib.sha256((inputs/name).read_bytes()).hexdigest()
        if hashes[name]!=qa['processed_hashes'][name] or hashes[name]!=baseline['input_hashes'][name]:
            raise ValueError('input hash mismatch')
    if baseline['qa_sha256']!=hashlib.sha256(qa_path.read_bytes()).hexdigest():
        raise ValueError('QA hash mismatch')
    with (inputs/'monthly_returns.csv').open() as f: rows=list(csv.DictReader(f))
    with (inputs/'rates.csv').open() as f: rates=list(csv.DictReader(f))
    rf={r['month']:float(r['krw_rf_proxy']) for r in rates}
    if len(rf)!=len(rates): raise ValueError('duplicate rate month')
    months,panel,rf=aligned_panel(rows,rf,ASSETS)
    if months[62:]!=list(month_range('2017-01','2026-09')):
        raise ValueError('unexpected OOS months')
    paths={}; checked=0; error=0.
    for name,target in WEIGHTS.items():
        gross,turn,_=fixed_path(panel[62:].tolist(),target,12)
        prior=[c['metrics'] for c in baseline['comparisons'] if c['scenario']==name and c['cost_bps']==10 and c['rebalance_months']==12]
        if len(prior)!=1: raise ValueError('missing/duplicate baseline')
        metrics=independent_metrics(gross,turn,rf[62:],10)
        for k,v in metrics.items():
            delta=abs(v-prior[0][k]); checked+=1; error=max(error,delta)
            if delta>1e-10: raise ValueError('baseline reproduction mismatch')
        paths[name]=(1+np.asarray(gross))*(1-np.asarray(turn)*.001)-1
    pairs=[('us_bond','kr_bond'),('mixed_bonds','kr_bond'),('us_bond','mixed_bonds')]
    result={}
    for block in (3,6,12):
        ix=block_indices(len(months)-62,block,reps,seed+block)
        result[str(block)]={}
        for left,right in pairs:
            samples=paired_differences(paths[left],paths[right],rf[62:],ix)
            a,b=ratios(paths[left]-rf[62:]),ratios(paths[right]-rf[62:])
            result[str(block)][left+' - '+right]={key:summarize(values,a[key]-b[key]) for key,values in samples.items()}
    payload=dict(status='EXPLORATORY_PROXY_PATH_UNCERTAINTY',oos_start=months[62],oos_end=months[-1],months=len(months)-62,
                 method='paired circular block bootstrap of realized net returns and RF; percentile intervals',
                 blocks=[3,6,12],replicates_per_block=reps,seed=seed,block_seed_rule='seed + block_length',
                 numpy_version=np.__version__,input_hashes=hashes,
                 qa_sha256=hashlib.sha256(qa_path.read_bytes()).hexdigest(),
                 baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                 baseline_check=dict(metric_count=checked,max_difference=error),results=result,
                 limitations=['resampled observations are synthetic statistical replicates, not collected market data',
                              'conditional on realized annual-rebalance net paths; strategy not rerun on resampled assets',
                              'same indices across portfolios and RF preserve contemporaneous pairing',
                              'circular wrap joins sample end to start; stationarity/dependence approximation',
                              '3/6/12 blocks not fitted or chosen to maximize significance',
                              'pointwise exploratory intervals; no multiple-testing adjustment, p-value or posterior probability',
                              'positive_fraction is a replicate share, not probability of future outperformance',
                              'latest-vintage proxies; Korean official long TR unresolved; no untouched holdout'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--qa',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=Path('reports/saa/20261030-defensive-mix/results-summary.json'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(run(a.inputs,a.qa,a.baseline,a.output)['baseline_check'])
