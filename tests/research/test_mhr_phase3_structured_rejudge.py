"""Synthetic tests: strict schema, persistent budget, checkpoint and no result selection."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from reproduce.research import mhr_phase3_structured_rejudge as r


class Backend:
    def __init__(self, replies):
        self.replies = iter(replies); self.calls = 0

    async def complete(self, model, prompt):
        self.calls += 1
        return next(self.replies)


def response(label):
    return {"ok": True, "raw": json.dumps({"label": label}), "finish_reason": "stop", "response_model": "model", "requests": []}


class StructuredTests(unittest.TestCase):
    def test_exact_schema_only(self):
        self.assertEqual(r.parse_response('{"label":"neither"}'), 'neither')
        for raw in ('error', '{"label":"inaccurate"}', '{"label":"error","explanation":"x"}',
                    '{"label":"accurate","label":"error"}', '[]', '{"label":null}', '```json\n{"label":"error"}\n```'):
            self.assertIsNone(r.parse_response(raw))

    def test_all_slots_first_valid_and_resume_no_calls(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); identity = {'model':'model','passes':[1,2,3],'query_id':'q','seed':101,'config':'C1'}
            backend = Backend([response('neither'),response('accurate'),response('error')])
            self.assertEqual(asyncio.run(r.execute_slots(out,identity,'same prompt',backend)),0)
            self.assertEqual(backend.calls,3)
            self.assertEqual(asyncio.run(r.execute_slots(out,identity,'same prompt',Backend([]))),0)
            votes=r.read_json(out/'NEW_VALID_VOTES.json')['votes']
            self.assertEqual([v['label'] for v in votes],['neither','accurate','error'])

    def test_budget_persists_across_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); identity={'model':'model','passes':[1,2,3]}
            failed={'ok':False,'http_status':400,'error_type':'BadRequestError','requests':[]}
            self.assertEqual(asyncio.run(r.execute_slots(out,identity,'x',Backend([failed]))),2)
            self.assertEqual(asyncio.run(r.execute_slots(out,identity,'x',Backend([failed]))),2)
            backend=Backend([])
            self.assertEqual(asyncio.run(r.execute_slots(out,identity,'x',backend)),2)
            self.assertEqual(backend.calls,0)
            self.assertEqual(r.ledger_state(r.journal(out/'events.jsonl'),r.digest(identity))['reserved_total'],2)

    def test_dispatch_reservation_counts_even_if_response_lost(self):
        ident='hash'; event={'event':'dispatch_reserved','pass':1,'attempt':1,'identity_sha256':ident}
        state=r.ledger_state([event],ident)
        self.assertEqual(state['used'][1],1)
        self.assertEqual(state['unresolved_dispatches'],[(1,1)])

    def test_reject_duplicate_or_wrong_identity(self):
        event={'event':'dispatch_reserved','pass':1,'attempt':1,'identity_sha256':'hash'}
        with self.assertRaises(ValueError):r.ledger_state([event,event],'hash')
        with self.assertRaises(ValueError):r.ledger_state([event],'other')

    def test_truncated_ledger_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.jsonl';p.write_text('{"event":')
            with self.assertRaises(ValueError):r.journal(p)

    def test_http_schema_not_freeform(self):
        self.assertEqual(r.FORMAT['json_schema']['schema']['properties']['label']['enum'],list(r.LABELS))
        self.assertFalse(r.FORMAT['json_schema']['schema']['additionalProperties'])


if __name__=='__main__':unittest.main()
