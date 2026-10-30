"""Synthetic fixtures exercise reconstruction failures, not investment evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_korea_rebuild import (merge_event, parse_factsheet, exdate_ledger,
                               reconstruct, naver_prices, check_calendar, verify_manifest)


class KoreaRebuildTests(unittest.TestCase):
    def test_conflicting_cash_amount_rejected(self):
        events = {}
        merge_event(events, '2023-07-31', 75, 'a')
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            merge_event(events, '2023-07-31', 85, 'b')

    def test_agreeing_sources_are_deduplicated(self):
        events = {}
        for source in ('a', 'a', 'b'):
            merge_event(events, '2023-07-31', 75, source)
        self.assertEqual(events['2023-07-31']['sources'], ['a', 'b'])

    def test_pdf_scope_excludes_unrelated_dates(self):
        text = '2020.01.01 999\n투자분배금 지급현황\n지급기준일 분배금액\n2023.07.31 75\n\f2023.01.01 50'
        self.assertEqual(parse_factsheet(text), [('2023-07-31', 75.)])

    def prices(self):
        return {'2023-07-26': {'close': 1000., 'change': 0.},
                '2023-07-27': {'close': 1010., 'change': 10.},
                '2023-07-28': {'close': 940., 'change': 5.},
                '2023-07-31': {'close': 950., 'change': 10.}}

    def test_record_date_maps_to_prior_observed_trading_day(self):
        events = {'2023-07-31': {'amount': 75., 'sources': ['fixture']}}
        ledger = exdate_ledger(self.prices(), events, start='2023-07-27')
        self.assertEqual(ledger['2023-07-28']['record_date'], '2023-07-31')

    def test_missing_distribution_cannot_pass_reference_check(self):
        with self.assertRaisesRegex(ValueError, 'unexplained'):
            exdate_ledger(self.prices(), {}, start='2023-07-27')

    def test_reference_rounding_does_not_replace_cash_amount(self):
        events = {'2023-07-31': {'amount': 78., 'sources': ['fixture']}}
        ledger = exdate_ledger(self.prices(), events, start='2023-07-27')
        self.assertEqual(ledger['2023-07-28']['amount'], 78.)

    def test_distinct_reinvestment_conventions(self):
        prices = {'2023-07-27': {'close': 100.}, '2023-07-28': {'close': 92.}}
        ledger = {'2023-07-28': {'amount': 10.}}
        self.assertAlmostEqual(reconstruct(prices, ledger)[-1][1], 100*92/90)
        self.assertAlmostEqual(reconstruct(prices, ledger, 'exdate_close_cash')[-1][1], 102.)

    def test_zero_or_excessive_cash_rejected(self):
        with self.assertRaises(ValueError):
            merge_event({}, '2023-07-31', 0, 'fixture')
        with self.assertRaises(ValueError):
            reconstruct({'2023-07-27': {'close': 100.}, '2023-07-28': {'close': 92.}}, {'2023-07-28': {'amount': 100.}})

    def test_secondary_calendar_gap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'calendar'):
            check_calendar({'2023-07-28': 10}, ['2023-07-28', '2023-07-31'], '2023-07-28', '2023-07-31')

    def test_secondary_duplicate_and_nonpositive_rejected(self):
        header = ['날짜', '시가', '고가', '저가', '종가']
        with self.assertRaises(ValueError):
            naver_prices(repr([header, ['20230731', 1, 1, 1, 1], ['20230731', 1, 1, 1, 1]]))
        with self.assertRaises(ValueError):
            naver_prices(repr([header, ['20230731', 1, 1, 1, 0]]))

    def test_hash_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'raw').mkdir()
            (root / 'raw/source').write_bytes(b'actual observation')
            row = {'path': 'raw/source', 'sha256': hashlib.sha256(b'actual observation').hexdigest()}
            (root / 'manifest.json').write_text(json.dumps([row]))
            verify_manifest(root)
            (root / 'raw/source').write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'hash'):
                verify_manifest(root)

    def test_outside_manifest_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'manifest.json').write_text(json.dumps([{'path': '../outside', 'sha256': ''}]))
            with self.assertRaisesRegex(ValueError, 'outside'):
                verify_manifest(root)


if __name__ == '__main__':
    unittest.main()
