"""Reconstruct research returns without editing the original raw snapshot.

KODEX prices and distributions are issuer observations. KIWOOM uses a separately
labelled secondary adjusted-price proxy; it is NOT an official TR certification.
Optional pandas/xlrd and pdftotext are required only for issuer XLS/PDF parsing.
"""
import argparse
import ast
import bisect
import csv
import hashlib
import json
import math
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs

from saa_market_data import build, monthly, previous_month
from saa_source_gate import inspect_etf


def verify_manifest(root):
    records = json.loads((root / 'manifest.json').read_text())
    paths = [r['path'] for r in records]
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate manifest path')
    for r in records:
        p = (root / r['path']).resolve()
        if not p.is_relative_to(root.resolve()):
            raise ValueError('manifest path outside snapshot')
        if hashlib.sha256(p.read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('source hash mismatch: ' + r['path'])
    return records


def merge_event(events, record_date, amount, source):
    date.fromisoformat(record_date)
    amount = float(amount)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError('invalid distribution amount')
    if record_date in events and events[record_date]['amount'] != amount:
        raise ValueError('conflicting issuer distributions: ' + record_date)
    item = events.setdefault(record_date, {'amount': amount, 'sources': []})
    if source not in item['sources']:
        item['sources'].append(source)


def parse_factsheet(text):
    """Only dated rows in the distribution table; old quarterly grids excluded."""
    match = re.search(r'투자\s*분배금\s*지급\s*현황', text)
    if not match:
        return []
    section = text[match.end():].split('\f')[0]
    return [(d.replace('.', '-'), float(a.replace(',', '')))
            for d, a in re.findall(r'(20\d{2}\.\d{2}\.\d{2})\s+([\d,]+)\s*$', section, re.M)]


def issuer_prices(path, end='2026-09-30'):
    import pandas as pd
    frame = pd.read_excel(path, header=None)
    if 'KODEX 200' not in str(frame.iloc[0, 0]):
        raise ValueError('unexpected issuer XLS product')
    observations = {}
    for row in frame.iloc[4:].itertuples(index=False, name=None):
        raw = str(row[0])
        if not re.fullmatch(r'\d{8}', raw):
            continue
        d = datetime.strptime(raw, '%Y%m%d').date().isoformat()
        if '2009-12-01' <= d <= end:
            close = float(row[1])
            # Issuer displays an unchanged price difference as a dash.
            change = 0. if row[2] == '-' else float(row[2])
            if d in observations or not math.isfinite(close + change) or close <= 0:
                raise ValueError('invalid/duplicate issuer price')
            observations[d] = {'close': close, 'change': change}
    if not observations or max(observations) != end:
        raise ValueError('issuer price end coverage missing')
    return dict(sorted(observations.items()))


def exdate_ledger(prices, events, start='2010-01-01', end='2026-09-30'):
    days = sorted(prices)
    ledger = {}
    for record, item in sorted(events.items()):
        if not start <= record <= end:
            continue
        # Issuer record date and prior observed trading day, NOT payment date.
        i = bisect.bisect_left(days, record)
        if i < 2 or i == len(days) or days[i] != record:
            raise ValueError('record date absent from issuer calendar: ' + record)
        exdate = days[i - 1]
        if exdate in ledger:
            raise ValueError('multiple events on one ex-date')
        ledger[exdate] = dict(record_date=record, ex_date=exdate, **item)
    for i, d in enumerate(days[1:], 1):
        if d < start:
            continue
        reference_adjustment = prices[days[i-1]]['close'] - (prices[d]['close'] - prices[d]['change'])
        amount = ledger.get(d, {}).get('amount', 0.)
        # Exchange reference-price adjustment is rounded to the 5-KRW tick.
        # This tolerance corroborates known cash amounts; NEVER infer cash from it.
        if abs(reference_adjustment - 5 * math.floor(amount / 5)) > 1e-7:
            raise ValueError('unexplained issuer reference-price adjustment: ' + d)
    return ledger


def reconstruct(prices, ledger, convention='adjusted_proxy'):
    if convention not in ('adjusted_proxy', 'exdate_close_cash'):
        raise ValueError('unknown reinvestment convention')
    result = []
    level = 100.
    previous = None
    for d, row in sorted(prices.items()):
        close = row['close']
        amount = ledger.get(d, {}).get('amount', 0.)
        if previous is not None:
            if not 0 <= amount < previous:
                raise ValueError('invalid dividend/reference price')
            growth = (close + amount) / previous if convention == 'exdate_close_cash' else close / (previous - amount)
            level *= growth
        result.append((d, level))
        previous = close
    return result


def naver_prices(text):
    rows = ast.literal_eval(text.strip())
    if rows[0][:5] != ['날짜', '시가', '고가', '저가', '종가']:
        raise ValueError('unexpected secondary source schema')
    result = {}
    previous = ''
    for row in rows[1:]:
        d = datetime.strptime(row[0], '%Y%m%d').date().isoformat()
        value = float(row[4])
        if d <= previous or not math.isfinite(value) or value <= 0:
            raise ValueError('invalid/duplicate/out-of-order secondary observation')
        result[d] = value
        previous = d
    return result


def check_calendar(prices, calendar, start, end):
    expected = {d for d in calendar if start <= d <= end}
    actual = {d for d in prices if start <= d <= end}
    if not expected or actual != expected:
        raise ValueError('secondary source calendar gap/extra date: ' + str(sorted(expected ^ actual)[:10]))


def yahoo_observations(root, symbol, field='adjclose'):
    j = json.loads((root / 'raw/yahoo' / (symbol + '.json')).read_text())['chart']['result'][0]
    z = ZoneInfo(j['meta']['exchangeTimezoneName'])
    values = j['indicators']['adjclose'][0]['adjclose'] if field == 'adjclose' else j['indicators']['quote'][0]['close']
    return {datetime.fromtimestamp(t, z).date().isoformat(): float(v)
            for t, v in zip(j['timestamp'], values) if v is not None}


def build_reconciled(original, supplement, output):
    records = verify_manifest(supplement)
    by_path = {r['path']: r for r in records}
    required = {'raw/kodex-standard.xls', 'raw/kodex-divid.json',
                'raw/official-events-extract.json', 'raw/naver-bond-adjusted.txt'}
    if not required <= by_path.keys():
        raise ValueError('required supplement provenance missing')
    url = urlparse(by_path['raw/naver-bond-adjusted.txt']['source_url'])
    if url.hostname != 'api.finance.naver.com' or parse_qs(url.query).get('symbol') != ['148070']:
        raise ValueError('secondary source identity mismatch')
    for path, key in (('raw/kodex-standard.xls', 'fId'), ('raw/kodex-divid.json', 'id')):
        url = urlparse(by_path[path]['source_url'])
        if url.hostname != 'www.samsungfund.com' or parse_qs(url.query).get(key) != ['2ETF01']:
            raise ValueError('issuer source identity mismatch')
    # build verifies every original source hash/identity. Original raw stays intact.
    build(original)
    for symbol in ('SPY', 'IEF'):
        j = json.loads((original / 'raw/yahoo' / (symbol + '.json')).read_text())['chart']['result'][0]
        if inspect_etf(j)['status'] != 'INTERNAL_CHECK_PASS':
            raise ValueError('unresolved US source: ' + symbol)
    prices = issuer_prices(supplement / 'raw/kodex-standard.xls')
    events = {}
    for r in records:
        p = supplement / r['path']
        if r['kind'] == 'issuer_factsheet_pdf':
            # Extract afresh from hash-checked PDF; do not trust untracked .txt.
            text = subprocess.check_output(['pdftotext', '-layout', str(p), '-'], text=True)
            if '069500' not in text:
                raise ValueError('factsheet product identity mismatch')
            for d, amount in parse_factsheet(text):
                merge_event(events, d, amount, r['path'])
    for row in json.loads((supplement / 'raw/kodex-divid.json').read_text())['dividList']:
        d = datetime.strptime(row['basicD'], '%Y%m%d').date().isoformat()
        merge_event(events, d, row['dividA'], 'raw/kodex-divid.json')
    for row in json.loads((supplement / 'raw/official-events-extract.json').read_text())['events']:
        merge_event(events, row['record_date'], row['amount'], 'raw/official-events-extract.json')
    ledger = exdate_ledger(prices, events)
    stock_levels = monthly(reconstruct(prices, ledger), '2026-09')
    cash_levels = monthly(reconstruct(prices, ledger, 'exdate_close_cash'), '2026-09')
    bond = naver_prices((supplement / 'raw/naver-bond-adjusted.txt').read_text())
    if min(bond) != '2011-10-20' or max(bond) != '2026-09-30':
        raise ValueError('secondary bond coverage changed')
    check_calendar(bond, prices, min(bond), max(bond))
    vendor = yahoo_observations(original, '148070.KS')
    overlap = sorted(set(bond) & set(vendor))
    deviations = [abs(bond[d] / vendor[d] - 1) for d in overlap]
    if len(overlap) < 3500 or max(deviations) > .0001:
        raise ValueError('secondary bond cross-check outside declared tolerance')
    stock_vendor = yahoo_observations(original, '069500.KS', 'close')
    stock_overlap = sorted(set(prices) & set(stock_vendor))
    if any(prices[d]['close'] != stock_vendor[d] for d in stock_overlap):
        raise ValueError('issuer/vendor unadjusted stock price conflict')
    bond_levels = monthly(list(bond.items()), '2026-09')
    with (original / 'processed/monthly_returns.csv').open() as f:
        rows = [r for r in csv.DictReader(f) if r['asset_id'] not in ('KR_EQUITY', 'KR_TREASURY10Y')]
    for asset, levels, source, typ in (
            ('KR_EQUITY', stock_levels, 'KODEX_ISSUER_RECONSTRUCTION', 'calculated_adjusted_price_TR_proxy'),
            ('KR_TREASURY10Y', bond_levels, 'NAVER_148070', 'secondary_adjusted_price_TR_proxy')):
        for m, (d, level) in levels.items():
            prev = previous_month(m)
            if prev not in levels:
                continue
            ret = level / levels[prev][1] - 1
            rows.append(dict(month=m, asset_id=asset, total_return_local=ret, fx_to_krw_return=0., return_krw=ret,
                             source_id=source, as_of=d, available_at='', quality='research_proxy', fx_observation_date='', return_type=typ))
    comparison = []
    with (original / 'processed/monthly_returns.csv').open() as f:
        old = {(r['asset_id'], r['month']): float(r['return_krw']) for r in csv.DictReader(f)}
    for r in rows:
        key = (r['asset_id'], r['month'])
        if key in old and key[0].startswith('KR_'):
            delta = float(r['return_krw']) - old[key]
            if abs(delta) > .0001:
                comparison.append(dict(asset=key[0], month=key[1], old=old[key], rebuilt=float(r['return_krw']), delta=delta))
    qa = dict(status='PROVISIONAL_RECONSTRUCTED_RESEARCH_PROXY', official_bond_TR=False,
              issuer_price_count=len(prices), issuer_dividends=len(ledger),
              stock_price_cross_check_count=len(stock_overlap), stock_price_mismatches=0,
              bond_calendar_cross_check='matches issuer KODEX trading-date observations; not independent KRX calendar',
              bond_observations=len(bond), bond_overlap=len(overlap), bond_max_relative_level_difference=max(deviations),
              bond_level_tolerance=.0001, corrected_months=comparison,
              cash_vs_adjusted_proxy_max_monthly_difference=max(abs(cash_levels[m][1]/cash_levels[previous_month(m)][1]-stock_levels[m][1]/stock_levels[previous_month(m)][1]) for m in stock_levels if previous_month(m) in stock_levels),
              limitations=['secondary bond methodology not certified by issuer', 'historical available_at unknown',
                           'adjusted-price convention differs from ex-date-close cash reinvestment and actual payment-date execution',
                           'issuer reference adjustment confirms event coverage only for selected sample',
                           'raw source snapshots are latest vintage; no untouched holdout'])
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'monthly_returns.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (output / 'rates.csv').write_bytes((original / 'processed/rates.csv').read_bytes())
    qa['input_manifest_hashes'] = {name: hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()
                                  for name, root in (('original', original), ('supplement', supplement))}
    qa['processed_hashes'] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                              for name in ('monthly_returns.csv', 'rates.csv')}
    (output / 'qa.json').write_text(json.dumps(qa, indent=2, ensure_ascii=False))
    (output / 'dividend-ledger.json').write_text(json.dumps(ledger, indent=2))
    return qa


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--supplement', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_reconciled(args.original, args.supplement, args.output), indent=2))
