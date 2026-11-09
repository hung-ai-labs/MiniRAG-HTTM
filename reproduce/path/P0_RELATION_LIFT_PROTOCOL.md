# P0-based relation-conditioned path scoring, fixed C1 candidates

2026-11-09. Registered before measurement. Exploratory dev, not final QA.
P2 weighted is removed from current C3/main-method configuration; its source
remains only for historical reproduction. No prior result row is relabeled.

Observed: transmitting/calibrating P0/P2 has not improved over C1. Old P2 adds
mostly structural heuristics, not evidence-specific query information. Raw path
source mass also depends on how often the same source occurs across paths.
The original edge vote uses a count, discarding continuous relation similarity.

Hypothesis: retain P0 answer-type and voted-edge counts as a prior, use existing
query/relation cosine to assess all hops, then correct source multiplicity with
a matched structural background. Query/chunk affinity remains the existing C1
signal, not a replacement for graph flows.

For every unchanged original path p:

    q0(p) = answer_type_count(p) + original_edge_vote_count(p) + 1
    r(e) = max(0, cosine(query, existing_relation_vector(e)))
    R(p) = geometric_mean(r(e) for adjacent physical edges in p)
    q(p) = q0(p) * R(p)

Read vectors for physical edges on original paths, without adding/removing paths
or replacing the original semantic relationship search/goodedge filter/votes.
Both hops participate. Empty-edge paths use R=1. If an entire seed has zero
query-conditioned mass, explicitly fall back to q0 for that seed and report it.
Zero-score paths are still enumerated/processed, not pruned.

Using the exact same complete node/voted-edge provenance projector as C1, form:

    Prior_s(c): projection of q0, with per-seed mass normalized to one
    B_s(c): projection of uniform path weights 1, same paths and source channels
    F_s(c): projection of q, with per-seed mass normalized to one
    weight_s(c) = max(0,cos(query,chunk)) * F_s(c) / B_s(c)

Uniform background removes structural/source repetition while retaining P0
answer-type/edge-vote information in F. Division occurs only on supported
chunks, with B>0; no smoothing/tuned coefficient. Isolated nodes keep their
original node-source fallback. Both node and edge provenance channels stay.

Freeze ordered local lists to C1: select its original three using
Prior_s(c)*chunk_affinity, then evaluate the new weights on exactly those IDs.
Do not reselect with the new formula. Feed dimensionless weights into unchanged
kwd2chunk with score flow on, preserving seed, first-seed and legacy dense boost
scope. No local-mean calibration after the likelihood ratio; no RRF/BM25.

Prespecified arms:
- C0: frozen project MiniRAG baseline (same answer-type fix/A1@4000).
- C1: frozen current C1; must reproduce every context and graph rank.
- C2: existing P0 calibrated fixed-C1 control, descriptive only.
- C3: new full P0 relation-conditioned/background-corrected scoring (primary).
- no_relation: q=q0; isolate continuous relation information.
- no_background: use chunk_affinity*F; isolate structural correction.
- affinity_only: use chunk_affinity on the same fixed C1 IDs; strong ablation.
- no_score_flow: same ordered C1 IDs, no score multiplication; must equal C1.

All original MiniRAG flows stay active in C3: entity matching, all original
two-hop paths/seed eligibility, answer-type, P0 scorer, semantic relationship
search, edge_vote_path, node/edge sources, path2chunk, scorednode2chunk, dense
search/boost, kwd2chunk and Entities/Sources. No new LLM/index/embedding model,
prompt changes, pruning, top-k/context-budget changes or coefficient sweep.

Controlled inputs: same Qwen index and frozen parser, all-MiniLM-L6-v2 pinned
revision, dev 200, top_k=60, local three, graph top-30 and A1@4000. Temporary
index copies; forbidden_llm and cache-only parser; no API calls. Snapshot code,
index/parser/data hashes before/after, per-query inputs, path/vote fingerprints,
fallbacks, relation-vector work, contexts and rankings. Labels evaluation-only.

Primary full-evidence comparisons: C3 vs C0 and C1, exact paired McNemar with
Holm adjustment. Secondary: all ablations, especially affinity_only; no graph
benefit claim without improvement over that control. Report top-30, capped
evidence/full evidence, Single/Multi and Null context changes. Record actual
retrieval and projection timing; no speedup comparison to cached baselines.

Test complete-hop scoring, P0 type/vote effects, source-budget conservation,
matched-background removal of duplicate path bias, zero-signal fallback,
isolated-node provenance and failure on missing/nonfinite vectors. C1 and
no_score_flow must match 200 frozen outputs; all C3 contexts must match replay.
Run actual baseline C0/C1/C2 on first two questions as an independent check.

No new variants or mechanism changes after results. Dev is already inspected;
offline gains are not accuracy, independent confirmation or a novelty claim.
