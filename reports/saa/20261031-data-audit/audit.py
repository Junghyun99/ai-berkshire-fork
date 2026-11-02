"""Read-only audit of existing private snapshots; no downloads or backtests.
Run from any directory; output contains metadata/counts, not raw prices.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from saa_korea_rebuild import verify_manifest
from saa_market_data import FRED, ETFS, read_series, month_range
from saa_source_gate import enforce
from saa_data_quality import load_panel


def audit(original, supplement, processed):
    manifests = {name: verify_manifest(root) for name, root in [('original', original), ('supplement', supplement)]}
    qa = json.loads((processed / 'qa.json').read_text())
    for name, expected in qa['processed_hashes'].items():
        if hashlib.sha256((processed / name).read_bytes()).hexdigest() != expected:
            raise ValueError('processed hash mismatch: ' + name)
    for name, root in [('original', original), ('supplement', supplement)]:
        if hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest() != qa['input_manifest_hashes'][name]:
            raise ValueError('input manifest mismatch: ' + name)
    coverage = {}
    for symbol in FRED + ETFS:
        observations, nulls = read_series(original, symbol)
        coverage[symbol] = dict(first=observations[0][0], last=observations[-1][0], observations=len(observations), nulls=nulls)
    with (processed / 'monthly_returns.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    months, keys, quality, types = defaultdict(set), set(), set(), defaultdict(set)
    for row in rows:
        key = row['asset_id'], row['month']
        if key in keys:
            raise ValueError('duplicate processed asset/month')
        keys.add(key)
        months[key[0]].add(key[1]); quality.add(row['quality']); types[key[0]].add(row['return_type'])
    coverage_months = {}
    for asset, values in months.items():
        ordered = sorted(values)
        coverage_months[asset] = dict(first=ordered[0], last=ordered[-1], count=len(values),
                                      contiguous=ordered == list(month_range(ordered[0], ordered[-1])),
                                      return_types=sorted(types[asset]))
    common = sorted(set.intersection(*months.values()))
    if common != list(month_range(common[0], common[-1])):
        raise ValueError('noncontiguous common months')
    try:
        enforce(original)
        source_gate = 'INTERNAL_CHECK_PASS'
    except ValueError as exc:
        source_gate = str(exc)
    try:
        load_panel(processed / 'monthly_returns.csv', 60)
        strict_gate = 'PASS'
    except ValueError as exc:
        strict_gate = str(exc)
    return dict(scope='snapshot integrity and coverage only; not official certification',
                manifest_files_verified={k: len(v) for k, v in manifests.items()},
                original_observed_coverage=coverage, processed_coverage=coverage_months,
                common=dict(first=common[0], last=common[-1], count=len(common)),
                quality=sorted(quality), available_at_missing=sum(not r['available_at'] for r in rows),
                processed_rows=len(rows), original_source_gate=source_gate, strict_data_gate=strict_gate,
                official_bond_TR=qa['official_bond_TR'], processed_hashes=qa['processed_hashes'],
                input_manifest_hashes=qa['input_manifest_hashes'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'supplement', 'processed'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(audit(a.original, a.supplement, a.processed), indent=2))
