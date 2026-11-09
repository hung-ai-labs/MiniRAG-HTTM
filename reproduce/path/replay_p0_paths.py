"""Independent fixed-input verification of P0 redesign and unchanged C1/C2."""
import argparse
import hashlib
import json
from pathlib import Path
from benchmark_c import ROOT,restore
from c_profiles import apply_profile,profile_env,PROFILES
from path_common import read
from minirag import operate as op


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run.resolve()
    m=json.loads((run/'manifest.json').read_text());report=json.loads((run/'report.json').read_text())
    old=ROOT/'logs/path_calibration/20261109_dev200'
    original={r['question']:r for r in read(old/'inputs.jsonl')}
    records={r['question']:r for r in read(run/'replay.jsonl')};inputs=read(run/'inputs.jsonl')
    assert report['questions']==len(m['questions'])==len(inputs)==len(records)
    assert all(profile_env(p)['MINIRAG_PATH_SCORE']=='' for p in PROFILES)
    checks=0
    for data in inputs:
        q=data['question'];baseline=original[q]
        assert data['groups']==baseline['groups'] and data['vector_ids']==baseline['vector_ids']
        assert {s:e['Path'] for s,e in data['entries'].items()}=={s:e['Path'] for s,e in baseline['entries'].items()}
        for p in ('C1','C2','C3'):
            apply_profile(p);d=data if p=='C3' else baseline
            groups=restore(d,p)
            assert op.kwd2chunk(groups,d['vector_ids'],30)==records[q]['selections'][p]['graph_top30']
            checks+=1
    assert all(digest(ROOT/n)==h for n,h in m['sources_sha256'].items())
    assert all(digest(ROOT/'LiHua-World-qwen-modal'/n)==h for n,h in m['index_sha256'].items())
    proof={'complete':True,'questions':len(inputs),'exact_rank_checks':checks,
        'exact_C1_candidate_and_vector_order_checks':len(inputs),'P2_absent_from_main_profiles':True,
        'index_and_sources_unchanged':True,'embedding_calls':0,'api_calls':0,
        'input_sha256':{n:digest(run/n) for n in ('manifest.json','inputs.jsonl','replay.jsonl','report.json','contexts.jsonl')},
        'verifier_sha256':digest(Path(__file__))}
    (run/'independent_replay_validation.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
