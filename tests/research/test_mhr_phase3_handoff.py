import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('handoff',ROOT/'reproduce/research/mhr_phase3_handoff.py')
handoff=importlib.util.module_from_spec(spec);spec.loader.exec_module(handoff)


class HandoffTests(unittest.TestCase):
    def test_valid_journal_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.write_bytes(b'{"valid":1}\n');before=p.read_bytes()
            self.assertIsNone(handoff.repair_final_fragment(p,Path(d)/'backup'))
            self.assertEqual(p.read_bytes(),before)

    def test_only_torn_tail_archived_and_removed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.write_bytes(b'{"valid":1}\n{"torn":');backup=Path(d)/'backup'
            result=handoff.repair_final_fragment(p,backup)
            self.assertEqual(p.read_bytes(),b'{"valid":1}\n');self.assertEqual(backup.read_bytes(),b'{"torn":')
            self.assertEqual(result['new_bytes'],12)

    def test_middle_corruption_never_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.write_bytes(b'{bad}\n{"valid":1}\n');before=p.read_bytes()
            with self.assertRaises(ValueError):handoff.repair_final_fragment(p,Path(d)/'backup')
            self.assertEqual(p.read_bytes(),before)

    def test_live_owner_refuses_repair(self):
        with patch.object(handoff,'alive',return_value=True),self.assertRaises(RuntimeError):
            handoff.verify_repair({'journals':{}},ROOT,ROOT,[55])


if __name__=='__main__':unittest.main()
