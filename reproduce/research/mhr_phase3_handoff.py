"""Offline journal checkpoint guard for a controlled Phase 3 process handoff."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from reproduce.research.mhr_phase3.common import alive,now
from reproduce.research.recover_mhr_phase3_windows import write_status


def digest(data):return hashlib.sha256(data).hexdigest()


def journals(root):
    paths=[]
    for seed in [101,202,303]:
        folder=root/'qa'/f's{seed}'
        paths.extend([folder/f'kw_s{seed}.jsonl',folder/'requests.jsonl'])
        for c in ['C0','C1']:
            part=folder/f'{c}_s{seed}'
            paths.extend(part/name for name in ['answers.jsonl','requests.jsonl','contexts.jsonl','context.jsonl','judge/judge.jsonl'])
        for i in range(3):
            part=folder/f'worker{i}'
            paths.append(part/'pairs.jsonl')
            for c in ['C0','C1']:
                paths.extend(part/f'{c}_s{seed}'/name for name in ['contexts.jsonl','context.jsonl'])
    return [p for p in paths if p.exists()]


def repair_final_fragment(path,backup):
    data=path.read_bytes();parts=data.splitlines(keepends=True);offset=0
    for i,line in enumerate(parts):
        try:
            if line.strip():json.loads(line)
        except (json.JSONDecodeError,UnicodeDecodeError):
            if i!=len(parts)-1:raise ValueError('Refuse to alter corruption inside a journal') from None
            backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(data[offset:])
            with path.open('r+b') as f:f.truncate(offset)
            return {'old_bytes':len(data),'new_bytes':offset,'archived_tail':str(backup),'tail_sha256':digest(data[offset:])}
        offset+=len(line)
    return None


def capture(root):
    result={}
    for p in journals(root):
        data=p.read_bytes();end=data.rfind(b'\n')+1
        result[str(p.relative_to(root))]={'complete_prefix_bytes':end,'complete_prefix_sha256':digest(data[:end]),
                                        'observed_bytes':len(data)}
    return {'at':now(),'run_root':str(root),'journals':result}


def verify_repair(snapshot,root,backup,owners):
    if any(alive(p) for p in owners):raise RuntimeError('Refuse journal repair while an owner is alive')
    repaired=[]
    for rel,meta in snapshot['journals'].items():
        p=root/rel;data=p.read_bytes()
        if digest(data[:meta['complete_prefix_bytes']])!=meta['complete_prefix_sha256']:
            raise ValueError('Previously completed prefix changed: '+rel)
        repair=repair_final_fragment(p,backup/(rel.replace('/','__')+'.tail.bin'))
        if repair:repaired.append({'file':rel,**repair})
    return {'at':now(),'status':'verified','completed_prefixes_preserved':True,'repairs':repaired,
            'verified_journals':len(snapshot['journals'])}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',type=Path)
    p.add_argument('--owners',type=int,nargs='+',default=[]);a=p.parse_args()
    if a.verify:
        result=verify_repair(json.loads(a.verify.read_text(encoding='utf-8')),a.run_root,a.out.parent/'archived_tails',a.owners)
    else:result=capture(a.run_root)
    write_status(a.out,result);print(json.dumps({k:v for k,v in result.items() if k!='journals'}))


if __name__=='__main__':main()
