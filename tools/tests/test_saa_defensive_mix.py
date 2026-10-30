import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from saa_defensive_mix import fixed_path, fx_parts, WEIGHTS


class DefensiveMixTests(unittest.TestCase):
    def test_equity_targets_constant(self):
        for target in WEIGHTS.values():
            self.assertEqual(target[:2],[.3,.3])
            self.assertAlmostEqual(sum(target),1)

    def test_drift_and_rebalance(self):
        gross,turn,starts=fixed_path([[1.,0.],[0.,0.],[0.,0.]],[.5,.5],2)
        self.assertEqual(gross,[.5,0.,0.])
        self.assertAlmostEqual(starts[1][0],2/3)
        self.assertEqual(starts[2],[.5,.5])
        self.assertAlmostEqual(turn[2],1/3)
        self.assertEqual(turn[0],0)

    def test_zero_weight_asset_no_effect(self):
        a=fixed_path([[.1,.2],[.2,-.3]],[1.,0.],12)[0]
        self.assertEqual(a,[.1,.2])

    def test_fx_interaction(self):
        p=fx_parts(-.1,.2)
        self.assertAlmostEqual(sum(p),.08)
        self.assertAlmostEqual(p[2],-.02)

    def test_invalid_returns(self):
        for value in (-1.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                fixed_path([[value,0]],[.5,.5],12)
            with self.assertRaises(ValueError):
                fx_parts(0,value)

    def test_invalid_targets_interval_and_shape(self):
        for target in ([.6,.6],[-.1,1.1],[float('nan'),1]):
            with self.assertRaises(ValueError):
                fixed_path([[0,0]],target,12)
        with self.assertRaises(ValueError): fixed_path([[0,0]],[.5,.5],0)
        with self.assertRaises(ValueError): fixed_path([[0]],[.5,.5],12)
