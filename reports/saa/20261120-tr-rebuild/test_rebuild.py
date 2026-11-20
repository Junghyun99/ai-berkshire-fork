import unittest
from decimal import Decimal as D
from rebuild import gross_return, rebuild, monthly, compare
class Tests(unittest.TestCase):
    def test_reinvestment_identity(self):
        # One share, USD 2 entitlement reinvested at 90 buys 2/90 shares.
        self.assertEqual(gross_return(D(100),D(90),D(2),"ex_close"),D(".92"))
        self.assertEqual(gross_return(D(100),D(90),D(2),"backward"),D(90)/98)
    def test_zero_dividend_methods_agree(self):
        self.assertEqual(gross_return(D(100),D(101),D(0),"backward"),
                         gross_return(D(100),D(101),D(0),"ex_close"))
    def test_missing_event_date_blocks(self):
        with self.assertRaises(ValueError):
            rebuild(["2020-01-01","2020-01-03"],[D(100),D(101)],{"2020-01-02":D(1)},"ex_close")
    def test_month_end_compounding(self):
        self.assertEqual(monthly(["2020-01-30","2020-01-31","2020-02-28"],
                                 [D(1),D(2),D(3)]),{"2020-02":D(".5")})
        with self.assertRaises(ValueError):monthly(["2020-01-31","2020-03-31"],[D(1),D(2)])
    def test_wealth_comparison_is_multiplicative(self):
        r=compare({"a":D(".1"),"b":D("-.1")},{"a":D(".2"),"b":D("-.2")})
        self.assertAlmostEqual(r["terminal_wealth_difference_bp"],(D(".96")/D(".99")-1)*10000,places=20)
    def test_invalid_inputs(self):
        for price in [D(0),D(-1),D("NaN")]:
            with self.assertRaises(ValueError):gross_return(price,D(1),D(0),"ex_close")
        with self.assertRaises(ValueError):rebuild(["2020-01-01","2020-01-01"],[D(1),D(1)],{},"ex_close")
if __name__=="__main__":unittest.main()
