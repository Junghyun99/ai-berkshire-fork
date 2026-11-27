import unittest
from decimal import Decimal as D

from verify import compare


class RiskReviewTest(unittest.TestCase):
    def run_case(self, shock="30", budget="2.5", cash="4"):
        return compare({"A": D(4), "B": D(4)}, "C", D(4), D(cash),
                       {"A": D(30), "B": D(10), "C": D(shock)}, D(budget))

    def test_partial_entry(self):
        self.assertEqual(self.run_case(), tuple(map(D, ("1.6", "4", "2.8", "3", "2.5"))))

    def test_exhausted_budget(self):
        self.assertEqual(self.run_case(budget="1")[3:], (0, D("1.6")))

    def test_cash_limits_both_strategies(self):
        self.assertEqual(self.run_case(cash="2")[1:4], (2, D("2.2"), 2))

    def test_no_added_exposure(self):
        self.assertEqual(self.run_case(shock="0")[3:], (4, D("1.6")))
