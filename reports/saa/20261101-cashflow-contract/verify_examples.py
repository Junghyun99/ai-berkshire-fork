"""Synthetic contract arithmetic only; not a portfolio engine or market result.
Run: python3 reports/saa/20261101-cashflow-contract/verify_examples.py
"""
from fractions import Fraction as F
import unittest


class ContractArithmetic(unittest.TestCase):
    def test_deposit_twr(self):
        self.assertEqual(F(110, 100) * F(231, 210) - 1, F(21, 100))

    def test_withdrawal_twr(self):
        self.assertEqual(F(110, 100) * F(66, 60) - 1, F(21, 100))

    def test_transfer_and_transit(self):
        self.assertEqual(60 + 40, 40 + 60)
        self.assertEqual(60 + 40, 40 + 40 + 20)
        self.assertEqual(-20 + 20, 0)

    def test_fee_is_return(self):
        self.assertEqual(F(99, 100) - 1, F(-1, 100))

    def test_one_year_mwr(self):
        self.assertEqual(-100 + F(110) / (1 + F(1, 10)), 0)

    def test_multiple_irr_roots(self):
        for rate in (F(1, 10), F(1, 5)):
            self.assertEqual(-100 + F(230) / (1 + rate)
                             - F(132) / (1 + rate) ** 2, 0)

    def test_currency_paths(self):
        self.assertEqual(F(100 * 1100, 100 * 1000) - 1, F(1, 10))
        self.assertEqual(F(100, 100) - 1, 0)

    def test_dietz_approximation(self):
        self.assertEqual(F(210 - 100 - 100) / (100 + F(1, 2) * 100), F(1, 15))


if __name__ == "__main__":
    unittest.main(verbosity=2)
