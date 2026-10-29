"""Replay a limited issuer-table/Yahoo event check; does not certify TR."""
import argparse
import ast
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Factual transcription of issuer product page's distribution table, retrieved
# 2026-10-29 KST through web search extraction (not a downloaded HTML snapshot).
SOURCE = 'https://www.kiwoometf.com/service/etf/KO02010200M?gcode=148070'
RECORDS = [
    ('2011-12-06', 582), ('2012-12-06', 4333), ('2014-12-30', 3300),
    ('2015-12-30', 3100), ('2016-12-29', 1500), ('2018-12-28', 2500),
    ('2019-12-30', 2900), ('2020-12-30', 2300), ('2022-12-29', 1200),
    ('2023-12-28', 3500), ('2024-12-30', 4000), ('2025-12-30', 3742),
]


def check(yahoo_path, calendar_path):
    raw = json.loads(yahoo_path.read_text())['chart']['result'][0]
    if raw['meta']['symbol'] != '148070.KS':
        raise ValueError('wrong symbol')
    events = list(raw['events']['dividends'].values())
    observed = {datetime.fromtimestamp(x['date'], ZoneInfo('Asia/Seoul')).date().isoformat(): x['amount'] for x in events}
    if len(observed) != len(events):
        raise ValueError('duplicate event dates')
    # Existing secondary trading-day sequence: not an official KRX calendar.
    table = ast.literal_eval(calendar_path.read_text().strip())
    days = [str(x[0]) for x in table[1:] if x]
    days = [f'{d[:4]}-{d[4:6]}-{d[6:]}' for d in days]
    if days != sorted(set(days)):
        raise ValueError('invalid calendar sequence')
    expected = {}
    for record, amount in RECORDS:
        index = days.index(record)
        if index == 0:
            raise ValueError('no previous trading day')
        expected[days[index - 1]] = amount
    if expected != observed:
        raise ValueError('issuer/event mismatch')
    return {'status': 'distribution_table_matches_only', 'event_count': len(expected),
            'source_url': SOURCE, 'source_retrieval_date_kst': '2026-10-29',
            'source_capture': 'web search text extraction; no local HTML snapshot',
            'source_page_as_of': '2026-09-11', 'official_tr_verified': False,
            'inputs_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [yahoo_path, calendar_path]},
            'limits': ['record-to-ex-date mapping uses secondary observed calendar',
                       'no proof of unlisted events being absent',
                       'not a price, adjustment-factor, or full-TR verification']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('yahoo', type=Path)
    parser.add_argument('calendar', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.yahoo, args.calendar), ensure_ascii=False, indent=2))
