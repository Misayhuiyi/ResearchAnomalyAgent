import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime_guard import RuntimeLease,RuntimeBusy


class RuntimeGuardTests(unittest.TestCase):
    def test_competing_owner_rejected_and_released_after_exception(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                with RuntimeLease(root):
                    with self.assertRaises(RuntimeBusy):
                        with RuntimeLease(root): pass
                    raise ValueError('simulated crash')
            with RuntimeLease(root): pass


if __name__=='__main__':unittest.main()
