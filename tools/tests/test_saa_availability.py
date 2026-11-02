"""Synthetic publication/vintage fixtures; not actual economic releases."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_availability import select


def record(value=1, released='2020-02-03T09:00:00+09:00', vintage_id='v1'):
    return dict(series_id='fixture', observation_at='2020-01-31T16:00:00+09:00',
                available_at=released, vintage_at=released, retrieval_at='2026-10-31T00:00:00Z',
                vintage_id=vintage_id, value=value, source_url='fixture:source', evidence_ref='fixture:release')


class TestAvailability(unittest.TestCase):
    def setUp(self):
        self.required = [dict(series_id='fixture', observation_at='2020-01-31T16:00:00+09:00')]

    def run_select(self, rows, cutoff='2020-02-03T00:00:00Z'):
        return select(rows, cutoff, self.required)

    def test_late_publication_blocks_month_end(self):
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.run_select([record()], '2020-01-31T23:59:59+09:00')

    def test_timezone_and_exact_boundary(self):
        self.assertEqual(self.run_select([record()])['selected'][0]['value'], 1)
        with self.assertRaises(ValueError):
            self.run_select([record()], '2020-02-02T23:59:59Z')

    def test_revision_only_after_release(self):
        rows = [record(), record(2, '2020-03-03T09:00:00+09:00', 'v2')]
        result = self.run_select(rows)
        self.assertEqual(result['selected'][0]['value'], 1)
        self.assertEqual(result['excluded_future_records'], 1)
        self.assertEqual(self.run_select(rows, '2020-03-03T00:00:00Z')['selected'][0]['value'], 2)

    def test_delayed_old_vintage_does_not_displace_newer_revision(self):
        old = record()
        old['available_at'] = '2020-04-01T00:00:00Z'
        revised = record(2, '2020-03-03T09:00:00+09:00', 'v2')
        self.assertEqual(self.run_select([old, revised], '2020-05-01T00:00:00Z')['selected'][0]['value'], 2)

    def test_future_revision_cannot_change_past(self):
        first = self.run_select([record()])['selected']
        self.assertEqual(first, self.run_select([record(999,'2021-01-01T00:00:00Z','v2'),record()])['selected'])

    def test_unknown_dates_and_date_only_block(self):
        for field in ('observation_at','available_at','vintage_at','retrieval_at'):
            for value in (None, '', 'UNKNOWN', '2020-02-03', '2020-02-03T00:00:00'):
                with self.subTest(field=field,value=value):
                    row=record();row[field]=value
                    with self.assertRaises(ValueError):self.run_select([row])

    def test_bad_timestamp_order(self):
        for field in ('vintage_at','available_at','retrieval_at'):
            row=record();row[field]='2019-01-01T00:00:00Z'
            with self.assertRaises(ValueError):self.run_select([row])

    def test_latest_retrieval_not_historical_evidence(self):
        row=record();row['available_at']=None
        with self.assertRaises(ValueError):self.run_select([row])

    def test_conflicting_vintage_and_same_time(self):
        for second in (record(2),record(2,vintage_id='other')):
            with self.assertRaisesRegex(ValueError,'conflicting'):
                self.run_select([record(),second])

    def test_required_missing_series(self):
        self.required.append(dict(series_id='missing',observation_at='2020-01-31T16:00:00+09:00'))
        with self.assertRaisesRegex(ValueError,'unavailable'):self.run_select([record()])

    def test_evidence_and_values(self):
        for field,value in [('evidence_ref',''),('source_url','UNKNOWN'),('vintage_id',None),('value',True),('value',float('nan'))]:
            row=record();row[field]=value
            with self.assertRaises(ValueError):self.run_select([row])

    def test_does_not_mutate_or_authenticate(self):
        rows=[record()];before=copy.deepcopy(rows);result=self.run_select(rows)
        self.assertFalse(result['evidence_authenticated'])
        self.assertEqual(result['quality'],'research_proxy')
        result['selected'][0]['value']=99
        self.assertEqual(rows,before)

    def test_cli_blocked_without_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.json';row=record();row.pop('available_at')
            path.write_text(json.dumps(dict(records=[row],required=self.required)))
            run=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'saa_availability.py'),
                                '--input',str(path),'--decision-at','2020-02-03T00:00:00Z'],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertEqual(json.loads(run.stdout)['status'],'BLOCKED')
