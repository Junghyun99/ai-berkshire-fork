"""Research-only point-in-time selection from explicitly evidenced vintages.

Does not infer publication dates, authenticate evidence, fetch vintages or change
existing latest-vintage backtests. Timestamps require an explicit UTC offset.
"""
import argparse
import copy
import json
from datetime import datetime, timezone
from math import isfinite


def instant(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be a timezone-aware ISO string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('invalid timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone required; date-only evidence is insufficient')
    return parsed.astimezone(timezone.utc)


def key(record):
    values = record.get('series_id'), record.get('observation_at')
    if not isinstance(values[0], str) or not values[0].strip():
        raise ValueError('series_id required')
    return values[0], instant(values[1])


def select(records, decision_at, required):
    cutoff = instant(decision_at)
    if not isinstance(records, list) or not records:
        raise ValueError('nonempty vintage records required')
    if not isinstance(required, list) or not required or any(not isinstance(r, dict) for r in required):
        raise ValueError('explicit required series/observation keys required')
    keys = [key(r) for r in required]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate required key')
    wanted = set(keys)
    candidates, seen = {}, {}
    excluded = 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('record must be an object')
        k = key(record)
        available = instant(record.get('available_at'))
        vintage = instant(record.get('vintage_at'))
        retrieved = instant(record.get('retrieval_at'))
        if not k[1] <= vintage <= available <= retrieved:
            raise ValueError('observation/vintage/availability/retrieval ordering invalid')
        for name in ('source_url', 'evidence_ref', 'vintage_id'):
            value = record.get(name)
            if not isinstance(value, str) or not value.strip() or value.upper() in ('TBD', 'UNKNOWN'):
                raise ValueError(name + ' evidence required')
        value = record.get('value')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError('finite numeric value required')
        # Same semantic vintage cannot carry contradictory numbers or timing.
        identity = k, record['vintage_id']
        signature = (value, vintage, available)
        if identity in seen and seen[identity] != signature:
            raise ValueError('conflicting vintage identity')
        seen[identity] = signature
        if available > cutoff:
            excluded += 1
            continue
        if k not in wanted:
            continue
        rank = (vintage, available)
        previous = candidates.get(k)
        if previous is not None and rank == previous[0] and value != previous[1]['value']:
            raise ValueError('conflicting values at same release time')
        if previous is None or rank > previous[0]:
            candidates[k] = rank, record
    missing = wanted - candidates.keys()
    if missing:
        raise ValueError('required observations unavailable at decision: ' +
                         ', '.join(s + '@' + t.isoformat() for s, t in sorted(missing)))
    return {'status': 'PASS', 'scope': 'declared_timestamp_selection_only',
            'quality': 'research_proxy', 'evidence_authenticated': False,
            'decision_at': cutoff.isoformat(), 'excluded_future_records': excluded,
            'selected': [copy.deepcopy(candidates[k][1]) for k in sorted(wanted)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='JSON object: records and required arrays')
    parser.add_argument('--decision-at', required=True)
    args = parser.parse_args()
    try:
        with open(args.input, encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError('input object required')
        result = select(data.get('records'), args.decision_at, data.get('required'))
    except (ValueError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc), 'evidence_authenticated': False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
