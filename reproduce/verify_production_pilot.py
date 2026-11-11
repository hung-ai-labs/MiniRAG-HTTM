"""Verify the published QA50 table from paired rows. Offline; no model/API calls."""
import csv
import hashlib
import json
from math import comb
from pathlib import Path

RESULTS=Path(__file__).resolve().parent/'production_results'/'qa50_20261111'


def exact_p(up,down):
    n=up+down
    return min(1.,2*sum(comb(n,i) for i in range(min(up,down)+1))/2**n) if n else 1.


def verify(directory=RESULTS):
    report=json.loads((directory/'qa_report.json').read_text())
    rows=list(csv.DictReader((directory/'paired_results.csv').open(encoding='utf-8',newline='')))
    assert len(rows)==50 and len({r['id'] for r in rows})==50
    judgments={(str(r['id']),r['arm']):r for r in
               map(json.loads,(directory/'judgments.jsonl').read_text().splitlines())}
    answers={(str(r['id']),r['arm']):r for r in
             map(json.loads,(directory/'answers.jsonl').read_text().splitlines())}
    assert len(answers)==len(judgments)==100
    for field,arm in [('baseline_verdict','BASELINE'),('recomp_verdict','RECOMP_NEIGHBORS')]:
        counts={k:sum(r[field]==k for r in rows) for k in ('accurate','error','neither')}
        assert counts==report['rates'][arm]['counts']
        for row in rows:
            key=(row['id'],arm);j=judgments[key];a=answers[key]
            assert j['verdict']==row[field]
            prediction=row['baseline_prediction' if arm=='BASELINE' else 'recomp_prediction']
            assert prediction==a['prediction']
            assert hashlib.sha256(prediction.encode()).hexdigest()==j['prediction_sha256']
    for label in ('accurate','error'):
        up=sum(r['baseline_verdict']!=label and r['recomp_verdict']==label for r in rows)
        down=sum(r['baseline_verdict']==label and r['recomp_verdict']!=label for r in rows)
        expected=report['paired'][label]
        assert (up,down)==(expected['became_label'],expected['ceased_label'])
        assert exact_p(up,down)==expected['p_exact']
    return {'paired_questions':len(rows),'answers':len(answers),'judgments':len(judgments),
            'counts_labels_prediction_hashes_and_exact_p_verified':True,'API_calls':0}


if __name__=='__main__':print(json.dumps(verify(),indent=2))
