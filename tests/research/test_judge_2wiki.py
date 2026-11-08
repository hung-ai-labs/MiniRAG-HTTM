"""Offline judge contract and ID/alias safety tests; never call a provider."""
import asyncio
import ast
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reproduce/research'))
import judge_2wiki as judge


def test_registered_prompt_is_preserved_with_aliases_only():
    source = Path(__file__).resolve().parents[2] / 'reproduce/Step_2_evaluate.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    original = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'JUDGE_PROMPT' for t in n.targets))
    values = {'question': 'Synthetic spouse?', 'gold': 'Person A', 'pred': 'I do not know.'}
    rendered = judge.RUBRIC.format(**values, accepted_aliases='["Alias A"]')
    assert rendered.startswith(original.format(**values))
    assert 'Alias A' in rendered[len(original.format(**values)):]
    assert 'Judge the whole answer' not in judge.RUBRIC
    assert judge.RUBRIC_VERSION == '2wiki-upstream-aliases-v2'


def test_invalid_judgments_are_not_converted_to_neither():
    for raw in ['inaccurate', 'accurate or error', 'not accurate', '', 'accurate because yes']:
        assert judge.parse_label(raw) is None
    assert judge.parse_label(' **Accurate.** ') == 'accurate'
    async def call(prompt):
        return 'inaccurate'
    result = asyncio.run(judge.verdict(call, 'fixture'))
    assert result['status'] == 'parse_failed' and result['label'] is None
    assert len(result['attempts']) == 3


def fixture(tmp_path):
    questions = tmp_path / 'questions.csv'
    with questions.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['query_id', 'Question', 'Gold Answer', 'Type'])
        w.writeheader()
        # Duplicate question text is deliberate: joins must use IDs.
        w.writerows([{'query_id': q, 'Question': 'Same question?', 'Gold Answer': q, 'Type': 'comparison'} for q in ['a', 'b']])
    gold, answers = tmp_path / 'gold.jsonl', tmp_path / 'answers.jsonl'
    gold.write_text(''.join(json.dumps({'query_id': q, 'answer': q, 'aliases': [q, q.upper()]})+'\n' for q in ['a', 'b']), encoding='utf-8')
    answers.write_text(''.join(json.dumps({'query_id': q, 'answer': q.upper()})+'\n' for q in ['b', 'a']), encoding='utf-8')
    return questions, gold, answers


def test_exact_id_coverage_and_aliases(tmp_path):
    q, g, a = fixture(tmp_path)
    rows, gold, answers = judge.inputs(q, g, a)
    assert gold['a']['aliases'] == ['a', 'A'] and answers['a']['answer'] == 'A'
    a.write_text(json.dumps({'query_id': 'a', 'answer': 'A'})+'\n', encoding='utf-8')
    with pytest.raises(ValueError, match='cover exactly'):
        judge.inputs(q, g, a)


def test_three_pass_checkpoint_resume_and_metrics_compatibility(tmp_path):
    q, g, a = fixture(tmp_path)
    rows, gold, answers = judge.inputs(q, g, a)
    out = tmp_path / 'judge'
    out.mkdir()
    calls = []
    async def call(prompt):
        calls.append(prompt)
        assert 'accepted_aliases' in prompt
        return 'accurate'
    args = SimpleNamespace(out=out, concurrency=2)
    assert asyncio.run(judge.run(args, rows, gold, answers, call)) == 0
    assert len(calls) == 6
    assert asyncio.run(judge.run(args, rows, gold, answers, call)) == 0
    assert len(calls) == 6
    verdicts = judge.metrics.read_csv(out / 'per_question.csv')
    prepared, _, _ = judge.metrics.prepare(rows, verdicts, '101')
    assert len(prepared) == 2


def test_torn_checkpoint_refused(tmp_path):
    q, g, a = fixture(tmp_path)
    rows, gold, answers = judge.inputs(q, g, a)
    (tmp_path / 'judge.jsonl').write_bytes(b'{')
    async def call(prompt):
        raise AssertionError('No requests allowed for invalid checkpoint')
    with pytest.raises(ValueError, match='Torn'):
        asyncio.run(judge.run(SimpleNamespace(out=tmp_path, concurrency=1), rows, gold, answers, call))
