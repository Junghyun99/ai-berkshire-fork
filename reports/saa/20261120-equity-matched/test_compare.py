import unittest
from compare import matched,replay,EQUITY
class Tests(unittest.TestCase):
    def test_group_sum_preserved(self):
        t={"KR_EQUITY":.1,"US_SP500":.2,"US_NASDAQ100":.1,"KR_BOND":.4,"US_BOND":.2}
        m=matched(t)
        self.assertAlmostEqual(sum(m[a] for a in m if a in EQUITY),.4)
        self.assertAlmostEqual(m["KR_BOND"],.3)
        self.assertEqual(m["KR_EQUITY"],m["US_SP500"])
    def test_drift_and_turnover(self):
        g,t,e=replay(["01","02"],["KR_EQUITY","BOND"],[[1.,0.],[0.,0.]],
                     {"01":{"KR_EQUITY":.5,"BOND":.5},"02":{"KR_EQUITY":.5,"BOND":.5}})
        self.assertEqual(g,[.5,0.]);self.assertEqual(t[0],0)
        self.assertAlmostEqual(t[1],1/3)
    def test_bad_panel_rejected(self):
        with self.assertRaises(ValueError):replay(["01"],["KR_EQUITY"],[],{})
    def test_future_target_not_applied_early(self):
        with self.assertRaises(ValueError):
            replay(["01"],["KR_EQUITY"],[[0.]],{"02":{"KR_EQUITY":1.}})
if __name__=="__main__":unittest.main()
