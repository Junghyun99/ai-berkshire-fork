"""Fixed equity targets / defensive sleeves; FX removal is not a hedge return."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from saa_backtest import performance

ASSETS = ['KR_EQUITY', 'US_SP500', 'KR_TREASURY10Y', 'US_TREASURY7_10Y']
WEIGHTS = {'kr_bond': [.3, .3, .4, 0.], 'us_bond': [.3, .3, 0., .4],
           'mixed_bonds': [.3, .3, .2, .2]}


def fixed_path(panel, target, rebalance):
    if not isinstance(rebalance, int) or rebalance < 1:
        raise ValueError('invalid rebalance interval')
    if not target or any(not math.isfinite(w) or w < 0 for w in target) or not math.isclose(sum(target), 1):
        raise ValueError('invalid target weights')
    w = None
    gross, turns, starts = [], [], []
    for t, row in enumerate(panel):
        if len(row) != len(target) or any(not math.isfinite(r) or r <= -1 for r in row):
            raise ValueError('invalid asset returns')
        change = 0.
        if t % rebalance == 0:
            change = 0. if w is None else sum(abs(x-y) for x,y in zip(target,w))
            w = target[:]
        starts.append(w[:])
        r = sum(x*y for x,y in zip(w,row))
        gross.append(r)
        turns.append(change)
        w = [x*(1+y)/(1+r) for x,y in zip(w,row)]
    return gross, turns, starts


def fx_parts(local, fx):
    if not all(math.isfinite(x) and x > -1 for x in (local, fx)):
        raise ValueError('invalid local/FX return')
    return local, fx, local*fx


def run(inputs, qa_path, output):
    import numpy as np
    from saa_rebuilt_experiment import aligned_panel
    from saa_independent_check import reference_run, independent_metrics
    if output.exists():
        raise ValueError('refusing to overwrite output')
    qa = json.loads(qa_path.read_text())
    hashes = {}
    for name in ('monthly_returns.csv', 'rates.csv'):
        hashes[name] = hashlib.sha256((inputs/name).read_bytes()).hexdigest()
        if hashes[name] != qa['processed_hashes'][name]:
            raise ValueError('input hash mismatch')
    with (inputs/'monthly_returns.csv').open() as f:
        rows = list(csv.DictReader(f))
    with (inputs/'rates.csv').open() as f:
        rates = list(csv.DictReader(f))
    rf = {r['month']:float(r['krw_rf_proxy']) for r in rates}
    if len(rf) != len(rates):
        raise ValueError('duplicate rate month')
    months, panel, rf = aligned_panel(rows, rf, ASSETS)
    if months[0] != '2011-11' or months[-1] != '2026-09' or months[62] != '2017-01':
        raise ValueError('unexpected experiment period')
    if not np.isfinite(rf).all():
        raise ValueError('invalid RF proxy')
    us = {r['month']:r for r in rows if r['asset_id'] == ASSETS[3]}
    local = np.array([float(us[m]['total_return_local']) for m in months])
    fx = np.array([float(us[m]['fx_to_krw_return']) for m in months])
    parts = np.array([fx_parts(l,f) for l,f in zip(local,fx)])
    if not np.allclose(parts.sum(axis=1),panel[:,3],atol=1e-12,rtol=0):
        raise ValueError('FX identity mismatch')
    variants = {name:(target,panel) for name,target in WEIGHTS.items()}
    nofx = panel.copy(); nofx[:,3] = local
    for name in ('us_bond','mixed_bonds'):
        variants[name+'_no_bond_fx'] = (WEIGHTS[name], nofx)
    records, count, error, base_paths = [], 0, 0., {}
    for name,(target,full) in variants.items():
        for rebalance in (3,6,12):
            gross,turn,starts = fixed_path(full[62:].tolist(),target,rebalance)
            rg,rt,_ = reference_run(full,rf,'equal',fixed=target,rebalance=rebalance)
            if not np.allclose(gross,rg,atol=1e-12,rtol=0) or not np.allclose(turn,rt,atol=1e-12,rtol=0):
                raise ValueError('independent path mismatch')
            for cost in (0,10,30):
                metrics = performance(gross,turn,cost,rf[62:].tolist())
                for k,v in independent_metrics(rg,rt,rf[62:],cost).items():
                    delta=abs(v-metrics[k]); count+=1; error=max(error,delta)
                    if delta > 1e-10:
                        raise ValueError('independent metric mismatch')
                records.append(dict(scenario=name,rebalance_months=rebalance,cost_bps=cost,metrics=metrics))
            if rebalance == 12:
                base_paths[name]=(gross,turn,starts)
    subperiods = {}
    for name,(gross,turn,starts) in base_paths.items():
        subperiods[name]={}
        for begin,end in [('2017-01','2019-12'),('2020-01','2021-12'),('2022-01','2022-12'),('2023-01','2026-09')]:
            idx=[i for i,m in enumerate(months[62:]) if begin<=m<=end]
            subperiods[name][begin+':'+end]=performance([gross[i] for i in idx],[turn[i] for i in idx],10,[float(rf[62+i]) for i in idx])
    attribution={}
    for name in WEIGHTS:
        gross,turn,starts=base_paths[name]
        weighted=np.asarray(starts)[:,3,None]*parts[62:]
        attribution[name]={'mean_monthly_contribution':dict(zip(['local_bond','fx','interaction'],weighted.mean(axis=0).tolist())),
                           'max_identity_error':float(np.max(np.abs(weighted.sum(axis=1)-np.asarray(starts)[:,3]*panel[62:,3]))),
                           'scope':'monthly arithmetic gross-return contribution, not additive CAGR attribution',
                           'equity_weight_min':min(w[0]+w[1] for w in starts),
                           'equity_weight_max':max(w[0]+w[1] for w in starts)}
    result=dict(status='PROVISIONAL_RESEARCH_PROXY',input_hashes=hashes,
                qa_sha256=hashlib.sha256(qa_path.read_bytes()).hexdigest(),assets=ASSETS,targets=WEIGHTS,
                oos_start=months[62],oos_end=months[-1],oos_months=len(months)-62,
                reference_check=dict(metric_count=count,max_difference=error,monthly_paths_match=True),
                comparisons=records,subperiods=subperiods,us_bond_fx_attribution=attribution,
                limitations=['60% equity target only at rebalance; weights drift between dates',
                             'no-bond-FX is counterfactual, not a tradable hedged portfolio; equity FX unchanged',
                             'Korean bond official long TR unresolved; latest-vintage proxies',
                             'no untouched holdout; subperiods descriptive; no causal or significance claim',
                             'RF estimated cash proxy; monthly MDD; taxes/accounts/cashflows absent; initial cost excluded'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--qa',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); print(run(a.inputs,a.qa,a.output)['reference_check'])
