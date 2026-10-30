"""Synthetic fixtures test mechanics only; never reported as market performance."""
import math
import json
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_backtest import performance, backtest
from saa_market_data import monthly, previous_month, build, read_series

class RealDataMechanics(unittest.TestCase):
    def test_rf_metrics_manual(self):
        r = [.03, -.01, .02]; rf = [.01] * 3
        got = performance(r, [0, 0, 0], 0, rf)
        x = [.02, -.02, .01]; avg = sum(x)/3
        sd = math.sqrt(sum((v-avg)**2 for v in x)/2)
        self.assertAlmostEqual(got['sharpe_rf_proxy'], avg/sd*math.sqrt(12))
        self.assertAlmostEqual(got['sortino_rf_proxy'], avg/(.02/math.sqrt(3))*math.sqrt(12))
    def test_signal_gap_excluded(self):
        months = [str(i) for i in range(28)]
        panel = [[.01 + i*.0001, -.002 + (i%3)*.002] for i in range(28)]
        a = backtest(months, ['a', 'b'], panel, lookback=24, signal_lag=2, grid_count=20)
        panel[24] = [10, -.9]; panel[25] = [-.9, 10]
        b = backtest(months, ['a', 'b'], panel, lookback=24, signal_lag=2, grid_count=20)
        for s in a['strategies']:
            self.assertEqual(a['strategies'][s]['rebalance_targets'], b['strategies'][s]['rebalance_targets'])
    def test_rf_length_rejected(self):
        with self.assertRaises(ValueError): performance([.1], [0], 0, [])
    def test_lag_leaves_no_oos(self):
        with self.assertRaises(ValueError): backtest(list(range(26)), ['a','b'], [[0,0]]*26, lookback=24, signal_lag=2)
    def test_stale_month_not_filled(self):
        self.assertEqual(monthly([('2020-01-02', 100)], '2020-01'), {})
    def test_month_end_boundary(self):
        self.assertEqual(monthly([('2020-02-28', 100), ('2020-03-31', 110)], '2020-02'), {'2020-02': ('2020-02-28', 100)})
    def test_rate_lag_year_boundary(self):
        self.assertEqual(previous_month('2020-01', 3), '2019-10')

    def test_incomplete_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'manifest.json').write_text('[]')
            with self.assertRaisesRegex(ValueError, 'manifest'): build(root)
    def test_provider_resampling_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'raw/yahoo').mkdir(parents=True)
            (root/'raw/yahoo/SPY.json').write_text(json.dumps({'chart':{'result':[{'meta':{'dataGranularity':'1mo'}}]}}))
            with self.assertRaisesRegex(ValueError, 'daily'): read_series(root,'SPY')
