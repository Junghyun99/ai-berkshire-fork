import unittest
from analyze import regime,net_returns
class Tests(unittest.TestCase):
    def test_four_regimes_and_zero(self):
        self.assertEqual(len({regime(e,b) for e in (-1,1) for b in (-1,1)}),4)
        self.assertEqual(regime(0,0),"equity_up_bonds_up")
    def test_cost_once_multiplicative(self):
        self.assertAlmostEqual(net_returns({"gross_returns":[.1],"turnover":[1]},10)[0],.0989)
    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):net_returns({"gross_returns":[.1],"turnover":[]},10)
if __name__=="__main__":unittest.main()
