"""Download observed data and build explicitly provisional SAA research panels.

No prices are invented, backfilled or interpolated. Raw snapshots are private;
public manifests contain hashes and provenance, not redistribution permission.
"""
import argparse
import calendar
import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

FRED = ('NASDAQXNDX', 'DEXKOUS', 'DGS3MO', 'IR3TIB01KRM156N')
ETFS = ('SPY', 'IEF', '069500.KS', '148070.KS')
ASSETS = {'KR_EQUITY': ('069500.KS', 'KRW'), 'US_SP500': ('SPY', 'USD'),
          'US_NASDAQ100': ('NASDAQXNDX', 'USD'), 'KR_TREASURY10Y': ('148070.KS', 'KRW'),
          'US_TREASURY7_10Y': ('IEF', 'USD')}


def month_range(first, last):
    y, m = map(int, first.split('-'))
    while f'{y:04d}-{m:02d}' <= last:
        yield f'{y:04d}-{m:02d}'
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def previous_month(month, n=1):
    y, m = map(int, month.split('-'))
    k = y * 12 + m - 1 - n
    return f'{k // 12:04d}-{k % 12 + 1:02d}'


def download(root, end):
    raw = root / 'raw'
    records = []
    end_epoch = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())
    for vendor, symbols in [('fred', FRED), ('yahoo', ETFS)]:
        for s in symbols:
            url = (f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}' if vendor == 'fred'
                   else f'https://query2.finance.yahoo.com/v8/finance/chart/{s}?period1=1072915200&period2={end_epoch}&interval=1d&events=div%2Csplits')
            path = raw / vendor / (s + ('.csv' if vendor == 'fred' else '.json'))
            path.parent.mkdir(parents=True, exist_ok=True)
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=45) as response:
                body = response.read()
            if path.exists() and path.read_bytes() != body:
                raise ValueError(f'refusing to overwrite immutable snapshot {path}')
            path.write_bytes(body)
            records.append({'source_id': s, 'vendor': vendor, 'source_url': url,
                            'path': str(path.relative_to(root)), 'retrieval_at': datetime.now(timezone.utc).isoformat(),
                            'sha256': hashlib.sha256(body).hexdigest(),
                            'vintage': 'latest_at_retrieval', 'available_at': None,
                            'license': 'provider terms apply; public redistribution NOT cleared',
                            'quality': 'observed_source_not_full_independent_validation'})
            print(f'downloaded {s}: {len(body)} bytes', flush=True)
    (root / 'manifest.json').write_text(json.dumps(records, indent=2))


def read_series(root, s):
    if s in FRED:
        with (root / 'raw/fred' / (s + '.csv')).open() as f:
            rows = list(csv.DictReader(f))
        observations = [(r['observation_date'], float(r[s])) for r in rows if r[s] not in ('', '.')]
        nulls = len(rows) - len(observations)
    else:
        j = json.loads((root / 'raw/yahoo' / (s + '.json')).read_text())['chart']['result'][0]
        if j['meta']['dataGranularity'] != '1d':
            raise ValueError(f'{s}: daily data required (provider silently resampled)')
        z = ZoneInfo(j['meta']['exchangeTimezoneName'])
        adj = j['indicators']['adjclose'][0]['adjclose']
        observations = [(datetime.fromtimestamp(t, z).date().isoformat(), float(v))
                        for t, v in zip(j['timestamp'], adj) if v is not None]
        nulls = len(adj) - len(observations)
    dates = [d for d, v in observations]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError(f'{s}: duplicate or unsorted dates')
    if any(not math.isfinite(v) or (s not in ('DGS3MO', 'IR3TIB01KRM156N') and v <= 0) for d, v in observations):
        raise ValueError(f'{s}: invalid observations')
    return observations, nulls


def monthly(observations, end_month, rate=False):
    result = {}
    for d, v in observations:
        if d[:7] <= end_month:
            result[d[:7]] = (d, v)
    if not rate:
        # A holiday is allowed; weeks of stale observations are not.
        for m, (d, _) in list(result.items()):
            y, mo = map(int, m.split('-'))
            if (date(y, mo, calendar.monthrange(y, mo)[1]) - date.fromisoformat(d)).days > 7:
                del result[m]
    return result


def build(root, end_month='2026-09'):
    manifest = json.loads((root / 'manifest.json').read_text())
    expected = set(FRED) | set(ETFS)
    if len(manifest) != len(expected) or {r['source_id'] for r in manifest} != expected:
        raise ValueError('incomplete or duplicate source manifest')
    for r in manifest:
        if hashlib.sha256((root / r['path']).read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('raw hash mismatch: ' + r['source_id'])
    levels, coverage = {}, {}
    for s in (*FRED, *ETFS):
        obs, nulls = read_series(root, s)
        levels[s] = monthly(obs, end_month, rate=s in ('DGS3MO', 'IR3TIB01KRM156N'))
        coverage[s] = {'first_observation': obs[0][0], 'last_observation': obs[-1][0],
                       'valid_observations': len(obs), 'null_observations_excluded': nulls,
                       'monthly_levels': len(levels[s])}
    rows = []
    for asset, (s, currency) in ASSETS.items():
        for m, (d, v) in levels[s].items():
            prev = previous_month(m)
            if prev not in levels[s] or m not in levels['DEXKOUS'] or prev not in levels['DEXKOUS']:
                continue
            local = v / levels[s][prev][1] - 1
            fx = levels['DEXKOUS'][m][1] / levels['DEXKOUS'][prev][1] - 1 if currency == 'USD' else 0.
            rows.append({'month': m, 'asset_id': asset, 'total_return_local': local, 'fx_to_krw_return': fx,
                         'return_krw': (1 + local) * (1 + fx) - 1, 'source_id': s, 'as_of': d,
                         'available_at': '', 'quality': 'research_proxy',
                         'fx_observation_date': levels['DEXKOUS'][m][0] if currency == 'USD' else '',
                         'return_type': 'official_TR_index' if s == 'NASDAQXNDX' else 'vendor_adjusted_ETF_proxy'})
    out = root / 'processed'; out.mkdir(exist_ok=True)
    with (out / 'monthly_returns.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    rates = []
    for m in month_range('2004-01', end_month):
        # Deliberate 3-month observation lag, NOT an authenticated publication date.
        prior = previous_month(m, 3)
        if all(prior in levels[s] for s in ('DGS3MO', 'IR3TIB01KRM156N')):
            rates.append({'month': m, 'rate_observation_month': prior,
                          'krw_rf_proxy': levels['IR3TIB01KRM156N'][prior][1] / 1200,
                          'usd_rf_proxy': levels['DGS3MO'][prior][1] / 1200,
                          'classification': 'estimated_monthly_cash_return_from_observed_annual_yield'})
    with (out / 'rates.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rates[0])); w.writeheader(); w.writerows(rates)
    (root / 'coverage.json').write_text(json.dumps(coverage, indent=2))
    return coverage


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--download', action='store_true')
    p.add_argument('--end-exclusive', default='2026-10-01')
    p.add_argument('--end-month', default='2026-09')
    a = p.parse_args()
    a.root.mkdir(parents=True, exist_ok=True)
    if a.download:
        download(a.root, a.end_exclusive)
    print(json.dumps(build(a.root, a.end_month), indent=2))
