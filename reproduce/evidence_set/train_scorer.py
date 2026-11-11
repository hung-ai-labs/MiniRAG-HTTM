"""Local-only, nested cross-fitting of whole-chunk evidence probabilities.

Full run (waits for the immutable export, then runs the reporting gate once):
  HF_HUB_OFFLINE=1 .venv/bin/python -m reproduce.evidence_set.train_scorer --wait-for-export
Schema/engineering smoke, NEVER a result:
  HF_HUB_OFFLINE=1 .venv/bin/python -m reproduce.evidence_set.train_scorer --smoke
Contract tests (no model, API, dataset or index reads):
  .venv/bin/python -m reproduce.evidence_set.train_scorer --self-test

Only chunks.jsonl, train_dev200.jsonl and their export manifest supply data.
No answer generation, external services, FriendsQA or RECOMP imports occur here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from contextlib import nullcontext
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import numpy as np
import torch
from torch.utils.checkpoint import checkpoint
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'review/evidence_set_20261111'
MODEL = 'cross-encoder/ms-marco-MiniLM-L6-v2'
REVISION = '233902d25c440f23af6f7d6e94d2946bac0bee0a'
SEED = 13
ARMS = ('F', 'CE0', 'CE', 'CE+F')
# Declared BEFORE training. Epoch checkpoints share one training trajectory.
GRID = {'learning_rates': [2e-5, 5e-5], 'epochs': [1, 2], 'negative_ratios': [8],
        'feature_C': [0.1, 1.0, 10.0], 'feature_head_lr': 1e-3,
        'pairwise_weight': 0.5, 'max_length': 512, 'document_stride': 128,
        'window_microbatch': 4, 'inference_window_microbatch': 16, 'gradient_checkpointing': True,
        'feature_weight_decay': 0.0, 'encoder_weight_decay': 0.01,
        'calibration': 'Platt, C=10; all inner-held-out candidates; equal question weights',
        'selection_metric': 'macro question AP (labelled queries, zero when no pool positive)',
        'hard_negative_rule': 'same speaker entity and query keywords, different non-null source time; '
                              'include up to 4 before random same-query negatives',
        'refit': 'outer four folds after inner choice; inner-held-out Platt transferred to refit',
        'all_fold_choice': 'modal outer choice, deterministic tie: smaller epoch/lr/C',
        'fallback_Qwen': 'not automatic; no model escalation based on the reporting gate'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    tmp.replace(path)


def lines(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def load_export(path, smoke=False, verify_upstream=True):
    m = json.loads((path / 'export_manifest.json').read_text())
    for name, key in [('chunks.jsonl', 'chunks_sha256'), ('train_dev200.jsonl', 'train_sha256')]:
        if sha(path / name) != m[key]:
            raise ValueError(f'Input SHA256 mismatch: {name}')
    chunks = {r['chunk_id']: r for r in lines(path / 'chunks.jsonl')}
    rows = lines(path / 'train_dev200.jsonl')
    if not smoke and (len(rows) != 200 or len(chunks) != 514):
        raise ValueError('Full protocol requires the final 200-question / 514-chunk export')
    if len(rows) != m['questions'] or sum(len(r['candidates']) for r in rows) != m['candidates']:
        raise ValueError('Export count mismatch')
    if not smoke and verify_upstream and sha(OUT / 'pools_dev200.jsonl') != m['pools_sha256']:
        raise ValueError('Frozen upstream pool SHA256 mismatch')
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate question id')
    features = m['features']
    docs = {}
    for r in rows:
        if r['fold'] not in range(5) or r['status'] not in ('labelled', 'null', 'unmapped'):
            raise ValueError('Invalid fold/status')
        if len({c['chunk_id'] for c in r['candidates']}) != len(r['candidates']):
            raise ValueError('Duplicate candidate')
        for c in r['candidates']:
            if c['chunk_id'] not in chunks or c['label'] not in (0, 1):
                raise ValueError('Invalid candidate/label')
            if set(c['features']) != set(features) or not all(math.isfinite(c['features'][f]) for f in features):
                raise ValueError('Feature schema mismatch/nonfinite feature')
            if r['status'] == 'null' and c['label']:
                raise ValueError('Null query has a positive label')
            if c['label']:
                d = chunks[c['chunk_id']]['doc']
                if d in docs and docs[d] != r['fold']:
                    raise ValueError('Positive conversation crosses supplied folds')
                docs[d] = r['fold']
    return m, chunks, rows


def arrays(rows, features):
    x, y, w = [], [], []
    for r in rows:
        for c in r['candidates']:
            x.append([c['features'][k] for k in features])
            y.append(c['label'])
            w.append(1 / len(r['candidates']))
    w = np.asarray(w, dtype=np.float64)
    return np.asarray(x, dtype=np.float64), np.asarray(y), w / w.mean()


def ranking_metrics(rows, scores):
    y = np.asarray([c['label'] for r in rows for c in r['candidates']])
    p = np.concatenate([scores[r['id']] for r in rows])
    aps, hits = [], []
    for r in rows:
        if r['status'] != 'labelled':
            continue
        yy = np.asarray([c['label'] for c in r['candidates']])
        ss = np.asarray(scores[r['id']])
        aps.append(float(average_precision_score(yy, ss)) if yy.sum() else 0.)
        hits.append(bool(yy[np.argsort(-ss, kind='stable')[:5]].sum()))
    bins = []
    for j in range(10):
        mask = (p >= j / 10) & (p < (j + 1) / 10 if j < 9 else p <= 1)
        bins.append({'bin': [j / 10, (j + 1) / 10], 'n': int(mask.sum()),
                     'mean_p': float(p[mask].mean()) if mask.any() else None,
                     'fraction_positive': float(y[mask].mean()) if mask.any() else None})
    return {'auc': float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
            'map': float(np.mean(aps)) if aps else None,
            'positive_in_top5': float(np.mean(hits)) if hits else None,
            'brier': float(brier_score_loss(y, p)), 'questions': len(rows),
            'labelled_queries': len(aps), 'candidates': len(y), 'positives': int(y.sum()),
            'reliability': bins}


def split_flat(rows, flat):
    out, start = {}, 0
    for r in rows:
        stop = start + len(r['candidates'])
        out[r['id']] = np.asarray(flat[start:stop], dtype=np.float64)
        start = stop
    assert start == len(flat)
    return out


def fit_linear(rows, features, C=1.0):
    x, y, w = arrays(rows, features)
    scaler = StandardScaler().fit(x, sample_weight=w)
    clf = LogisticRegression(C=C, max_iter=3000, random_state=SEED)
    clf.fit(scaler.transform(x), y, sample_weight=w)
    return {'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
            'coef': clf.coef_[0].tolist(), 'intercept': float(clf.intercept_[0]), 'C': C}


def linear_scores(rows, features, state):
    x, _, _ = arrays(rows, features)
    z = (x - state['mean']) / state['scale']
    return split_flat(rows, z @ state['coef'] + state['intercept'])


def fit_platt(rows, raw):
    z = np.concatenate([raw[r['id']] for r in rows])
    _, y, w = arrays(rows, [])
    scaler = StandardScaler().fit(z[:, None], sample_weight=w)
    clf = LogisticRegression(C=10., max_iter=3000, random_state=SEED)
    clf.fit(scaler.transform(z[:, None]), y, sample_weight=w)
    return {'mean': float(scaler.mean_[0]), 'scale': float(scaler.scale_[0]),
            'coef': float(clf.coef_[0, 0]), 'intercept': float(clf.intercept_[0])}


def calibrate(raw, state):
    def prob(x):
        z = (np.asarray(x) - state['mean']) / state['scale'] * state['coef'] + state['intercept']
        return 1 / (1 + np.exp(-np.clip(z, -700, 700)))
    return {i: prob(z) for i, z in raw.items()}


def seed_all():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)


def autocast(device):
    return torch.autocast('cuda', dtype=torch.float16) if device == 'cuda' else nullcontext()


class TextScorer(torch.nn.Module):
    """Original BERT classification head + optional linear standardized-feature head.

    This is a joint head on [pooled CLS, features]. The pretrained text head is
    preserved; the feature head starts at zero. ALL encoder weights are trained.
    A long chunk is represented by overlapping pair windows, aggregated by max.
    No chunk suffix is silently discarded.
    """
    def __init__(self, snapshot, nfeatures=0):
        super().__init__()
        self.encoder = AutoModelForSequenceClassification.from_pretrained(snapshot, local_files_only=True)
        self.feature_head = torch.nn.Linear(nfeatures, 1, bias=False) if nfeatures else None
        if self.feature_head is not None:
            torch.nn.init.zeros_(self.feature_head.weight)

    def forward(self, batch, groups, features):
        keys = list(batch)

        def encode(*values):
            return self.encoder(**dict(zip(keys, values))).logits.flatten()

        pieces = []
        width = GRID['window_microbatch'] if self.training and torch.is_grad_enabled() else GRID['inference_window_microbatch']
        for start in range(0, batch['input_ids'].shape[0], width):
            values = tuple(batch[k][start:start + width] for k in keys)
            if self.training and torch.is_grad_enabled():
                pieces.append(checkpoint(encode, *values, use_reentrant=False, preserve_rng_state=True))
            else:
                pieces.append(encode(*values))
        logits = torch.cat(pieces)
        out = torch.stack([logits[a:b].max() for a, b in groups])
        if self.feature_head is not None:
            out = out + self.feature_head(features).flatten()
        return out


class Pairs:
    def __init__(self, rows, chunks, tokenizer, features, max_length, stride):
        self.rows, self.chunks, self.tokenizer, self.features = rows, chunks, tokenizer, features
        self.tokens, self.hard = {}, {}
        self.windows = Counter()
        words = lambda s: set(re.findall(r'[a-z]{3,}', s.lower()))
        speakers = {cid: {m.strip().lower() for m in re.findall(r'^([^:\n]{1,60}):', c['content'], re.M)
                          if m.strip().lower() not in ('time', 'date')} for cid, c in chunks.items()}
        for r in rows:
            qid = r['id']
            positive = [c['chunk_id'] for c in r['candidates'] if c['label']]
            ps = [speakers[c] for c in positive if speakers[c]]
            pt = {chunks[c]['time'] for c in positive if chunks[c]['time'] is not None}
            hard = []
            for j, c in enumerate(r['candidates']):
                cid = c['chunk_id']
                enc = tokenizer(r['question'], chunks[cid]['content'], max_length=max_length,
                                truncation='only_second', stride=stride, return_overflowing_tokens=True)
                n = len(enc['input_ids'])
                self.windows[n] += 1
                self.tokens[qid, j] = [{k: enc[k][w] for k in tokenizer.model_input_names if k in enc}
                                       for w in range(n)]
                same_participants = any(len(s & speakers[cid]) >= min(2, len(s)) for s in ps)
                if (not c['label'] and same_participants and chunks[cid]['time'] is not None
                        and chunks[cid]['time'] not in pt
                        and len(words(r['question']) & words(chunks[cid]['content'])) >= 2):
                    hard.append(j)
            self.hard[qid] = sorted(hard, key=lambda j: -len(words(r['question']) &
                                      words(chunks[r['candidates'][j]['chunk_id']]['content'])))

    def batch(self, r, indices, mean, scale, device):
        windows, groups = [], []
        for j in indices:
            start = len(windows)
            windows.extend(self.tokens[r['id'], j])
            groups.append((start, len(windows)))
        batch = self.tokenizer.pad(windows, padding=True, return_tensors='pt')
        feat = np.asarray([[r['candidates'][j]['features'][f] for f in self.features] for j in indices])
        feat = (feat - mean) / scale
        return ({k: v.to(device) for k, v in batch.items()}, groups,
                torch.tensor(feat, dtype=torch.float32, device=device))

    def sample(self, r, ratio, rng):
        pos = [i for i, c in enumerate(r['candidates']) if c['label']]
        neg = [i for i, c in enumerate(r['candidates']) if not c['label']]
        count = min(len(neg), ratio * max(len(pos), 1))
        hard = self.hard[r['id']]
        # Rotate hard examples between visits while always including one if present.
        nh = min(4, count, len(hard))
        chosen = rng.sample(hard[:max(4, len(hard))], nh) if nh else []
        left = [j for j in neg if j not in chosen]
        chosen += rng.sample(left, count - len(chosen))
        return pos + chosen


def standardize(rows, features):
    x, _, w = arrays(rows, features)
    s = StandardScaler().fit(x, sample_weight=w)
    return s.mean_, s.scale_


@torch.no_grad()
def predict(model, rows, pairs, mean, scale, device):
    model.eval()
    out = {}
    for qi, r in enumerate(rows):
        score = []
        width = 32 if device == 'cuda' else 8
        for a in range(0, len(r['candidates']), width):
            js = list(range(a, min(a + width, len(r['candidates']))))
            with autocast(device):
                value = model(*pairs.batch(r, js, mean, scale, device))
            score.extend(value.float().cpu().tolist())
        out[r['id']] = np.asarray(score)
        if (qi + 1) % 20 == 0:
            print(json.dumps({'stage': 'forward_only', 'questions_completed': qi + 1,
                              'questions_total': len(rows)}), flush=True)
    return out


def fit_text(snapshot, rows, validation, pairs, features, device, arm, lr, epochs,
             ratio, run_dir, select_epochs=None, max_steps=None):
    seed_all()
    mean, scale = standardize(rows, features)
    model = TextScorer(snapshot, len(features) if arm == 'CE+F' else 0).to(device)
    groups = [{'params': model.encoder.parameters(), 'lr': lr, 'weight_decay': GRID['encoder_weight_decay']}]
    if model.feature_head is not None:
        groups.append({'params': model.feature_head.parameters(), 'lr': GRID['feature_head_lr'], 'weight_decay': 0.})
    opt = torch.optim.AdamW(groups)
    scaler = torch.amp.GradScaler('cuda', enabled=device == 'cuda')
    history, best, best_state, best_raw, steps, total_seconds = [], None, None, None, 0, time.monotonic()
    for epoch in range(1, epochs + 1):
        rng = random.Random(SEED + epoch)
        shuffled = list(rows)
        rng.shuffle(shuffled)
        model.train()
        losses, hard_batches = [], 0
        for r in shuffled:
            indices = pairs.sample(r, ratio, rng)
            hard_batches += bool(set(indices) & set(pairs.hard[r['id']]))
            opt.zero_grad(set_to_none=True)
            with autocast(device):
                logits = model(*pairs.batch(r, indices, mean, scale, device))
            logits = logits.float()
            labels = torch.tensor([r['candidates'][j]['label'] for j in indices], device=device, dtype=torch.float32)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
            pos, neg = logits[labels > 0], logits[labels == 0]
            if pos.numel() and neg.numel():
                loss = loss + GRID['pairwise_weight'] * torch.nn.functional.softplus(neg[:, None] - pos[None, :]).mean()
            if not torch.isfinite(loss).item():
                raise RuntimeError(f'Nonfinite loss: {arm}, epoch={epoch}, question={r["id"]}')
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            scaler.step(opt)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
            steps += 1
            if steps % 25 == 0:
                print(json.dumps({'stage': str(run_dir), 'arm': arm, 'epoch': epoch,
                                  'training_steps_completed': steps}), flush=True)
            if max_steps and steps >= max_steps:
                break
        record = {'epoch': epoch, 'steps': steps, 'loss': float(np.mean(losses)),
                  'batches_with_different_time_hard_negatives': hard_batches}
        raw = predict(model, validation, pairs, mean, scale, device) if validation else None
        if raw is not None:
            metric = ranking_metrics(validation, {i: 1 / (1 + np.exp(-np.clip(z, -60, 60))) for i, z in raw.items()})
            record['inner_map'] = metric['map']
        eligible = select_epochs is None or epoch in select_epochs
        value = record.get('inner_map', 0.)
        if eligible and (best is None or value > best['inner_map']):
            best = {'lr': lr, 'epochs': epoch, 'negative_ratio': ratio, 'inner_map': value}
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_raw = raw
        history.append(record)
        print(json.dumps({'stage': str(run_dir), 'arm': arm, **record}), flush=True)
        if max_steps and steps >= max_steps:
            break
    assert best_state is not None
    model.load_state_dict(best_state)
    run_dir.mkdir(parents=True, exist_ok=True)
    torch.save({'state_dict': best_state, 'mean': mean.tolist(), 'scale': scale.tolist(),
                'arm': arm, 'choice': best, 'features': features, 'base_revision': REVISION}, run_dir / 'model.pt')
    dump(run_dir / 'history.json', {'history': history, 'choice': best, 'seconds': time.monotonic() - total_seconds})
    return model, mean, scale, best, best_raw


def write_scores(path, rows, scores, provenance):
    tmp = path.with_suffix('.jsonl.tmp')
    count = 0
    with tmp.open('w') as f:
        for r in rows:
            ps = scores[r['id']]
            assert len(ps) == len(r['candidates'])
            folds = provenance[r['id']]
            assert r['fold'] not in folds
            for c, p in zip(r['candidates'], ps):
                assert np.isfinite(p) and 0 <= p <= 1
                f.write(json.dumps({'id': r['id'], 'chunk_id': c['chunk_id'], 'p': float(p),
                                    'trained_on_folds': folds}) + '\n')
                count += 1
    tmp.replace(path)
    assert count == sum(len(r['candidates']) for r in rows)


def release(model, device):
    model.to('cpu')
    del model
    import gc
    gc.collect()
    if device == 'mps':
        torch.mps.empty_cache()


def run(args):
    start = time.monotonic()
    source = OUT / ('codex_preview' if args.smoke else 'codex')
    deadline = start + args.wait_minutes * 60
    while not (source / 'export_manifest.json').exists():
        if not args.wait_for_export or time.monotonic() >= deadline:
            raise SystemExit(f'Final export not ready: {source}. Use --smoke for preview; no final results fabricated.')
        print('Waiting for final codex/export_manifest.json; no indexing/model calls.', flush=True)
        time.sleep(30)
    manifest, chunks, all_rows = load_export(source, args.smoke, verify_upstream=not args.defer_gate)
    dest = OUT / ('smoke_scorer' if args.smoke else 'scores')
    models = dest / 'models' if args.smoke else OUT / 'models'
    if (dest / 'protocol.json').exists():
        raise SystemExit(f'Refusing to overwrite a started run: {dest}. Review its progress before resuming.')
    dest.mkdir(parents=True, exist_ok=True)
    # The exporter can still be used by another researcher. Read an immutable
    # copy throughout this run rather than silently mixing exports mid-training.
    original_source = source
    source = dest / 'inputs'
    source.mkdir(exist_ok=True)
    for name in ('chunks.jsonl', 'train_dev200.jsonl', 'export_manifest.json'):
        shutil.copy2(original_source / name, source / name)
    frozen_manifest, _, _ = load_export(source, args.smoke, verify_upstream=not args.defer_gate)
    assert frozen_manifest == manifest, 'Export changed while making the immutable run snapshot'
    device = args.device or ('mps' if torch.backends.mps.is_available() else 'cpu')
    if device == 'cuda':
        GRID['window_microbatch'] = 8
        GRID['inference_window_microbatch'] = 64
    torch.set_num_threads(args.threads)
    snapshot = Path.home() / '.cache/huggingface/hub' / ('models--' + MODEL.replace('/', '--')) / 'snapshots' / REVISION
    if not snapshot.is_dir():
        raise SystemExit(f'Pinned model not cached: {snapshot}; offline-only run refuses download')
    grid = copy.deepcopy(GRID)
    if args.smoke:
        grid.update(learning_rates=[2e-5], epochs=[1], negative_ratios=[4])
    hashes = {name: sha(source / name) for name in ('chunks.jsonl', 'train_dev200.jsonl', 'export_manifest.json')}
    protected = {'baseline.yaml': sha(ROOT / 'baseline.yaml')}
    for p in (ROOT / 'minirag').rglob('*.py'):
        protected[str(p.relative_to(ROOT))] = sha(p)
    for p in (ROOT / 'reproduce/evidence_set').glob('*.py'):
        if p.name != 'train_scorer.py':
            protected[str(p.relative_to(ROOT))] = sha(p)
    protocol = {'seed': SEED, 'smoke_NOT_A_RESULT': args.smoke, 'grid': grid, 'input_hashes': hashes,
                'export_manifest': manifest, 'model': MODEL, 'revision': REVISION,
                'model_files': {p.name: sha(p) for p in snapshot.iterdir()
                                if p.name in ('model.safetensors', 'pytorch_model.bin', 'config.json', 'tokenizer.json')},
                'source_sha256': sha(Path(__file__)), 'hardware': platform.platform(), 'device': device,
                'input_snapshot': str(source), 'original_export': str(original_source),
                'torch': torch.__version__, 'threads': args.threads,
                'precision': 'CUDA mixed fp16 / fp32 loss and parameters' if device == 'cuda' else 'fp32',
                'dependencies': {n: version(n) for n in ('transformers', 'scikit-learn', 'numpy', 'tokenizers')},
                'excluded_from_learning': [r['id'] for r in all_rows if r['status'] == 'unmapped'],
                'protected_hashes': protected, 'api_calls': 0}
    dump(dest / 'protocol.json', protocol)
    rows = [r for r in all_rows if r['status'] != 'unmapped']
    features = manifest['features']
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    pairs = Pairs(all_rows, chunks, tokenizer, features, grid['max_length'], grid['document_stride'])
    dump(dest / 'tokenization.json', {'window_histogram': dict(pairs.windows),
                                     'candidates_with_hard_negatives': sum(bool(v) for v in pairs.hard.values()),
                                     'truncated_chunk_suffixes': 0, 'aggregation': 'max over overlapping windows'})
    raw_all, prob_all, provenance, choices, metrics = ({a: {} for a in ARMS} for _ in range(5))
    folds_to_run = [0] if args.smoke else list(range(5))
    # CE0 encoder is identical across folds: cache forward passes, calibrate separately.
    ce0 = TextScorer(snapshot).to(device)
    zeros, ones = np.zeros(len(features)), np.ones(len(features))
    raw_ce0 = predict(ce0, all_rows, pairs, zeros, ones, device)
    protocol['encoder_parameters'] = sum(p.numel() for p in ce0.parameters())
    dump(dest / 'protocol.json', protocol)
    release(ce0, device)
    for fold in folds_to_run:
        outer = [r for r in rows if r['fold'] != fold]
        inner_fold = (fold + 1) % 5
        inner = [r for r in outer if r['fold'] != inner_fold]
        validation = [r for r in outer if r['fold'] == inner_fold]
        test = [r for r in all_rows if r['fold'] == fold]
        trained_folds = sorted({r['fold'] for r in outer})
        fold_dir = models / f'fold{fold}'
        fold_dir.mkdir(parents=True, exist_ok=True)
        f_trials = []
        for C in grid['feature_C']:
            state = fit_linear(inner, features, C)
            raw = linear_scores(validation, features, state)
            ap = ranking_metrics(validation, {i: 1 / (1 + np.exp(-np.clip(z, -60, 60))) for i, z in raw.items()})['map']
            f_trials.append((ap, C, state, raw))
        _, C, _, val_raw = max(f_trials, key=lambda v: (v[0], -v[1]))
        calibration = fit_platt(validation, val_raw)
        final_f = fit_linear(outer, features, C)
        raw = linear_scores(test, features, final_f)
        raw_all['F'].update(raw)
        prob_all['F'].update(calibrate(raw, calibration))
        provenance['F'].update({r['id']: trained_folds for r in test})
        choices['F'][str(fold)] = {'C': C, 'trials': [{'C': v[1], 'inner_map': v[0]} for v in f_trials]}
        dump(fold_dir / 'F.json', {'linear': final_f, 'platt': calibration, 'trained_on_folds': trained_folds})
        calibration0 = fit_platt(validation, raw_ce0)
        raw = {r['id']: raw_ce0[r['id']] for r in test}
        raw_all['CE0'].update(raw)
        prob_all['CE0'].update(calibrate(raw, calibration0))
        provenance['CE0'].update({r['id']: [inner_fold] for r in test})
        dump(fold_dir / 'CE0.json', {'base_revision': REVISION, 'platt': calibration0,
                                    'calibrated_on_fold': inner_fold, 'encoder_trained_on_folds': []})
        for arm in ('CE', 'CE+F'):
            trials, best = [], None
            for ratio in grid['negative_ratios']:
                for lr in grid['learning_rates']:
                    model, mean, scale, choice, val_raw = fit_text(
                        snapshot, inner, validation, pairs, features, device, arm, lr, max(grid['epochs']), ratio,
                        fold_dir / arm / f'inner_lr{lr}_neg{ratio}', select_epochs=grid['epochs'],
                        max_steps=12 if args.smoke else None)
                    trials.append(choice)
                    if best is None or choice['inner_map'] > best['choice']['inner_map']:
                        best = {'choice': choice, 'platt': fit_platt(validation, val_raw)}
                    release(model, device)
            choice = best['choice']
            # No outer labels or gate measurements enter this refit.
            model, mean, scale, _, _ = fit_text(
                snapshot, outer, [], pairs, features, device, arm, choice['lr'], choice['epochs'],
                choice['negative_ratio'], fold_dir / arm / 'refit', select_epochs=[choice['epochs']],
                max_steps=12 if args.smoke else None)
            raw = predict(model, test, pairs, mean, scale, device)
            raw_all[arm].update(raw)
            prob_all[arm].update(calibrate(raw, best['platt']))
            provenance[arm].update({r['id']: trained_folds for r in test})
            choices[arm][str(fold)] = {'choice': choice, 'trials': trials}
            dump(fold_dir / arm / 'calibration.json', {'platt': best['platt'], 'calibration_fold': inner_fold,
                                                     'trained_on_folds': trained_folds,
                                                     'choice': choice})
            release(model, device)
        labelled_test = [r for r in test if r['status'] != 'unmapped']
        for arm in ARMS:
            metrics[arm][str(fold)] = ranking_metrics(labelled_test, prob_all[arm])
            write_scores(dest / f'{arm}.jsonl', [r for r in all_rows if r['id'] in prob_all[arm]],
                         prob_all[arm], provenance[arm])
        dump(dest / 'progress.json', {'completed_outer_folds': folds_to_run[:folds_to_run.index(fold) + 1],
                                      'choices': choices, 'metrics': metrics,
                                      'seconds': time.monotonic() - start})
    if not args.smoke:
        # Deployment checkpoints are never used to produce the cross-fitted gate scores.
        final_dir = models / 'all_folds'
        final_dir.mkdir(parents=True, exist_ok=True)
        counts = Counter(v['C'] for v in choices['F'].values())
        C = min(counts, key=lambda x: (-counts[x], x))
        dump(final_dir / 'F.json', {'linear': fit_linear(rows, features, C),
                                   'platt': fit_platt(rows, raw_all['F']), 'trained_on_folds': list(range(5))})
        dump(final_dir / 'CE0.json', {'base_revision': REVISION, 'platt': fit_platt(rows, raw_all['CE0']),
                                     'calibrated_on_folds': list(range(5))})
        for arm in ('CE', 'CE+F'):
            settings = [(v['choice']['lr'], v['choice']['epochs'], v['choice']['negative_ratio'])
                        for v in choices[arm].values()]
            counts = Counter(settings)
            lr, epochs, ratio = min(counts, key=lambda x: (-counts[x], x[1], x[0], x[2]))
            model, _, _, _, _ = fit_text(snapshot, rows, [], pairs, features, device, arm, lr, epochs, ratio,
                                         final_dir / arm, select_epochs=[epochs])
            dump(final_dir / arm / 'calibration.json', {'platt': fit_platt(rows, raw_all[arm]),
                                                       'trained_on_folds': list(range(5)),
                                                       'deployment_ONLY': True})
            release(model, device)
    # Recheck immutability and all candidate coverage before the ONE reporting gate.
    for name, digest in hashes.items():
        assert sha(source / name) == digest, f'Input changed during run: {name}'
    if not args.smoke and not args.defer_gate:
        assert sha(OUT / 'pools_dev200.jsonl') == manifest['pools_sha256'], 'Upstream pool changed during run'
    for name, digest in protected.items():
        assert sha(ROOT / name) == digest, f'Protected source changed during run: {name}'
    aggregate = {arm: ranking_metrics(rows if not args.smoke else [r for r in rows if r['fold'] == 0], prob_all[arm])
                 for arm in ARMS}
    result = {'per_fold': metrics, 'aggregate': aggregate, 'choices': choices,
              'elapsed_seconds': time.monotonic() - start, 'api_calls': 0,
              'smoke_NOT_A_RESULT': args.smoke, 'input_hashes': hashes}
    dump(dest / 'metrics.json', result)
    gate_output = ('NOT RUN: preview smoke is not an experiment.\n' if args.smoke else
                   'PENDING: deferred for GPU artifact verification and local evaluation.\n')
    if not args.smoke and not args.defer_gate:
        gate_output = reporting_gate(source, dest)
    report = ['# Evidence scorer — ' + ('SMOKE ONLY; NOT RESULTS' if args.smoke else 'cross-fitted dev200'), '',
              'No paid API, QA, judge, RECOMP, FriendsQA or production changes.', '',
              f'Hardware: {platform.platform()}; device={device}; wall={result["elapsed_seconds"]:.1f}s.',
              f'Pinned model: `{MODEL}@{REVISION}`, {protocol["encoder_parameters"]:,} parameters.', '',
              '## Protocol fixed before training', '```json', json.dumps(grid, indent=2), '```', '',
              '## Input hashes', '```json', json.dumps(hashes, indent=2), '```', '',
              '## Inner-fold choices', '```json',
              ('"Omitted: preview engineering run, not experimental results"' if args.smoke else json.dumps(choices, indent=2)), '```', '',
              '## Per-fold metrics', '', '|Arm|Fold|AUC|mAP|Positive in top-5|Brier|', '|---|---|---|---|---|---|']
    if args.smoke:
        report += ['', 'Preview numeric metrics intentionally omitted. See internal engineering logs only.']
    else:
        for arm in ARMS:
            for fold, metric in metrics[arm].items():
                report.append(f'|{arm}|{fold}|{metric["auc"]}|{metric["map"]}|{metric["positive_in_top5"]}|{metric["brier"]}|')
        report += ['', '## Reliability (outer-held-out candidates)', '', '|Arm|Bin|n|Mean probability|Positive frequency|', '|---|---|---|---|---|']
        for arm in ARMS:
            for b in aggregate[arm]['reliability']:
                report.append(f'|{arm}|{b["bin"]}|{b["n"]}|{b["mean_p"]}|{b["fraction_positive"]}|')
    report += ['', '## Reporting gate — verbatim', '```text', gate_output.rstrip(), '```', '',
               '## Interpretation and limits',
               '- Evidence means the supplied source-stamp chunk label, not verified semantic sufficiency.',
               '- Null queries enter BCE/calibration as negatives; unmapped queries are scored but never trained/evaluated.',
               '- CE0 has a frozen pretrained encoder; only its probability calibration uses LiHua labels.',
               '- CE+F trains the encoder and a joint additive classification head on pooled CLS plus standardized features.',
               '- CE/CE+F use per-question BCE + 0.5 pairwise softplus; F uses logistic BCE on all candidates with equal query weights.',
               '- mAP/top-5 include labelled queries with no positive in the pool as misses; Null queries only affect AUC/Brier/calibration.',
               '- Calibration fitted on inner held-out predictions transfers to an outer-training refit; calibration drift is possible.',
               '- Hyperparameter selection and Platt share an inner fold; outer metrics remain held out.',
               '- Gold-conversation grouping applies to positives. Shared negative corpus chunks may occur across folds.',
               '- A cross-fitted score excludes its own fold from encoder, feature scaler, hyperparameter and calibration fitting.',
               '- The unchanged evaluation gate tunes selection on other-fold OOF scores. Those other scorers may have seen this fold;',
               '  consequently selector-hyperparameter tuning is not fully nested end-to-end. Treat the gate as exploratory dev evidence.',
               '- Keep non-dev labels unseen for the deployment model; evidence gains do not establish ACC/ERR gains.',
               '- No automatic switch to Qwen and no tuning after reading the reporting gate.', '']
    report += [f'- Gate pool pinned to export manifest: `{manifest["pool"]}`; no reliance on a mutable coverage default.', '']
    (dest / 'REPORT.md').write_text('\n'.join(report))
    print(f'Complete: {dest / "REPORT.md"}', flush=True)


def reporting_gate(source, dest):
    manifest, _, rows = load_export(source)
    protocol = json.loads((dest / 'protocol.json').read_text())
    for name, digest in protocol['input_hashes'].items():
        assert sha(source / name) == digest, f'Input changed since training: {name}'
    for arm in ARMS:
        got = lines(dest / f'{arm}.jsonl')
        actual = {(r['id'], r['chunk_id']) for r in got}
        expected = {(r['id'], c['chunk_id']) for r in rows for c in r['candidates']}
        assert len(got) == len(actual) and actual == expected, f'{arm}: missing/duplicate/extra candidate'
        folds = {r['id']: r['fold'] for r in rows}
        assert all(folds[r['id']] not in r['trained_on_folds'] and math.isfinite(r['p'])
                   and 0 <= r['p'] <= 1 for r in got), f'{arm}: leaked/invalid scores'
    marker = dest / 'gate_started.json'
    assert not marker.exists(), 'Reporting gate already started; do not rerun automatically'
    # Export can intentionally override coverage.py's default. Preserve export pool.
    cmd = [sys.executable, '-m', 'reproduce.evidence_set.evaluate', '--pool', manifest['pool'], '--scores']
    cmd += [f'{arm}={dest / (arm + ".jsonl")}' for arm in ARMS]
    dump(marker, {'command': cmd, 'input_hashes': protocol['input_hashes'],
                  'score_hashes': {a: sha(dest / (a + '.jsonl')) for a in ARMS}})
    gate = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = gate.stdout + gate.stderr
    (dest / 'gate_output.txt').write_text(output)
    dump(dest / 'gate_finished.json', {'returncode': gate.returncode})
    return output


def resume_deployment(args):
    """Finish interrupted deployment refits; NEVER refit or alter OOF scores.

    Platt scaling is invertible. Recover the original outer raw logits from
    saved p + fold calibrators rather than repeating any of the cross-fitting.
    This restoration is round-trip checked and cannot change an OOF prediction.
    """
    start = time.monotonic()
    dest = args.score_dir or OUT / 'scores'
    source = dest / 'inputs'
    protocol = json.loads((dest / 'protocol.json').read_text())
    progress = json.loads((dest / 'progress.json').read_text())
    assert progress['completed_outer_folds'] == list(range(5)), 'All five outer folds must be complete'
    manifest, chunks, all_rows = load_export(source)
    for n, h in protocol['input_hashes'].items():
        assert sha(source / n) == h, 'Recovery input mismatch: ' + n
    before = {arm: sha(dest / f'{arm}.jsonl') for arm in ARMS}
    rows = [r for r in all_rows if r['status'] != 'unmapped']
    features = manifest['features']
    models = dest.parent / 'models'
    raw_all, prob_all = {a: {} for a in ARMS}, {a: {} for a in ARMS}
    for arm in ARMS:
        saved = {(s['id'], s['chunk_id']): s['p'] for s in lines(dest / f'{arm}.jsonl')}
        for r in all_rows:
            f = r['fold']
            path = models / f'fold{f}' / (f'{arm}.json' if arm in ('F', 'CE0') else f'{arm}/calibration.json')
            cal = json.loads(path.read_text())['platt']
            p = np.asarray([saved[r['id'], c['chunk_id']] for c in r['candidates']])
            assert np.all((p > 0) & (p < 1)) and cal['coef'] != 0, 'Saturated Platt probabilities require raw re-inference'
            z = ((np.log(p) - np.log1p(-p) - cal['intercept']) / cal['coef']) * cal['scale'] + cal['mean']
            assert np.max(np.abs(calibrate({0: z}, cal)[0] - p)) < 1e-12
            raw_all[arm][r['id']], prob_all[arm][r['id']] = z, p
    choices = progress['choices']
    final_dir = models / 'all_folds'
    final_dir.mkdir(exist_ok=True)
    counts = Counter(v['C'] for v in choices['F'].values())
    C = min(counts, key=lambda x: (-counts[x], x))
    if not (final_dir / 'F.json').exists():
        dump(final_dir / 'F.json', {'linear': fit_linear(rows, features, C),
                                   'platt': fit_platt(rows, raw_all['F']), 'trained_on_folds': list(range(5))})
    if not (final_dir / 'CE0.json').exists():
        dump(final_dir / 'CE0.json', {'base_revision': REVISION, 'platt': fit_platt(rows, raw_all['CE0']),
                                     'calibrated_on_folds': list(range(5))})
    device = args.device or ('mps' if torch.backends.mps.is_available() else 'cpu')
    torch.set_num_threads(args.threads)
    GRID.update(protocol['grid'])
    GRID['window_microbatch'] = 8 if device == 'cuda' else 4
    GRID['inference_window_microbatch'] = 64 if device == 'cuda' else 16
    snapshot = Path.home() / '.cache/huggingface/hub' / ('models--' + MODEL.replace('/', '--')) / 'snapshots' / REVISION
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    pairs = Pairs(rows, chunks, tokenizer, features, GRID['max_length'], GRID['document_stride'])
    refits = {}
    for arm in ('CE', 'CE+F'):
        settings = [(v['choice']['lr'], v['choice']['epochs'], v['choice']['negative_ratio'])
                    for v in choices[arm].values()]
        counts = Counter(settings)
        lr, epochs, ratio = min(counts, key=lambda x: (-counts[x], x[1], x[0], x[2]))
        if not (final_dir / arm / 'model.pt').exists():
            model, _, _, _, _ = fit_text(snapshot, rows, [], pairs, features, device, arm,
                                         lr, epochs, ratio, final_dir / arm, select_epochs=[epochs])
            release(model, device)
        dump(final_dir / arm / 'calibration.json', {'platt': fit_platt(rows, raw_all[arm]),
                                                   'trained_on_folds': list(range(5)), 'deployment_ONLY': True,
                                                   'recovered_after_timeout': True, 'refit_device': device})
        refits[arm] = {'lr': lr, 'epochs': epochs, 'negative_ratio': ratio}
    assert all(sha(dest / f'{a}.jsonl') == h for a, h in before.items()), 'OOF scores changed during recovery'
    aggregate = {a: ranking_metrics(rows, prob_all[a]) for a in ARMS}
    recovered = {'per_fold': progress['metrics'], 'aggregate': aggregate, 'choices': choices,
                 'input_hashes': protocol['input_hashes'], 'api_calls': 0,
                 'outer_crossfit_seconds': progress['seconds'], 'deployment_recovery_seconds': time.monotonic() - start}
    dump(dest / 'metrics.json', recovered)
    dump(dest / 'recovery.json', {'original_source_sha256': protocol['source_sha256'],
                                 'recovery_source_sha256': sha(Path(__file__)), 'OOF_scores_unchanged': before,
                                 'raw_logit_restore': 'inverse saved Platt; round-trip absolute p error < 1e-12',
                                 'crossfit_device': protocol['device'], 'deployment_device': device,
                                 'deployment_precision': 'fp32' if device != 'cuda' else 'mixed fp16',
                                 'refits': refits, 'seconds': time.monotonic() - start})
    report = ['# Evidence scorer — cross-fitted dev200', '',
              'All five outer folds finished on Kaggle Tesla T4. The 30-minute limit interrupted deployment refits.',
              f'Deployment refits alone were completed on {device}; cross-fitted probabilities were NOT altered.',
              'No paid API, QA, judge, RECOMP or FriendsQA model was used.', '',
              '## Inputs and predeclared grid', '```json', json.dumps({'input_hashes': protocol['input_hashes'],
                'pool': manifest['pool'], 'features': features, 'seed': SEED, 'grid': protocol['grid']}, indent=2), '```', '',
              '## Inner-fold hyperparameter choices', '```json', json.dumps(choices, indent=2), '```', '',
              '## Hardware and time',
              f'Cross-fit: Tesla T4 / {protocol["hardware"]}, {protocol["precision"]}; outer-fold wall {progress["seconds"]:.1f}s.',
              f'Deployment completion: {platform.platform()} / {device}; {recovered["deployment_recovery_seconds"]:.1f}s.',
              'GPU model parameters: 22,713,601; CE+F adds one weight per supplied feature. Encoder fully fine-tuned.', '',
              '## Per-fold metrics', '|Arm|Fold|AUC|mAP|Positive in top-5|Brier|', '|---|---|---|---|---|---|']
    for arm in ARMS:
        for f, m in progress['metrics'][arm].items():
            report.append(f'|{arm}|{f}|{m["auc"]}|{m["map"]}|{m["positive_in_top5"]}|{m["brier"]}|')
    report += ['', '## Reliability', '|Arm|Bin|n|Mean p|Positive fraction|', '|---|---|---|---|---|']
    for arm in ARMS:
        for b in aggregate[arm]['reliability']:
            report.append(f'|{arm}|{b["bin"]}|{b["n"]}|{b["mean_p"]}|{b["fraction_positive"]}|')
    report += ['', '## Reporting gate — verbatim', '```text',
               'PENDING: deferred for GPU artifact verification and local evaluation.', '```', '', '## Limits',
               '- Source-stamp labels are proxies for evidence, not verified answer sufficiency or QA accuracy.',
               '- CE0 encoder is zero-shot; its Platt calibration is supervised on inner folds.',
               '- Hyperparameter choice and Platt share an inner fold; outer scores remain held out.',
               '- Calibration fitted on a three-fold predictor transfers to a four-fold refit; calibration drift is possible.',
               '- Long chunks use overlapping 512-token windows / max pooling for ALL text arms; no suffix is discarded.',
               '- Unmapped questions are scored but excluded from learning; Null questions provide negatives.',
               '- CE/CE+F use question-level BCE + 0.5 pairwise loss, with different-date hard negatives.',
               '- The unchanged selector gate is not fully nested end-to-end: other-fold OOF scorers can have trained on this fold.',
               '- Treat the gate as exploratory dev evidence. Hold out non-dev questions before any publication claim.',
               '- F and CE+F bundle graph, time and ranking features; their comparison does not isolate graph-only attribution.',
               '- Deployment FP32 MPS refits differ numerically from mixed-precision CUDA cross-fit training.',
               '- No hyperparameters were chosen using the reporting gate. No QA/Judge was run.', '']
    (dest / 'REPORT.md').write_text('\n'.join(report))
    print('DEPLOYMENT_RECOVERED_OOF_UNCHANGED', flush=True)


def self_test():
    import unittest

    class Contracts(unittest.TestCase):
        def test_hash_rejects_mutation(self):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)
                (p / 'chunks.jsonl').write_text('')
                (p / 'train_dev200.jsonl').write_text('')
                dump(p / 'export_manifest.json', {'chunks_sha256': 'wrong'})
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    load_export(p, True)

        def test_calibration_unbalanced(self):
            rs = [{'id': i, 'status': 'labelled', 'candidates': [
                {'label': int(j == 0), 'features': {}} for j in range(20)]} for i in range(4)]
            raw = {i: np.arange(20, dtype=float)[::-1] for i in range(4)}
            p = calibrate(raw, fit_platt(rs, raw))
            self.assertTrue(all(np.isfinite(p[0])))
            self.assertAlmostEqual(float(p[0].mean()), .05, places=3)
            self.assertGreater(p[0][0], p[0][-1])

        def test_candidate_and_fold_contract(self):
            rs = [{'id': 1, 'fold': 3, 'candidates': [{'chunk_id': 'c'}, {'chunk_id': 'd'}]}]
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 's.jsonl'
                with self.assertRaises(AssertionError):
                    write_scores(p, rs, {1: [.1, .2]}, {1: [3]})
                write_scores(p, rs, {1: [.1, .2]}, {1: [0, 1, 2, 4]})
                self.assertEqual(len(lines(p)), 2)
                with self.assertRaises(AssertionError):
                    write_scores(p, rs, {1: [.1]}, {1: [0]})

        def test_null_and_missing_positive_ranking(self):
            rs = [{'id': 1, 'status': 'null', 'candidates': [{'label': 0}]},
                  {'id': 2, 'status': 'labelled', 'candidates': [{'label': 1}, {'label': 0}]},
                  {'id': 3, 'status': 'labelled', 'candidates': [{'label': 0}]}]
            m = ranking_metrics(rs, {1: [.01], 2: [.9, .1], 3: [.01]})
            self.assertEqual(m['map'], .5)
            self.assertEqual(m['positive_in_top5'], .5)

        def test_hard_negative_in_each_eligible_batch(self):
            pairs = object.__new__(Pairs)
            pairs.hard = {0: [5, 9]}
            r = {'id': 0, 'candidates': [{'label': int(j == 0)} for j in range(30)]}
            for seed in range(20):
                js = pairs.sample(r, 8, random.Random(seed))
                self.assertEqual(len(js), 9)
                self.assertEqual(len(js), len(set(js)))
                self.assertTrue({5, 9}.issubset(js))

        def test_hard_negative_must_share_counterpart_not_just_hub(self):
            class Tokenizer:
                model_input_names = ['input_ids']

                def __call__(self, *a, **kw):
                    return {'input_ids': [[1, 2]]}

            chunks = {
                'p': {'content': 'Li Hua: dinner together\nWolfgang: yes', 'time': 'a'},
                'h': {'content': 'Li Hua: dinner together\nWolfgang: yes', 'time': 'b'},
                'hub': {'content': 'Li Hua: dinner together\nJake: yes', 'time': 'b'},
                'same': {'content': 'Li Hua: dinner together\nWolfgang: yes', 'time': 'a'}}
            r = {'id': 0, 'question': 'dinner together', 'candidates': [
                {'chunk_id': c, 'label': int(c == 'p'), 'features': {'bm25': 1.}} for c in chunks]}
            p = Pairs([r], chunks, Tokenizer(), ['bm25'], 512, 128)
            self.assertEqual(p.hard[0], [1])

        def test_checkpointed_window_max_preserves_gradient(self):
            from types import SimpleNamespace

            class TinyEncoder(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    self.weight = torch.nn.Parameter(torch.tensor(.5))

                def forward(self, input_ids):
                    return SimpleNamespace(logits=input_ids.float() * self.weight)

            m = TextScorer.__new__(TextScorer)
            torch.nn.Module.__init__(m)
            m.encoder = TinyEncoder()
            m.feature_head = torch.nn.Linear(1, 1, bias=False)
            torch.nn.init.ones_(m.feature_head.weight)
            out = m({'input_ids': torch.arange(8)[:, None]}, [(0, 3), (3, 8)], torch.tensor([[1.], [2.]]))
            torch.testing.assert_close(out, torch.tensor([2., 5.5]))
            out.sum().backward()
            torch.testing.assert_close(m.encoder.weight.grad, torch.tensor(9.))
            torch.testing.assert_close(m.feature_head.weight.grad, torch.tensor([[3.]]))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--wait-for-export', action='store_true')
    p.add_argument('--wait-minutes', type=float, default=45.)
    p.add_argument('--device', choices=['cpu', 'mps', 'cuda'])
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--defer-gate', action='store_true',
                   help='GPU-only training artifact; validate inputs and run --finish-gate locally after download')
    p.add_argument('--finish-gate', action='store_true', help='verify downloaded cross-fitted scores and run the gate ONCE')
    p.add_argument('--score-dir', type=Path, help='downloaded GPU scores directory for --finish-gate')
    p.add_argument('--resume-deployment', action='store_true', help='finish only deployment refits after all five cross-fit folds completed')
    a = p.parse_args()
    if a.self_test:
        self_test()
    elif a.resume_deployment:
        resume_deployment(a)
    elif a.finish_gate:
        dest = a.score_dir or OUT / 'scores'
        source = dest / 'inputs' if (dest / 'inputs').exists() else OUT / 'codex'
        output = reporting_gate(source, dest)
        report = dest / 'REPORT.md'
        text = report.read_text().replace('PENDING: deferred for GPU artifact verification and local evaluation.', output.rstrip())
        report.write_text(text)
        print(output)
    else:
        run(a)


if __name__ == '__main__':
    main()
