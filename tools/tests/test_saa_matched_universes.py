"""Synthetic calendar fixtures only; no synthetic market observations in reports."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saa_market_data import ASSETS, month_range
try:
    from saa_matched_universes import matched_panels
except ModuleNotFoundError as exc:
    if exc.name not in ("numpy", "pandas"):
        raise
    matched_panels = None


@unittest.skipIf(matched_panels is None, "optional requirements-research.txt dependencies unavailable")
class MatchedCalendarTests(unittest.TestCase):
    def fixture(self):
        months = list(month_range('2010-01', '2016-12'))
        rf = {m: .001 for m in months}
        rows = [{'month': m, 'asset_id': a, 'return_krw': .01}
                for a in ASSETS for m in months[12 if a == 'KR_TREASURY10Y' else 0:]]
        return rows, rf

    def test_shortest_asset_controls_all_universes(self):
        months, rates, panels = matched_panels(*self.fixture())
        self.assertEqual(months[0], '2011-01')
        self.assertEqual(months[62], '2016-03')
        self.assertEqual(len(months), 72)
        for assets, panel in panels.values():
            self.assertEqual(panel.shape, (72, len(assets)))
            self.assertEqual(len(rates), 72)

    def test_interior_gap_rejected(self):
        rows, rf = self.fixture()
        rows = [r for r in rows if not (r['asset_id'] == 'KR_TREASURY10Y' and r['month'] == '2013-05')]
        with self.assertRaisesRegex(ValueError, 'missing common month'):
            matched_panels(rows, rf)

    def test_duplicate_rejected(self):
        rows, rf = self.fixture()
        rows.append(dict(rows[-1]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            matched_panels(rows, rf)

    def test_invalid_return_rejected(self):
        rows, rf = self.fixture()
        rows[-1]['return_krw'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'invalid return'):
            matched_panels(rows, rf)

    def test_short_history_rejected(self):
        rows, rf = self.fixture()
        rf = {m: v for m, v in rf.items() if m >= '2013-01'}
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            matched_panels(rows, rf)
