import unittest,statistics,math
from compare import scale_targets,simulate
class Tests(unittest.TestCase):
    def test_common_excess_vol_and_no_leverage(self):
        train=[[.02,.01],[-.03,-.01],[.04,.015],[-.01,-.005]]
        rf=[.001,.002,.001,.003]
        scaled,vols,target,scales=scale_targets({"a":[1.,0.],"b":[0.,1.]},train,rf)
        for s,w in scaled.items():
            excess=[sum(x*y for x,y in zip(w[:-1],row))+(w[-1]-1)*r for row,r in zip(train,rf)]
            self.assertAlmostEqual(statistics.stdev(excess)*math.sqrt(12),target)
            self.assertTrue(0<=scales[s]<=1);self.assertAlmostEqual(sum(w),1.)
    def test_cash_return_and_risky_only_turnover(self):
        g,t,c=simulate(["01","02"],[[0.],[0.]],[.01,.01],{"01":[0.,1.],"02":[.5,.5]})
        self.assertAlmostEqual(g[0],.01);self.assertAlmostEqual(g[1],.005)
        self.assertEqual(t,[0.,.5])
    def test_degenerate_train_rejected(self):
        with self.assertRaises(ValueError):scale_targets({"a":[1.]},[[0.],[0.]],[0.,0.])
if __name__=="__main__":unittest.main()
