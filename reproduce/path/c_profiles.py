"""Current C0/C1/C2/C3 profiles. Historical C arms are not selectable here."""
import argparse
import json
import os

VERSION='20261109-p0-relation-lift'
PROFILES=('C0','C1','C2','C3')
DESCRIPTIONS={
    'C0':'MiniRAG project baseline; same answer-type fix and A1@4000',
    'C1':'Graph provenance + added query affinity; P0 local selection, no score flow',
    'C2':'Exactly C1 candidates + P0 score flow calibrated to local mean one',
    'C3':'Experimental P0 relation-conditioned path scoring, structural background, fixed C1 candidates',
}
# These are provenance keys in immutable output files, not accepted profile names.
REFERENCE_KEYS={'C0':'C0','C1':'C1_affinity','C2':'P0_fixed_mean','C3':'C3'}


def profile_env(name):
    if name not in PROFILES:
        raise ValueError(f'Unknown current profile {name!r}; choose C0, C1, C2 or C3')
    flow=name in ('C2','C3')
    return {
        'MINIRAG_ANSWER_TYPE_FIX':'1',
        'MINIRAG_PATH2CHUNK_FIX':'0' if name=='C0' else '1',
        'MINIRAG_PATH_PROJECTION':'' if name=='C0' else 'p0_relation_lift' if name=='C3' else 'affinity',
        'MINIRAG_PATH_SELECTION':'c1_affinity' if flow else '',
        'MINIRAG_PATH_SCORE_FLOW':str(int(flow)),
        'MINIRAG_PATH_SCORE_CALIBRATION':'local_mean' if name=='C2' else '',
        'MINIRAG_PATH_SCORE':'',
        'MINIRAG_PATH_SCORE_NORMALIZATION':'',
        'MINIRAG_P2_ENHANCE':'','MINIRAG_GRAPH_FLOW':'','MINIRAG_GRAPH_FLOW_CANDIDATES':'semantic',
        'MINIRAG_PATH_PRUNE':'','MINIRAG_CHUNK_CUT':'','MINIRAG_LEEF':'','MINIRAG_RERANK':'',
        'MINIRAG_CHUNK_FUSION':'','MINIRAG_TRUNCATE_SOURCES':'1','MINIRAG_MAX_TOKEN_TEXT_UNIT':'4000',
    }


def apply_profile(name,environ=None):
    values=profile_env(name)  # Validate before mutating the caller's environment.
    (os.environ if environ is None else environ).update(values)
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=PROFILES)
    parser.add_argument('command',nargs=argparse.REMAINDER,
        help='Optional: -- <command> <args>; no command prints managed settings only')
    args=parser.parse_args();values=profile_env(args.profile)
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:
        print(json.dumps({'version':VERSION,'profile':args.profile,
            'description':DESCRIPTIONS[args.profile],'environment':values},indent=2));return
    env=os.environ.copy();env.update(values)
    os.execvpe(command[0],command,env)


if __name__=='__main__':main()
