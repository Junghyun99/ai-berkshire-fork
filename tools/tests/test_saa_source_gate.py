"""Artificial fixtures for input validation only, not market data."""
import json
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from saa_source_gate import inspect_etf
from saa_market_data import read_series

def sample(prices,adjusted,dates,dividends=None):
    return {'meta':{'exchangeTimezoneName':'UTC','dataGranularity':'1d','symbol':'SPY','currency':'USD'},
            'timestamp':[int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()) for d in dates],
            'indicators':{'quote':[{'close':prices}],'adjclose':[{'adjclose':adjusted}]},
            'events':{'dividends':dividends or {}}}

class SourceGateTests(unittest.TestCase):
    def test_month_end_missing_blocks(self):
        r=inspect_etf(sample([100,None],[100,None],['2023-07-28','2023-07-31']))
        self.assertEqual(r['status'],'BLOCKED_SOURCE_RECONCILIATION')
    def test_missing_exdate_not_mislabeled_zero_dividend(self):
        j=sample([100,None,99],[99,None,99],['2024-10-29','2024-10-30','2024-10-31'])
        j['events']['dividends']={'x':{'date':j['timestamp'][1],'amount':1}}
        self.assertEqual(inspect_etf(j)['issues'][0]['kind'],'dividend_on_missing_quote')
    def test_dividend_factor_missing_blocks(self):
        j=sample([100,99],[100,99],['2023-07-27','2023-07-28'])
        j['events']['dividends']={'x':{'date':j['timestamp'][1],'amount':1}}
        self.assertEqual(inspect_etf(j)['issues'][0]['kind'],'adjustment_factor_mismatch')
    def test_consistent_dividend_passes(self):
        j=sample([100,99],[99,99],['2023-07-27','2023-07-28'])
        j['events']['dividends']={'x':{'date':j['timestamp'][1],'amount':1}}
        self.assertEqual(inspect_etf(j)['status'],'INTERNAL_CHECK_PASS')
    def test_lengths_rejected(self):
        j=sample([100],[100],['2023-07-28']);j['timestamp'].append(0)
        with self.assertRaises(ValueError):inspect_etf(j)
    def test_currency_mismatch_rejected(self):
        j=sample([100],[100],['2023-07-28']);j['meta']['currency']='KRW'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw/yahoo').mkdir(parents=True)
            (root/'raw/yahoo/SPY.json').write_text(json.dumps({'chart':{'result':[j]}}))
            with self.assertRaisesRegex(ValueError,'currency'):read_series(root,'SPY')
