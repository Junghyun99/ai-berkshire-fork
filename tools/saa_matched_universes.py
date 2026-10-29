"""Compare provisional asset universes on identical input and OOS months."""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from saa_backtest import backtest
from saa_independent_check import independent_metrics, reference_run
from saa_market_data import ASSETS
from saa_rebuilt_experiment import aligned_panel


def matched_panels(rows, rf):
    assets = list(ASSETS)
    months, panel, rates = aligned_panel(rows, rf, assets)
    if len(months) <= 62:
        raise ValueError('insufficient common history for 60-month training and 2-month lag')
    if not np.isfinite(panel).all() or not np.isfinite(rates).all() or (panel <= -1).any():
        raise ValueError('invalid return/rate observations')
    universes = {'five_asset': assets,
                 'without_kr_bonds': [a for a in assets if a != 'KR_TREASURY10Y'],
                 'without_nasdaq': [a for a in assets if a != 'US_NASDAQ100']}
    return months, rates, {name: (subset, panel[:, [assets.index(a) for a in subset]])
                           for name, subset in universes.items()}


def run(inputs, qa_path, output):
    if output.exists():
        raise ValueError('refusing to overwrite experiment output')
    qa = json.loads(qa_path.read_text())
    hashes = {}
    for name in ('monthly_returns.csv', 'rates.csv'):
        digest = hashlib.sha256((inputs / name).read_bytes()).hexdigest()
        if digest != qa['processed_hashes'][name]:
            raise ValueError('input hash mismatch: ' + name)
        hashes[name] = digest
    with (inputs / 'monthly_returns.csv').open() as f:
        rows = list(csv.DictReader(f))
    with (inputs / 'rates.csv').open() as f:
        records = list(csv.DictReader(f))
    rf = {r['month']: float(r['krw_rf_proxy']) for r in records}
    if len(records) != len(rf):
        raise ValueError('duplicate rate month')
    months, rates, panels = matched_panels(rows, rf)
    results, checked, maximum = {}, 0, 0.
    for name, (assets, panel) in panels.items():
        result = backtest(months, assets, panel.tolist(), risk_free=rates.tolist(),
                          signal_lag=2, include_series=True)
        for strategy, values in result['strategies'].items():
            gross, turn, targets = reference_run(panel, rates, strategy)
            for actual, expected in ((values['gross_returns'], gross), (values['turnover'], turn),
                ([[t['target'][a] for a in assets] for t in values['rebalance_targets']], targets)):
                if not np.allclose(actual, expected, atol=1e-10, rtol=0):
                    raise ValueError('reference path/allocation mismatch')
            for key, expected in independent_metrics(gross, turn, rates[62:], 10).items():
                difference = abs(values[key] - expected)
                if difference > 1e-10:
                    raise ValueError('reference metric mismatch')
                maximum = max(maximum, difference)
                checked += 1
        results[name] = result
    public = copy.deepcopy(results)
    for result in public.values():
        for values in result['strategies'].values():
            for key in ('gross_returns', 'turnover', 'rebalance_targets'):
                values.pop(key, None)
    comparison = {}
    for name in ('without_kr_bonds', 'without_nasdaq'):
        comparison[name] = {s: {k: public[name]['strategies'][s][k] - base[k]
                               for k in ('cagr', 'mdd', 'sharpe_rf_proxy', 'sortino_rf_proxy')}
                            for s, base in public['five_asset']['strategies'].items()}
    payload = {'status': 'PROVISIONAL_MATCHED_PERIOD_RESEARCH_PROXY',
               'input_start': months[0], 'input_end': months[-1], 'input_months': len(months),
               'oos_start': months[62], 'oos_end': months[-1], 'oos_months': len(months) - 62,
               'settings': {'lookback': 60, 'signal_lag': 2, 'rebalance': 12, 'cost_bps': 10,
                            'seed': 17, 'random_candidates': 2500},
               'input_hashes': hashes, 'qa_sha256': hashlib.sha256(qa_path.read_bytes()).hexdigest(),
               'reference_check': {'metric_count': checked, 'max_metric_difference': maximum,
                                   'monthly_paths_turnover_targets_match': True},
               'universes': public, 'difference_vs_five_asset': comparison,
               'limits': ['latest-vintage proxies; not official TR certification',
                          'secondary Korean bond price proxy remains unverified',
                          'asset removal also changes allocations; not a causal diversification estimate',
                          'shared period selected after prior results; not an untouched holdout',
                          'monthly MDD; initial purchase costs excluded; RF is an estimated cash proxy']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--qa', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = run(a.inputs, a.qa, a.output)
    print(json.dumps(r['reference_check']))
