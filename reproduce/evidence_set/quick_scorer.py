"""Fast scorer: zero-shot cross-encoder relevance + graph/time features, stacked by
cross-fitted logistic regression (no fine-tuning, 0 API calls, a few minutes on Mac).

Arms written to review/evidence_set_20261111/scores/:
  CE0    zero-shot cross-encoder, Platt-calibrated on the other folds
  F      logistic regression on the 18 graph/time/structure features only
  CE0+F  logistic regression on [CE logit, features]   <- main arm

Every model for fold f is fit on the other four folds only (trained_on_folds).
Hyperparameters are fixed in advance (C=1.0, no grid).

    .venv/bin/python -m reproduce.evidence_set.quick_scorer [--fit-all]
"""
import argparse
import json
import os
import pickle

import numpy as np

from reproduce.graph_ablation.study import lines, sha
from reproduce.evidence_set.features import FEATURES
from reproduce.evidence_set.pool import OUT

CE_MODEL = 'cross-encoder/ms-marco-MiniLM-L6-v2'
C = 1.0
SEED = 13
GROUPS = {'graph': ('native_rank', 'native_rank_log', 'in_native30', 'graph_rank', 'graph_score', 'graph_score_rel',
                    'in_graph', 'n_seed_paths', 'n_keyword_groups', 'is_path_head'),
          'time': ('date_match', 'time_boosted'),
          'dense': ('in_dense30', 'dense_rank'),
          'structure': ('is_continuation', 'chunk_order', 'doc_chunks', 'tokens')}
assert sorted(sum(GROUPS.values(), ())) == sorted(FEATURES)


def ce_logits(rows, chunks, cache):
    if cache.exists():
        got = json.loads(cache.read_text())
    else:
        got = {}
    need = [(r['id'], x['chunk_id']) for r in rows for x in r['candidates']
            if f"{r['id']}|{x['chunk_id']}" not in got]
    if need:
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        from sentence_transformers import CrossEncoder
        import torch
        dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
        model = CrossEncoder(CE_MODEL, device=dev, max_length=512)
        q = {r['id']: r['question'] for r in rows}
        pairs = [(q[i], chunks[c]['content']) for i, c in need]
        s = model.predict(pairs, batch_size=32, show_progress_bar=False, activation_fn=torch.nn.Identity())
        for (i, c), v in zip(need, np.asarray(s, dtype=float).ravel()):
            got[f'{i}|{c}'] = float(v)
        cache.write_text(json.dumps(got))
    return got


def matrix(rows, ce, arm, drop=()):
    keep = [k for k in FEATURES if k not in drop]
    X, y, meta = [], [], []
    for r in rows:
        for x in r['candidates']:
            f = [x['features'][k] for k in keep]
            z = ce[f"{r['id']}|{x['chunk_id']}"]
            X.append({'CE0': [z], 'F': f, 'CE0+F': [z] + f}[arm])
            y.append(x['label'])
            meta.append((r['id'], x['chunk_id'], r['fold']))
    return np.array(X, float), np.array(y), meta


def fit(X, y):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000, random_state=SEED)).fit(X, y)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fit-all', action='store_true', help='also save the all-fold models for the non-dev test')
    ap.add_argument('--ablate', action='store_true', help='leave-one-group-out CE0+F arms (CE0+F-no_<group>)')
    a = ap.parse_args()
    src = OUT / 'codex'
    man = json.loads((src / 'export_manifest.json').read_text())
    assert sha((src / 'train_dev200.jsonl').read_bytes()) == man['train_sha256'], 'export changed'
    rows = [r for r in lines(src / 'train_dev200.jsonl') if r['status'] != 'unmapped']
    every = lines(src / 'train_dev200.jsonl')
    chunks = {c['chunk_id']: c for c in lines(src / 'chunks.jsonl')}
    ce = ce_logits(every, chunks, OUT / 'ce0_logits_dev200.json')
    dest, models = OUT / 'scores', OUT / 'models'
    dest.mkdir(exist_ok=True)
    models.mkdir(exist_ok=True)
    from sklearn.metrics import roc_auc_score
    report = {'export_train_sha256': man['train_sha256'], 'pool': man['pool'], 'C': C, 'seed': SEED,
              'ce_model': CE_MODEL, 'arms': {}}
    plan = [(f'CE0+F-no_{g}', 'CE0+F', GROUPS[g]) for g in GROUPS] if a.ablate else \
        [(x, x, ()) for x in ('CE0', 'F', 'CE0+F')]
    for name, arm, drop in plan:
        Xtr, ytr, mtr = matrix(rows, ce, arm, drop)
        Xev, _, mev = matrix(every, ce, arm, drop)
        out, auc = [], {}
        for f in range(5):
            tr = np.array([m[2] != f for m in mtr])
            model = fit(Xtr[tr], ytr[tr])
            te = np.array([m[2] == f for m in mev])
            p = model.predict_proba(Xev[te])[:, 1]
            for (i, c, _), v in zip([m for m, t in zip(mev, te) if t], p):
                out.append({'id': i, 'chunk_id': c, 'p': float(v),
                            'trained_on_folds': [g for g in range(5) if g != f]})
            lab = np.array([m[2] == f for m in mtr])
            if ytr[lab].any():
                auc[f] = round(roc_auc_score(ytr[lab], model.predict_proba(Xtr[lab])[:, 1]), 4)
        with (dest / f'{name}.jsonl').open('w') as fh:
            for o in out:
                fh.write(json.dumps(o) + '\n')
        report['arms'][name] = {'auc_per_fold': auc, 'dropped': list(drop)}
        if a.fit_all:
            with (models / f'{name}_allfolds.pkl').open('wb') as fh:
                pickle.dump(fit(Xtr, ytr), fh)
        print(name, auc)
    (dest / ('quick_scorer_ablation.json' if a.ablate else 'quick_scorer_report.json')).write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
