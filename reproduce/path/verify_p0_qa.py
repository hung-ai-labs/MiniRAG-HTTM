"""Independently validate a completed frozen-context QA run; never call APIs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[2]
ARMS = ('C0', 'C1', 'C3')
LABELS = ('accurate', 'error', 'neither')


def read(path):
    # A live worker may be appending the last line. Ignore an incomplete tail.
    text = path.read_text() if path.exists() else ''
    return [json.loads(line) for line in text.splitlines(keepends=True)
            if line.endswith('\n') and line.strip()]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else 'NONE'


def validate(directory):
    plan = json.loads((directory / 'manifest.json').read_text())
    questions = plan['questions']
    assert len(questions) == len(set(questions)) == 200
    assert tuple(plan['arms']) == ARMS
    answers = read(directory / 'answers.jsonl')
    judges = read(directory / 'judgments.jsonl')
    contexts = read(directory / 'contexts.jsonl')
    a = {(r['question'], r['variant']): r for r in answers}
    j = {(r['question'], r['variant'], r['judge_pass']): r for r in judges}
    c = {(r['question'], r['variant']): r for r in contexts}
    assert len(a) == len(answers) and len(j) == len(judges) and len(c) == len(contexts)
    expected_a = {(q, arm) for q in questions for arm in ARMS}
    expected_j = {(q, arm, p) for q in questions for arm in ARMS for p in (1, 2, 3)}
    assert set(a) <= expected_a and set(j) <= expected_j and set(c) == expected_a
    for key, record in a.items():
        assert record['generation_round'] == 1
        assert record['context_sha256'] == c[key]['context_sha256'] == sha(c[key]['context'])
    for (q, arm, _), record in j.items():
        assert record['generation_round'] == 1 and record['verdict'] in LABELS
        assert record['prediction_sha256'] == sha(a[(q, arm)]['prediction'])
    if set(a) != expected_a or set(j) != expected_j:
        progress = {'complete': False, 'answers': len(a), 'judgments': len(j),
                    'planned_answers': 600, 'planned_judgments': 1800,
                    'by_pass': dict(Counter(r['judge_pass'] for r in judges))}
        print(json.dumps(progress, indent=2))
        return False
    for name, h in plan['sources_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    for name, h in plan['index_sha256'].items():
        assert hashlib.sha256((ROOT / 'LiHua-World-qwen-modal' / name).read_bytes()).hexdigest() == h, name
    rates = {}
    for arm in ARMS:
        rates[arm] = {}
        for label in LABELS:
            values = [100 * sum(j[(q, arm, p)]['verdict'] == label for q in questions) / 200
                      for p in (1, 2, 3)]
            rates[arm][label] = {'mean': statistics.mean(values),
                                 'sd_judge': statistics.stdev(values), 'passes': values}
    majority = {}
    for q in questions:
        for arm in ARMS:
            votes = Counter(j[(q, arm, p)]['verdict'] for p in (1, 2, 3))
            label, n = votes.most_common(1)[0]
            majority[(q, arm)] = label if n >= 2 else 'neither'
    paired = {}
    for arm in ('C0', 'C1'):
        up = sum(majority[(q, arm)] != 'accurate' and majority[(q, 'C3')] == 'accurate' for q in questions)
        down = sum(majority[(q, arm)] == 'accurate' and majority[(q, 'C3')] != 'accurate' for q in questions)
        paired[arm] = {'n': 200, 'up': up, 'down': down, 'net': up - down,
                       'p_exact': float(binomtest(up, up + down).pvalue) if up + down else 1.0}
    previous = 0
    for i, arm in enumerate(sorted(paired, key=lambda k: paired[k]['p_exact'])):
        previous = min(1, max(previous, paired[arm]['p_exact'] * (2 - i)))
        paired[arm]['p_holm'] = previous
    original = json.loads((directory / 'accuracy_report.json').read_text())
    assert original['status'] == 'complete'
    for arm in ARMS:
        for label in LABELS:
            for metric in ('mean', 'sd_judge'):
                assert abs(original['rates_mean_judge_sd'][arm][label][metric] - rates[arm][label][metric]) < 1e-12
    for arm, values in paired.items():
        for key, value in values.items():
            assert abs(original['majority_paired']['All'][arm][key] - value) < 1e-12
    result = {'complete': True, 'questions': 200, 'answers': 600, 'judgments': 1800,
              'rates': rates, 'C3_vs_majority': paired, 'original_report_matches': True,
              'hashes_unchanged': True, 'generation_rounds': 1,
              'configuration_gain_confirmed': False, 'api_calls': 0}
    (directory / 'independent_qa_validation.json').write_text(json.dumps(result, indent=2))
    lines = ['# C0/C1/C3 QA — 200 câu, ba lượt judge', '',
             'Một lượt sinh; Gemini generation/judge trên Qwen graph/parser cố định. Đây là dev, không phải benchmark SLM cuối.', '',
             '| Bản | acc | err | neither |', '|---|---:|---:|---:|']
    for arm in ARMS:
        cells = [f"{rates[arm][l]['mean']:.2f} ± {rates[arm][l]['sd_judge']:.2f}" for l in LABELS]
        lines.append('| ' + arm + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '± là sd giữa ba lượt judge, không phải giữa các lượt sinh.', '',
              'McNemar chính xác trên majority nhãn của ba judge; tie=neither:', '',
              '| C3 so với | Lên / xuống | p | p Holm |', '|---|---:|---:|---:|']
    for arm, v in paired.items():
        lines.append(f"| {arm} | {v['up']} / {v['down']} | {v['p_exact']:.6g} | {v['p_holm']:.6g} |")
    lines += ['', 'Đã đối chiếu độc lập checkpoint, hash context/prediction, index/source và báo cáo gốc.',
              'Một lượt sinh và dev đã được quan sát nhiều lần chưa xác nhận cải tiến cấu hình; cần lặp sinh và xác nhận độc lập.',
              'Đây là C3 relation-lift; source-witness/W(p) không tham gia vào lượt đo.', '']
    (directory / 'RESULTS_COMPLETE.md').write_text('\n'.join(lines))
    print(json.dumps(result, indent=2))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    raise SystemExit(0 if validate(parser.parse_args().directory) else 2)
