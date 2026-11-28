import unittest
from fractions import Fraction

from compare import allocate


class AllocationTest(unittest.TestCase):
    def test_shortage(self):
        demand = {"A": 10, "B": 30, "C": 60}
        self.assertEqual(allocate(demand, 60, "equal"), dict(A=10, B=25, C=25))
        self.assertEqual(allocate(demand, 60, "proportional"), dict(A=6, B=18, C=36))
        self.assertEqual(allocate(demand, 60, "priority", dict(A=3, B=2, C=1)),
                         dict(A=0, B=0, C=60))

    def test_tied_priority(self):
        self.assertEqual(allocate(dict(A=2, B=4, C=1), 2, "priority", dict(A=2, B=2, C=1)),
                         dict(A=Fraction(1, 3), B=Fraction(2, 3), C=1))

    def test_budget_and_permutation(self):
        for cash in (0, 1, 6, 10):
            for method in ("equal", "proportional", "priority"):
                demand = dict(A=0, B=2, C=4)
                ranks = dict(A=2, B=1, C=1)
                out = allocate(demand, cash, method, ranks)
                self.assertEqual(sum(out.values()), min(cash, 6))
                self.assertTrue(all(0 <= out[k] <= v for k, v in demand.items()))
                self.assertEqual(out, allocate(dict(reversed(list(demand.items()))), cash, method, ranks))
