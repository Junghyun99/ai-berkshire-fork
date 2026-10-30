import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from saa_defense_uncertainty import block_indices, paired_differences, summarize
try:
    import numpy as np
except ModuleNotFoundError:
    np=None


@unittest.skipIf(np is None,'optional research NumPy unavailable')
class UncertaintyTests(unittest.TestCase):
    def test_wrap_block_order_length_and_seed(self):
        ix=block_indices(7,3,20,31)
        self.assertEqual(ix.shape,(20,7))
        np.testing.assert_array_equal(ix,block_indices(7,3,20,31))
        self.assertTrue(((ix>=0)&(ix<7)).all())
        for start in (0,3):
            np.testing.assert_array_equal((ix[:,start+1]-ix[:,start])%7,np.ones(20))
            np.testing.assert_array_equal((ix[:,start+2]-ix[:,start+1])%7,np.ones(20))

    def test_identical_paired_paths_zero(self):
        a=[-.03,.02,-.01,.04,-.02,.01]
        d=paired_differences(a,a,[.001]*6,block_indices(6,3,20,1))
        for v in d.values(): np.testing.assert_array_equal(v,np.zeros(20))

    def test_swapping_pairs_reverses_difference(self):
        a=[-.03,.02,-.01,.04,-.02,.01]; b=[-.01,.01,-.04,.02,-.03,.02]
        ix=block_indices(6,3,20,1)
        ab=paired_differences(a,b,[0]*6,ix);ba=paired_differences(b,a,[0]*6,ix)
        for k in ab: np.testing.assert_allclose(ab[k],-ba[k])

    def test_invalid_dimensions_and_inputs(self):
        for args in ((1,1,2,1),(7,0,2,1),(7,8,2,1),(7,2,0,1)):
            with self.assertRaises(ValueError): block_indices(*args)
        with self.assertRaises(ValueError): paired_differences([0,1],[0],[0,0],[[0,1]])
        with self.assertRaises(ValueError): paired_differences([0,float('nan')],[0,0],[0,0],[[0,1]])
        with self.assertRaises(ValueError): paired_differences([0,1],[0,0],[0,0],[[0,2]])

    def test_degenerate_replicates_disclosed(self):
        s=summarize(np.array([float('nan')]*20),0.)
        self.assertIsNone(s['percentile_95'])
        self.assertEqual(s['invalid_replicates'],20)
        self.assertEqual(s['status'],'INSUFFICIENT_VALID_REPLICATES')
