# Task for Codex: train the evidence scorer for the evidence-set selector

Read `CLAUDE.md` first. Its rules apply here:
- no paid APIs;
- do not edit `baseline.yaml`;
- do not delete or overwrite any index;
- report McNemar, not raw point differences.

## Context

This is MiniRAG on LiHua-World, with Qwen2.5-3B as the reader. The baseline is C0 + source-time + A1@4000, without RRF and without path pruning. That baseline cuts the candidate list to the top 30 chunks and then takes chunks in order until it reaches 4,000 tokens.

The oracle diagnostic run on 11/11 (`review/oracle_headroom_20261111/REPORT.md`) found two things:
- when the Sources block holds every gold chunk, Qwen answers about 83% of questions correctly;
- the order of the chunks hardly matters.

So the job is to decide **which whole chunks go into the 4,000 tokens**.

The pipeline around your model is already built in `reproduce/evidence_set/`:
- `pool.py` captures the full native candidate ranking for each question.
- `features.py` exports the candidates and their features.
- `select.py` holds the budgeted set selection. It needs a calibrated probability p(chunk is evidence) for each candidate.
- `evaluate.py` measures the offline gate.

**Your only job is the scorer that produces p.** Do not change the selection algorithm, the pools, the labels or the folds.

This work replaces RECOMP in the paper, so it must not reuse RECOMP:
- do not load the RECOMP checkpoint in `.cache/minirag/recomp`, or anything derived from it;
- do not use RECOMP's training objective, which labels sentences by the LM log-likelihood of the gold answer;
- do not use the FriendsQA MLP in `review/friendsqa_selector_kaggle_20261111`. It has already failed to transfer to LiHua.

## Inputs (read-only)

All inputs are in `review/evidence_set_20261111/codex/`.

**If that folder does not exist yet**, the pool capture is still running. Work in two phases:

1. **Now:** write `train_scorer.py` against `review/evidence_set_20261111/codex_preview/`. It has the same schema, but only about 68 of the 200 questions, and its pool and folds are not final. Use it for smoke tests only: one fold, a tiny grid, a few hundred steps. Do not report any number from it.
2. **When `codex/export_manifest.json` appears:** check the hashes, then run the full protocol below on `codex/`.

`chunks.jsonl` has one row per corpus chunk (514 rows):

```json
{"chunk_id", "content", "doc", "order", "tokens", "time"}
```

- `doc` is the conversation the chunk belongs to. Long conversations are split into 2–3 overlapping chunks.
- `time` is the chunk's `Time:` header, or null for a continuation chunk.

`train_dev200.jsonl` has one row per dev question (200 rows):

```json
{"id", "question", "type": "Single|Multi|Null", "status": "labelled|null|unmapped",
 "fold": 0-4, "n_evidence", "gold_in_pool", "baseline_kept": [...],
 "candidates": [{"chunk_id", "features": {...}, "label": 0|1, "evidence_index": [...]}]}
```

- The pool is **graph only**, `native@45`: the top 45 chunks of the native graph + source-time ranking. It has 8,943 candidates and 142 positives. The team dropped the dense top-30 expansion on 11/11, so `in_dense30` and `dense_rank` remain features only (C0 already uses them as a ×10 boost).
- Each question has up to 45 candidates and 1–2 positives.
- Every key in `features` can be computed at query time; none of them reads the gold labels. The full list is in `FEATURES` in `features.py`.
- Folds are grouped by gold conversation, so the same evidence never appears in two folds.

`export_manifest.json` holds the hashes of the input files. Verify them before training and record them in your report.

## What to train

Train **four arms**, all cross-fitted over the 5 given folds. For each fold f, train on the other four folds and score the candidates of fold f.

| Arm | Model | Purpose |
|---|---|---|
| `F` | Logistic regression or a small gradient-boosted tree on `features` only, no text | Shows how far the graph and time signals go without reading text |
| `CE0` | `cross-encoder/ms-marco-MiniLM-L6-v2` as is, zero-shot, logit on (question, chunk content) | Untrained reference. Reviewers will ask whether training adds anything over an off-the-shelf reranker |
| `CE` | The same cross-encoder fine-tuned on (question, chunk content) | Text only, trained |
| `CE+F` | The fine-tuned cross-encoder fused with the standardized `features`, either a joint head on [CLS ⊕ features] or a stack on [CE logit ⊕ features] | **Main arm** |

