import unittest
from fractions import Fraction as F

from compare import compare


class CashMatchedTest(unittest.TestCase):
    def test_original_stress(self):
        self.assertEqual(compare((-30, -10, -30), 0, 1),
                         (F(-14, 5), F(-5, 2), F(-77, 30)))

    def test_cash_interest_does_not_change_selection_spread(self):
        for cash in [0, 2]:
            _, selected, matched = compare((-30, -10, 30), cash, 1)
            self.assertEqual(selected - matched, F(-1, 3))

    def test_same_returns_remove_selection_effect(self):
        full, selected, matched = compare((-30, -30, -30), 0, 1)
        self.assertEqual(selected, matched)
        self.assertEqual(selected-full, F(3, 10))

    def test_no_reduction(self):
        full, selected, matched = compare((2, 7, -1), 0, 0)
        self.assertEqual((full, full), (selected, matched))
