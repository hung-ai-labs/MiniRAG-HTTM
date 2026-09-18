# E1 offline evaluation -- 2026-09-18 07:12:59

**Effect of E1 entity resolution under the deterministic relationship-embedding correction.** Control is NOT the byte-identical committed retrieval index.

- control   : `E:\Sv clone\MiniRAG\logs\entity_resolution\pair\control`
- treatment : `E:\Sv clone\MiniRAG\logs\entity_resolution\pair\entres`
- tap do    : 180 cau co evidence (159 Single + 21 Multi + 0 Null)
- validity  : **VALID** (68/68 check bat buoc PASS -- xem validity_audit.md)

## mode = graph (MINIRAG_CHUNK_FUSION='')
### full-evidence trong graph_ids (<=30, truoc fusion)

| tap | n | control | treatment | wins | losses | tie-pass | tie-fail | net | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 180 | 103 (57.2%) | 102 (56.7%) | 2 | 3 | 100 | 75 | -1 | 1 |
| Single | 159 | 95 (59.7%) | 94 (59.1%) | 1 | 2 | 93 | 63 | -1 | 1 |
| Multi | 21 | 8 (38.1%) | 8 (38.1%) | 1 | 1 | 7 | 12 | +0 | 1 |

### full-evidence trong chunk_ids (sau fusion + A1@4000)

| tap | n | control | treatment | wins | losses | tie-pass | tie-fail | net | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 180 | 74 (41.1%) | 77 (42.8%) | 6 | 3 | 71 | 100 | +3 | 0.5078 |
| Single | 159 | 69 (43.4%) | 71 (44.7%) | 5 | 3 | 66 | 85 | +2 | 0.7266 |
| Multi | 21 | 5 (23.8%) | 6 (28.6%) | 1 | 0 | 5 | 15 | +1 | 1 |

### workload

| arm | chi so | mean | median | p95 | max |
|---|---|---:|---:|---:|---:|
| control | graph_seeds | 96.08 | 96.5 | 149 | 176 |
| control | graph_paths | 19631.98 | 19994.5 | 31566 | 36741 |
| control | retrieval_ms | 13967.57 | 12158.42 | 28421.82 | 47936.26 |
| treatment | graph_seeds | 95.39 | 96.0 | 148 | 174 |
| treatment | graph_paths | 21909.57 | 22307.0 | 35154 | 40612 |
| treatment | retrieval_ms | 14342.58 | 11721.49 | 35847.86 | 49603.5 |

## mode = rrf (MINIRAG_CHUNK_FUSION='rrf')
### full-evidence trong graph_ids (<=30, truoc fusion)

| tap | n | control | treatment | wins | losses | tie-pass | tie-fail | net | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 180 | 103 (57.2%) | 102 (56.7%) | 2 | 3 | 100 | 75 | -1 | 1 |
| Single | 159 | 95 (59.7%) | 94 (59.1%) | 1 | 2 | 93 | 63 | -1 | 1 |
| Multi | 21 | 8 (38.1%) | 8 (38.1%) | 1 | 1 | 7 | 12 | +0 | 1 |

### full-evidence trong chunk_ids (sau fusion + A1@4000)

| tap | n | control | treatment | wins | losses | tie-pass | tie-fail | net | McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 180 | 112 (62.2%) | 112 (62.2%) | 2 | 2 | 110 | 66 | +0 | 1 |
| Single | 159 | 98 (61.6%) | 98 (61.6%) | 1 | 1 | 97 | 60 | +0 | 1 |
| Multi | 21 | 14 (66.7%) | 14 (66.7%) | 1 | 1 | 13 | 6 | +0 | 1 |

### workload

| arm | chi so | mean | median | p95 | max |
|---|---|---:|---:|---:|---:|
| control | graph_seeds | 96.08 | 96.5 | 149 | 176 |
| control | graph_paths | 19631.98 | 19994.5 | 31566 | 36741 |
| control | retrieval_ms | 10000.75 | 8354.77 | 20783.87 | 31113.64 |
| treatment | graph_seeds | 95.39 | 96.0 | 148 | 174 |
| treatment | graph_paths | 21909.57 | 22307.0 | 35154 | 40612 |
| treatment | retrieval_ms | 129878.71 | 7179.97 | 20694.94 | 11245501.39 |

## Cong da dang ky (nguong khong doi; cong RRF doc final_chunks)

```json
{
 "status": "EVALUATED",
 "blocking_checks": [],
 "graph_only": {
  "metric": "mode=graph -> graph_top30 (ALL)",
  "rule": "full-evidence net >= +9 VA McNemar exact p < 0,01",
  "net": -1,
  "mcnemar_p": 1.0,
  "passed": false
 },
 "rrf": {
  "metric": "mode=rrf -> final_chunks (ALL)",
  "rule": "full-evidence net >= 0",
  "net": 0,
  "mcnemar_p": 1.0,
  "passed": true
 }
}
```

## Audit notes

- 3-query engineering smoke test was observed before the full run; no merge decision, metric definition or numerical threshold was changed based on it. Its n=3 pass counts for mode=graph were printed to the operator.
- The RRF gate was corrected at the ANALYSIS layer from graph_top30 to final_chunks because graph_ids is captured before chunk fusion (minirag/operate.py:1489). The correction was applied to eval_offline.py at 2026-09-17 22:52:08 (file mtime), after the full run was launched at 22:43:00 (process output file ctime) and before the first full-run raw log existed (control_graph.jsonl ctime 23:25:45). It is NOT a preregistration made before measurement. Preregistered thresholds (+9 / p<0.01; >=0) are unchanged.
- The running retrieval process keeps the launch-time code in memory, so it still writes reports with the uncorrected RRF gate. Those reports are preserved under provenance/runner_original/ as run evidence and are superseded by this report for gate conclusions.
- Report-layer changes (fail-closed gating, provenance verification) do not change the merge list, the retrieval implementation, the sample, the metric definitions or the numerical thresholds.
- Control arm is NOT the byte-identical committed retrieval index: both arms had their relationship VDB re-embedded with hf_embed at batch=1 per the 17/09/2026 amendment.
- Headline result: effect of E1 entity resolution under the deterministic relationship-embedding correction.