Both models are already in the local Hugging Face cache, so use `HF_HUB_OFFLINE=1`.
- For `CE` and `CE+F`, start from the cross-encoder above. It fits on Mac CPU or MPS.
- Move to `Qwen/Qwen2.5-0.5B-Instruct` as a pointwise scorer only if `CE+F` is clearly weak on the inner-fold metrics below. Report it as a separate arm; do not replace the main arm with it.

### Training data and loss

- **Positives:** candidates with `label = 1`.
- **Negatives:** every other candidate in the same question's pool. Questions with `status = "null"` contribute only negatives; keep them, because they teach the model when nothing is evidence. Drop questions with `status = "unmapped"` (3 rows).
- **Hard negatives** matter most. Earlier deterministic rerankers failed on chunks that share the participants and topic but come from another date. Make sure these appear in every batch: same participants and keywords as a positive, but a different `time`.
- **Loss:** binary cross-entropy plus a per-question listwise or pairwise term, because ranking inside a question matters most. Handle the imbalance with question-level sampling, not by changing the labels.

### Calibration (required)

`select.py` combines probabilities, so p must be calibrated. Inside each outer training split, hold out one inner fold, fit Platt scaling or isotonic regression on it, and apply that to the outer test fold. Report the Brier score and a reliability table for each arm.

### Hyperparameters

- Choose them **only** from inner validation inside the training folds. Use per-question recall@budget or mean average precision, not `evaluate.py`.
- Declare a small grid before training and keep to it: at most 3 learning rates × 2 epoch counts × 2 negative ratios.
- Fix the seed to 13 and record it.
- Do not loop "train → run `evaluate.py` → tweak". `evaluate.py` is the reporting gate, not a tuning signal.

## Outputs

1. Training code in `reproduce/evidence_set/train_scorer.py`. It must be runnable end to end with one command, read only the inputs above, and verify their hashes.
2. One cross-fitted score file per arm, at `review/evidence_set_20261111/scores/<ARM>.jsonl`. Each line is:

   ```json
   {"id": <question id>, "chunk_id": "...", "p": <0..1>, "trained_on_folds": [..]}
   ```

   - There must be exactly one line for every candidate of every question, Null questions included.
   - `trained_on_folds` must never contain the question's own fold. `evaluate.py` checks this and refuses leaked files.
3. Checkpoints for each fold, plus a model trained on **all 5 folds** with the chosen hyperparameters, in `review/evidence_set_20261111/models/`. The all-fold model is used once, later, on the held-out non-dev questions.
4. `review/evidence_set_20261111/scores/REPORT.md` covering:
   - the hyperparameter grid and the inner-fold choice;
   - per-fold AUC, mean average precision, positive-in-top-5 and Brier score for each arm;
   - wall time and hardware;
   - the output of the gate below, pasted unedited.

## Gate (run once at the end, then report; do not optimise against it)

Score every candidate in the `native@45` export, then run:

```bash
S=review/evidence_set_20261111/scores
.venv/bin/python -m reproduce.evidence_set.evaluate --pool native@45 \
  --scores F=$S/F.jsonl CE0=$S/CE0.jsonl CE=$S/CE.jsonl CE+F=$S/CE+F.jsonl
```

Reference counts of full-evidence questions, out of 177 labelled (11/11, already measured):

| BASELINE | BM25_RERANK (comparison arm only) | ORACLE_WIDE (ceiling) |
|---:|---:|---:|
| 88 | 108 | 117 |

The main arm is interesting only if it beats **both** `BM25_RERANK` and `CE0_RERANK`. If it does not, report that honestly.

## Do not

- Read Gold Answer or Evidence from `dataset/` or `logs/`. The labels you need are already in `train_dev200.jsonl`.
- Edit anything under `minirag/`, or any file in `reproduce/evidence_set/` other than `train_scorer.py`.
- Run Qwen generation, the judge, or any QA. QA happens only after the offline gate passes, and the team decides when.
- Generate synthetic questions. That is a possible phase 2, and it needs the team's approval first.
- Add BM25 or any other lexical-retrieval score as a feature, or use RRF or any rank fusion. The team excluded both from the method. BM25 appears only as the `BM25_RERANK` comparison arm inside `evaluate.py`. The export has 18 features and none of them is BM25; if you started on an earlier export with 21 features, start again from the current one and check its hashes.
