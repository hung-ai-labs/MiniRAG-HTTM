"""Offline synthetic fixtures test queue order, no labels altered and hard gate."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fair_judge',ROOT/'reproduce/research/mhr_phase3_fair_judge.py')
fair=importlib.util.module_from_spec(spec);spec.loader.exec_module(fair)
from reproduce.research import recover_mhr_phase3_windows as controller


def record(q,p,status='ok'):
    return {'query_id':q,'pass':p,'status':status,'label':'accurate' if status=='ok' else None,'attempts':[]}


def write_journal(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')


class FairQueueTests(unittest.TestCase):
    def test_old_retry_budget_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'judge.jsonl';rows=[record('q',1,'parse_failed') for _ in range(32)]
            write_journal(p,rows);before=p.read_bytes();s=fair.journal_state(p,['q'],1)
            self.assertEqual(s['cycles_used'],32);self.assertEqual(s['valid'],0)
            self.assertIsNone(fair.choose([{'seed':101,'config':'C1','state':s}],32))
            self.assertEqual(p.read_bytes(),before)

    def test_unseen_cohort_precedes_blocked_retry(self):
        old={'seed':101,'config':'C1','state':{'pending':[1],'unseen':0,'cycles_used':27}}
        fresh={'seed':202,'config':'C0','state':{'pending':[1],'unseen':6468,'cycles_used':0}}
        self.assertIs(fair.choose([old,fresh],32),fresh)

    def test_lower_retry_count_precedes_higher_without_label_input(self):
        a={'seed':101,'config':'C1','state':{'pending':[1],'unseen':0,'cycles_used':27}}
        b={'seed':202,'config':'C0','state':{'pending':[1],'unseen':0,'cycles_used':1}}
        self.assertIs(fair.choose([a,b],32),b)

    def test_valid_records_and_unknown_ids(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'judge.jsonl';write_journal(p,[record('q',1),record('q',2,'parse_failed')])
            s=fair.journal_state(p,['q'],3)
            self.assertEqual(s['valid'],1);self.assertEqual(s['unseen'],1)
            self.assertEqual(len(s['pending']),2)
            with self.assertRaises(ValueError):fair.journal_state(p,['other'],3)

    def test_only_torn_final_line_tolerated(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'judge.jsonl';write_journal(p,[record('q',1)])
            with p.open('a') as f:f.write('{torn')
            self.assertEqual(fair.journal_state(p,['q'],1)['valid'],1)
            p.write_text('{broken}\n'+json.dumps(record('q',1))+'\n')
            with self.assertRaises(ValueError):fair.journal_state(p,['q'],1)

    def test_fair_command_only_changes_operational_entrypoint(self):
        args=SimpleNamespace(repo=ROOT,run_root=ROOT/'synthetic',fair_judge=True)
        cmd=controller.consumer_command(args)
        self.assertTrue(cmd[1].endswith('mhr_phase3_fair_judge.py'))
        self.assertNotIn('--judgemodel',cmd)
        args.fair_judge=False
        self.assertIn('reproduce.research.mhr_phase3.judge_worker',controller.consumer_command(args))

    def test_terminal_pending_status_cannot_restart_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'JUDGE_STATUS.json').write_text('{"status":"needs_adjudication"}')
            args=SimpleNamespace(run_root=root,fair_judge=True)
            with patch.object(controller.subprocess,'Popen') as spawn:
                self.assertIsNone(controller.ensure_consumer(args,{'pid':None},Mock()))
                spawn.assert_not_called()

    def test_full_rows_settings_preserved_and_incomplete_not_completed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=root/'repo';repo.mkdir()
            q=root/'test_internal.csv';q.write_text('synthetic inputs')
            (root/'TEST_INPUT.json').write_text(json.dumps({'sha256':fair.sha(q)}))
            manifest={'seeds':[101,202],'configs':['C0'],'source_hashes':{},'test_queries':2,
                'judge_passes':3,'judge_model':'gemini-flash-lite-latest','judge_concurrency':4,
                'invalid_tries':3,'outer_resume_limit':32,'valid_judge_votes':12}
            (root/'RUN_MANIFEST.json').write_text(json.dumps(manifest))
            for seed in [101,202]:
                folder=root/f'qa/s{seed}/C0_s{seed}';folder.mkdir(parents=True)
                a=folder/'answers.csv';a.write_text('synthetic answers')
                (root/f'READY_s{seed}.json').write_text(json.dumps({'questions_sha256':fair.sha(q),'answers':{'C0':fair.sha(a)}}))
            old=[record(qid,p) for qid in ['a','b'] for p in [1,2,3] if (qid,p)!=('b',3)]
            old += [record('b',3,'parse_failed') for _ in range(32)]
            oldpath=root/'qa/s101/C0_s101/judge/judge.jsonl';write_journal(oldpath,old);before=oldpath.read_bytes()
            def parser():
                p=argparse.ArgumentParser()
                for name in ['questions','answers','run-dir']:p.add_argument('--'+name,type=Path)
                p.add_argument('--judgemodel');p.add_argument('--passes',type=int)
                p.add_argument('--concurrency',type=int);p.add_argument('--invalid-tries',type=int)
                p.set_defaults(column='minirag',seed=13)
                return p
            invocations=[]
            async def run(args,rows,complete):
                invocations.append((args,rows))
                self.assertEqual(len(rows),2);self.assertEqual(args.prompt,'FROZEN PROMPT')
                self.assertEqual((args.passes,args.concurrency,args.invalid_tries,args.seed),(3,4,3,13))
                self.assertEqual(args.judgemodel,'gemini-flash-lite-latest')
                write_journal(args.run_dir/'judge.jsonl',[record(qid,p) for qid in ['a','b'] for p in [1,2,3]])
                return 0
            judge=SimpleNamespace(parser=parser,require_gemini_endpoint=Mock(),
                load_rows=lambda *a:[{'query_id':'a'},{'query_id':'b'}],run=run)
            modules={'dotenv':SimpleNamespace(load_dotenv=Mock()),
                'minirag.llm.gemini':SimpleNamespace(gemini_complete_if_cache=Mock(side_effect=AssertionError('No network permitted in test'))),
                'minirag.prompt':SimpleNamespace(PROMPTS={'fail_response':'fail'}),
                'Step_2_evaluate':SimpleNamespace(JUDGE_PROMPT='FROZEN PROMPT'),
                'llm_trace':SimpleNamespace(install=Mock())}
            with patch.dict(sys.modules,modules),patch.object(fair,'load_repo'),patch.object(fair,'load_judge',return_value=judge),patch.object(fair,'source_hashes',return_value={}):
                result=asyncio.run(fair.consume(SimpleNamespace(repo=repo,run_root=root)))
            self.assertEqual(result,2);self.assertEqual(len(invocations),1)
            self.assertIn('s202',str(invocations[0][0].answers))
            status=json.loads((root/'JUDGE_STATUS.json').read_text())
            self.assertEqual(status['status'],'needs_adjudication');self.assertEqual(status['valid_votes'],11)
            self.assertEqual(oldpath.read_bytes(),before)
            pending=json.loads((root/'PENDING_JUDGE_SLOTS.json').read_text())
            self.assertEqual(len(pending['pending_ready_slots']),1)


if __name__=='__main__':unittest.main()
