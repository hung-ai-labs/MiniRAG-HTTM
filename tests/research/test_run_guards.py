"""Guards added after the first LiHua smoke ran under WSL bash: wrong shell, wrong index, wrong judge path."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reproduce/research"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"reproduce/research/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ld, pq = load("launch_detached"), load("phased_qa")
LH = [{"query_id": "lh-0001"}]
MHR = [{"query_id": "mhr-0001"}]


class GuardTests(unittest.TestCase):
    def test_wsl_bash_is_refused(self):
        with self.assertRaises(SystemExit):
            ld.resolve_shell("bash", which=lambda n: r"C:\Windows\System32\bash.exe")
        with self.assertRaises(SystemExit):
            ld.resolve_shell("bash", which=lambda n: r"C:\Windows\System32\wsl.exe")
        self.assertEqual(ld.resolve_shell("bash", which=lambda n: r"E:\Git\usr\bin\bash.exe"), r"E:\Git\usr\bin\bash.exe")

    def test_questions_index_and_config_must_share_a_dataset(self):
        pq.check_family(LH, "LiHua-World-qwen-modal", "L-B2")
        pq.check_family(MHR, "indexes/multihop_rag-qwen-full609", "C1")
        for rows, index, config in ((LH, "indexes/multihop_rag-qwen-full609", None),  # the smoke mistake
                                    (MHR, "LiHua-World-qwen-modal", None),
                                    (LH, "LiHua-World-qwen-modal", "C1"),
                                    (MHR, "indexes/multihop_rag-qwen-full609", "L-B2")):
            with self.subTest(index=index, config=config), self.assertRaises(SystemExit):
                pq.check_family(rows, index, config)

    @unittest.skipUnless(os.name == "nt" or Path("/bin/bash").exists(), "needs bash")
    def test_run_phased_dev_refuses_to_judge_lihua_configs_itself(self):
        bash = ld.resolve_shell("bash") if os.name == "nt" else "/bin/bash"
        env = {k: v for k, v in os.environ.items() if k != "SKIP_JUDGE"}
        out = subprocess.run([bash, "reproduce/research/run_phased_dev.sh", "q.csv", "out", "101", "L-B2"], cwd=ROOT,
                             env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("SKIP_JUDGE", out.stderr)


if __name__ == "__main__":
    unittest.main()
