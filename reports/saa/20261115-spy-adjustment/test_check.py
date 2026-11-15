import unittest
from decimal import Decimal as D
from check import diagnostic
class Tests(unittest.TestCase):
    def test_known_adjustment(self):
        # Synthetic prices: backward adjustment 1 - 2/100 = .98.
        r=diagnostic(D(100),D(99),D(98),D(99),D(2))
        self.assertEqual(r["implied_dividend_usd"],D(2))
        self.assertEqual(r["daily_return_difference_bp"],D(0))
    def test_common_scale_cancels(self):
        a=diagnostic(D(100),D(99),D(98),D(99),D(3))
        b=diagnostic(D(100),D(99),D(49),D("49.5"),D(3))
        self.assertEqual(a,b)
        self.assertGreater(a["daily_return_difference_bp"],0)
    def test_invalid_prices(self):
        with self.assertRaises(ValueError):diagnostic(D(0),D(1),D(1),D(1),D(0))
if __name__=="__main__":unittest.main()
