"""Run explicitly provisional comparisons on reconciled Korean research sources."""
import argparse
import copy
import csv
import json
from pathlib import Path

import numpy as np
from saa_backtest import backtest, performance
from saa_independent_check import reference_run, independent_metrics
from saa_korea_rebuild import build_reconciled
from saa_market_data import ASSETS, month_range


def aligned_panel(rows, rf, assets):
    series = {a: {} for a in assets}
    for row in rows:
        a, m = row['asset_id'], row['month']
        if a in series:
            if m in series[a]:
                raise ValueError('duplicate asset/month')
            series[a][m] = float(row['return_krw'])
    common = sorted(set(rf).intersection(*(set(series[a]) for a in assets)))
    if not common or common != list(month_range(common[0], common[-1])):
        raise ValueError('missing common month')
    return common, np.array([[series[a][m] for a in assets] for m in common]), np.array([rf[m] for m in common])


def run(original, supplement, output):
    if (output / 'results-full.json').exists() or (output / 'results-summary.json').exists():
        raise ValueError('refusing to overwrite an existing experiment; use a new output directory')
    qa = build_reconciled(original, supplement, output / 'inputs')
    with (output / 'inputs/monthly_returns.csv').open() as f:
        rows = list(csv.DictReader(f))
    with (output / 'inputs/rates.csv').open() as f:
        rf = {r['month']: float(r['krw_rf_proxy']) for r in csv.DictReader(f)}
    universes = {'five_asset': list(ASSETS),
                 'without_nasdaq': [a for a in ASSETS if a != 'US_NASDAQ100'],
                 'without_kr_bonds': [a for a in ASSETS if a != 'KR_TREASURY10Y']}
    results, check = {}, {'metrics_checked': 0, 'max_metric_difference': 0., 'max_monthly_return_difference': 0.}
    for name, assets in universes.items():
        months, panel, rates = aligned_panel(rows, rf, assets)
        result = backtest(months, assets, panel.tolist(), risk_free=rates.tolist(), signal_lag=2, include_series=True)
        result.update(input_start=months[0], input_end=months[-1], input_months=len(months))
        for strategy, values in result['strategies'].items():
            gross, turn, targets = reference_run(panel, rates, strategy)
            diff = float(np.max(np.abs(np.asarray(gross) - values['gross_returns'])))
            check['max_monthly_return_difference'] = max(check['max_monthly_return_difference'], diff)
            for key, val in independent_metrics(gross, turn, rates[62:], 10).items():
                delta = abs(values[key] - val)
                check['metrics_checked'] += 1
                check['max_metric_difference'] = max(check['max_metric_difference'], delta)
                if delta > 1e-10 or diff > 1e-10:
                    raise ValueError('independent calculation mismatch')
            expected = [[item['target'][a] for a in assets] for item in values['rebalance_targets']]
            if not np.allclose(targets, expected, atol=1e-12, rtol=0):
                raise ValueError('independent allocation mismatch')
            values['cost_sensitivity'] = {str(cost): performance(values['gross_returns'], values['turnover'], cost, rates[62:].tolist()) for cost in (0, 10, 30)}
        results[name] = result
        print(name, result['oos_start'], result['oos_end'], flush=True)
    assets = universes['without_nasdaq']
    months, panel, rates = aligned_panel(rows, rf, assets)
    # A comparison scenario, not an approved policy: KR/US equity 30% each,
    # KR/US Treasury 20% each. Removing NASDAQ also changes sector exposure.
    fixed = [0.3 if a in ('KR_EQUITY', 'US_SP500') else 0.2 for a in assets]
    gross, turn, _ = reference_run(panel, rates, 'equal', fixed=fixed)
    benchmark = dict(assets=assets, weights=fixed, oos_start=months[62], oos_end=months[-1],
                     metrics=independent_metrics(gross, turn, rates[62:], 10))
    months, panel, rates = aligned_panel(rows, rf, universes['five_asset'])
    sensitivity = {}
    for lookback in (36, 60, 120):
        offset = 120-lookback
        sensitivity[str(lookback)] = backtest(months[offset:], universes['five_asset'], panel[offset:].tolist(),
                                             lookback=lookback, signal_lag=2, risk_free=rates[offset:].tolist())
    payload = dict(status='PROVISIONAL_RECONSTRUCTED_RESEARCH_PROXY', as_of='2026-09-30', base_currency='KRW',
                   lookback=60, signal_lag=2, rebalance=12, cost_bps=10, seed=17, random_candidates=2500,
                   rf='Korean 3m interbank annual yield /1200, observed-month lag 3; estimated cash proxy',
                   qa=qa, independent_check=check, universes=results, fixed_60_40=benchmark,
                   matched_oos_lookbacks=sensitivity)
    (output / 'results-full.json').write_text(json.dumps(payload, indent=2, allow_nan=False))
    public = copy.deepcopy(payload)
    for group in ('universes', 'matched_oos_lookbacks'):
        for result in public[group].values():
            for values in result['strategies'].values():
                for key in ('gross_returns', 'turnover', 'rebalance_targets'):
                    values.pop(key, None)
    (output / 'results-summary.json').write_text(json.dumps(public, indent=2, allow_nan=False))
    return public


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--supplement', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.original, a.supplement, a.output)
