# E1 offline evaluation -- 2026-09-18 07:08

Entity Resolution E1 under the deterministic relationship-embedding correction preregistered on 17/09/2026.

control   = E:\Sv clone\MiniRAG\logs\entity_resolution\pair\control
treatment = E:\Sv clone\MiniRAG\logs\entity_resolution\pair\entres
tap do: 180 cau co evidence (159 Single + 21 Multi + 0 Null)
sanity: VALID (32/32 check)

## mode = graph (MINIRAG_CHUNK_FUSION='')
### full-evidence trong graph top-30
- ALL:
  control  103/180 = 57.22%
  treatment 102/180 = 56.67%
  wins 2 / losses 3 / tie-pass 100 / tie-fail 75
  net -1, McNemar exact p = 1
- Single:
  control  95/159 = 59.75%
  treatment 94/159 = 59.12%
  wins 1 / losses 2 / tie-pass 93 / tie-fail 63
  net -1, McNemar exact p = 1
- Multi:
  control  8/21 = 38.10%
  treatment 8/21 = 38.10%
  wins 1 / losses 1 / tie-pass 7 / tie-fail 12
  net +0, McNemar exact p = 1

### full-evidence trong chunk_ids sau cat 4.000
- ALL:
  control  74/180 = 41.11%
  treatment 77/180 = 42.78%
  wins 6 / losses 3 / tie-pass 71 / tie-fail 100
  net +3, McNemar exact p = 0.507812
- Single:
  control  69/159 = 43.40%
  treatment 71/159 = 44.65%
  wins 5 / losses 3 / tie-pass 66 / tie-fail 85
  net +2, McNemar exact p = 0.726562
- Multi:
  control  5/21 = 23.81%
  treatment 6/21 = 28.57%
  wins 1 / losses 0 / tie-pass 5 / tie-fail 15
  net +1, McNemar exact p = 1

### workload
- control: {"graph_seeds": {"n": 180, "mean": 96.08, "median": 96.5, "p95": 149, "max": 176}, "graph_paths": {"n": 180, "mean": 19631.98, "median": 19994.5, "p95": 31566, "max": 36741}, "retrieval_ms": {"n": 180, "mean": 13967.57, "median": 12158.42, "p95": 28421.82, "max": 47936.26}}
- treatment: {"graph_seeds": {"n": 180, "mean": 95.39, "median": 96.0, "p95": 148, "max": 174}, "graph_paths": {"n": 180, "mean": 21909.57, "median": 22307.0, "p95": 35154, "max": 40612}, "retrieval_ms": {"n": 180, "mean": 14342.58, "median": 11721.49, "p95": 35847.86, "max": 49603.5}}

## mode = rrf (MINIRAG_CHUNK_FUSION='rrf')
### full-evidence trong graph top-30
- ALL:
  control  103/180 = 57.22%
  treatment 102/180 = 56.67%
  wins 2 / losses 3 / tie-pass 100 / tie-fail 75
  net -1, McNemar exact p = 1
- Single:
  control  95/159 = 59.75%
  treatment 94/159 = 59.12%
  wins 1 / losses 2 / tie-pass 93 / tie-fail 63
  net -1, McNemar exact p = 1
- Multi:
  control  8/21 = 38.10%
  treatment 8/21 = 38.10%
  wins 1 / losses 1 / tie-pass 7 / tie-fail 12
  net +0, McNemar exact p = 1

### full-evidence trong chunk_ids sau cat 4.000
- ALL:
  control  112/180 = 62.22%
  treatment 112/180 = 62.22%
  wins 2 / losses 2 / tie-pass 110 / tie-fail 66
  net +0, McNemar exact p = 1
- Single:
  control  98/159 = 61.64%
  treatment 98/159 = 61.64%
  wins 1 / losses 1 / tie-pass 97 / tie-fail 60
  net +0, McNemar exact p = 1
- Multi:
  control  14/21 = 66.67%
  treatment 14/21 = 66.67%
  wins 1 / losses 1 / tie-pass 13 / tie-fail 6
  net +0, McNemar exact p = 1

### workload
- control: {"graph_seeds": {"n": 180, "mean": 96.08, "median": 96.5, "p95": 149, "max": 176}, "graph_paths": {"n": 180, "mean": 19631.98, "median": 19994.5, "p95": 31566, "max": 36741}, "retrieval_ms": {"n": 180, "mean": 10000.75, "median": 8354.77, "p95": 20783.87, "max": 31113.64}}
- treatment: {"graph_seeds": {"n": 180, "mean": 95.39, "median": 96.0, "p95": 148, "max": 174}, "graph_paths": {"n": 180, "mean": 21909.57, "median": 22307.0, "p95": 35154, "max": 40612}, "retrieval_ms": {"n": 180, "mean": 129878.71, "median": 7179.97, "p95": 20694.94, "max": 11245501.39}}

## cong da dang ky truoc
{
 "graph_only": {
  "rule": "full-evidence net >= +9 VA p < 0,01",
  "net": -1,
  "p": 1.0,
  "passed": false
 },
 "rrf": {
  "rule": "full-evidence net >= 0",
  "net": -1,
  "passed": false
 }
}
