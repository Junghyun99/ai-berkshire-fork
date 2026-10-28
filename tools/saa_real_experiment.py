"""Reproducible latest-vintage, ETF-proxy study; NOT verified/live performance."""
import argparse
import csv
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from saa_backtest import backtest, performance
from saa_source_gate import enforce
from saa_market_data import ASSETS, build, month_range, read_series, monthly


def run(root, output):
    coverage = build(root)
    enforce(root)  # Stop before publishing performance on unresolved ETF source gaps.
    with (root/'processed/monthly_returns.csv').open() as f:
        rows = list(csv.DictReader(f))
    with (root/'processed/rates.csv').open() as f:
        rf = {r['month']: float(r['krw_rf_proxy']) for r in csv.DictReader(f)}
    by_asset = {a: {r['month']: float(r['return_krw']) for r in rows if r['asset_id']==a} for a in ASSETS}
    universes = {'five_asset': list(ASSETS),
                 'without_kr_bonds': [a for a in ASSETS if a != 'KR_TREASURY10Y'],
                 'us_only_long': ['US_SP500', 'US_NASDAQ100', 'US_TREASURY7_10Y']}
    results = {}
    for name, assets in universes.items():
        common = sorted(set(rf).intersection(*(set(by_asset[a]) for a in assets)))
        if common != list(month_range(common[0], common[-1])):
            raise ValueError('non-contiguous common months; never silently drop gaps')
        panel = [[by_asset[a][m] for a in assets] for m in common]
        rates = [rf[m] for m in common]
        result = backtest(common, assets, panel, risk_free=rates, signal_lag=2, include_series=True)
        result.update(input_start=common[0], input_end=common[-1], input_months=len(common),
                      status='PROVISIONAL_LATEST_VINTAGE_ETF_PROXY_SIMULATION')
        # Terminal period is a retrospective diagnostic, NOT an untouched holdout.
        oos_months = common[62:]
        for strat, values in result['strategies'].items():
            start = next(i for i,m in enumerate(oos_months) if m >= '2024-01')
            values['terminal_2024_onward'] = performance(values['gross_returns'][start:], values['turnover'][start:], 10, rates[62+start:])
            values['cost_sensitivity'] = {str(cost): performance(values['gross_returns'], values['turnover'], cost, rates[62:]) for cost in (0, 10, 30)}
        results[name] = result
        print(name, result['oos_start'], result['oos_end'], flush=True)
    # Lookback sensitivity: same start/end and rebalance schedule for all three.
    assets = universes['five_asset']; common = sorted(set(rf).intersection(*(set(by_asset[a]) for a in assets)))
    panel = [[by_asset[a][m] for a in assets] for m in common]
    rates = [rf[m] for m in common]
    sensitivity = {}
    for lookback in (36,60,120):
        offset = 120-lookback
        r = backtest(common[offset:], assets, panel[offset:], lookback=lookback, risk_free=rates[offset:], signal_lag=2)
        sensitivity[str(lookback)] = r
        print('lookback',lookback,r['oos_start'],flush=True)
    qa = {'status': 'PARTIAL_CROSS_CHECK_NOT_FULL_VERIFICATION',
          'no_interpolation': True, 'no_synthetic_prices': True, 'coverage':coverage,
          'exclusions': {'114260.KS':'issuer confirms 807 KRW distribution in Dec 2025; downloaded Yahoo events stop in 2018',
                         '069500.KS_pre_2009_05':'missing observations; no backfill'},
          'cross_checks': []}
    j=json.loads((root/'raw/yahoo/148070.KS.json').read_text())['chart']['result'][0]
    dividends={(datetime.fromtimestamp(d['date'], ZoneInfo('Asia/Seoul')).year, float(d['amount'])) for d in j['events']['dividends'].values()}
    for pair in ((2018,2500),(2019,2900),(2020,2300),(2022,1200),(2023,3500),(2024,4000),(2025,3742)):
        if pair not in dividends: raise ValueError('KR Treasury issuer distribution mismatch')
    qa['cross_checks'].append({'asset':'148070.KS','check':'issuer 2018/2019/2020/2022/2023/2024/2025 distribution year/amount pairs present; record date and ex-date differ',
                              'source':'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=148070','result':'pass'})
    j=json.loads((root/'raw/yahoo/069500.KS.json').read_text())['chart']['result'][0]
    pairs={(datetime.fromtimestamp(d['date'], ZoneInfo('Asia/Seoul')).strftime('%Y-%m'), float(d['amount'])) for d in j['events']['dividends'].values()}
    if ('2025-07',176.) not in pairs: raise ValueError('KODEX 200 issuer distribution mismatch')
    qa['cross_checks'].append({'asset':'069500.KS','check':'2025-07 issuer distribution 176 KRW', 'result':'pass',
                              'source':'https://www.samsungfund.com/etf/lounge/notice-view.do?no=68693'})
    levels=monthly(read_series(root,'IEF')[0],'2026-09')
    annual=levels['2024-12'][1]/levels['2023-12'][1]-1
    if abs(annual-(-.0063))>.0005: raise ValueError('IEF 2024 issuer market-return mismatch')
    qa['cross_checks'].append({'asset':'IEF','check':'2024 adjusted-close return vs issuer market-price -0.63%',
                              'computed':annual,'absolute_tolerance':.0005,'result':'pass',
                              'source':'https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf'})
    payload={'status':'PROVISIONAL_RESEARCH_ONLY','as_of':'2026-09-30','base_currency':'KRW',
             'seed':17,'random_candidates':2500,'lookback':60,'signal_lag':2,'rebalance':12,'cost_bps':10,
             'rf':'OECD Korea 3m interbank annual percentage /1200, observation lag 3 months; estimated cash-return proxy, not sovereign realized return',
             'qa':qa,'universes':results,'matched_oos_lookbacks':sensitivity}
    output.mkdir(parents=True,exist_ok=True)
    (output/'results-full.json').write_text(json.dumps(payload,indent=2,allow_nan=False))
    # Public compact results omit source-derived monthly histories/targets.
    for r in results.values():
        for v in r['strategies'].values():
            for k in ('gross_returns','turnover','rebalance_targets'):v.pop(k,None)
    for r in sensitivity.values():
        for v in r['strategies'].values():v.pop('rebalance_targets',None)
    (output/'results-summary.json').write_text(json.dumps(payload,indent=2,allow_nan=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.output)
