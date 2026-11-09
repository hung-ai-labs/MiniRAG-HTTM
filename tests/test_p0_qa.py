"""Matched QA cohorts and exact reporting; no model/API calls."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reproduce/path'))
from run_p0_qa import ARMS,append,summarize


class P0QAReportingTest(unittest.TestCase):
    def test_partial_uses_only_matched_questions(self):
        rows=[{'Question':'q1','Type':'Single'},{'Question':'q2','Type':'Multi'}]
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            for a,v in zip(ARMS,('error','error','accurate')):
                append(out/'judgments.jsonl',{'question':'q1','variant':a,'judge_pass':1,'verdict':v})
            append(out/'judgments.jsonl',{'question':'q2','variant':'C3','judge_pass':1,'verdict':'accurate'})
            r=summarize(out,rows)
        self.assertEqual(r['status'],'partial')
        self.assertEqual(r['passes']['1']['paired_questions'],1)
        self.assertEqual(r['passes']['1']['rates']['C3']['accurate'],100)

    def test_independent_passes_majority_and_three_labels(self):
        rows=[{'Question':'q1','Type':'Null'}]
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            for a,votes in {'C0':('error','error','accurate'),
                            'C1':('accurate','error','neither'),
                            'C3':('accurate','accurate','error')}.items():
                for j,v in enumerate(votes,1):
                    append(out/'judgments.jsonl',{'question':'q1','variant':a,'judge_pass':j,'verdict':v})
            r=summarize(out,rows)
        self.assertEqual(r['status'],'complete')
        self.assertEqual(r['majority_rates']['All']['C1']['neither'],100)
        self.assertEqual(r['majority_paired']['All']['C0']['up'],1)
        self.assertEqual(r['majority_paired']['All']['C0']['down'],0)
        self.assertAlmostEqual(r['rates_mean_judge_sd']['C3']['accurate']['mean'],200/3)
        self.assertGreater(r['rates_mean_judge_sd']['C3']['accurate']['sd_judge'],0)
        self.assertFalse(r['configuration_gain_confirmed'])

    def test_duplicate_judgments_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);r={'question':'q','variant':'C0','judge_pass':1,'verdict':'accurate'}
            append(out/'judgments.jsonl',r);append(out/'judgments.jsonl',r)
            with self.assertRaises(ValueError):summarize(out,[{'Question':'q','Type':'Single'}])


if __name__=='__main__':unittest.main()
