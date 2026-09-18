# E1 offline evaluation -- 2026-09-17 23:13:18

**Effect of E1 entity resolution under the deterministic relationship-embedding correction** (amendment 17/09/2026). Control is NOT the byte-identical committed retrieval index.

- control   : `E:\Sv clone\MiniRAG\logs\entity_resolution\pair\control`
- treatment : `E:\Sv clone\MiniRAG\logs\entity_resolution\pair\entres`
- tap do    : 180 cau co evidence (159 Single + 21 Multi + 0 Null)
- trang thai: **INVALID** (check bat buoc: 4 PASS / 8 FAIL / 8 UNVERIFIED)

## Cong: NOT_EVALUATED

Fail-closed: con check bat buoc chua PASS nen khong ket luan cong.

- **FAIL** — nap raw log: thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\control_graph.jsonl — thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\control_graph.jsonl _(nguon: raw_log)_
- **FAIL** — nap raw log: thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\treatment_graph.jsonl — thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\treatment_graph.jsonl _(nguon: raw_log)_
- **FAIL** — nap raw log: thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\control_rrf.jsonl — thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\control_rrf.jsonl _(nguon: raw_log)_
- **FAIL** — nap raw log: thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\treatment_rrf.jsonl — thieu raw log: E:\Sv clone\MiniRAG\logs\entity_resolution\eval\treatment_rrf.jsonl _(nguon: raw_log)_
- **FAIL** — control/graph: co raw log — thieu file _(nguon: raw_log)_
- **FAIL** — treatment/graph: co raw log — thieu file _(nguon: raw_log)_
- **FAIL** — control/rrf: co raw log — thieu file _(nguon: raw_log)_
- **FAIL** — treatment/rrf: co raw log — thieu file _(nguon: raw_log)_
- **UNVERIFIED** — control: graph_ids bat bien giua hai mode — thieu raw log _(nguon: raw_log)_
- **UNVERIFIED** — treatment: graph_ids bat bien giua hai mode — thieu raw log _(nguon: raw_log)_
- **UNVERIFIED** — khong co loi goi LLM trong lan chay truy hoi — khong co manifest va khong co bao cao cua lan chay _(nguon: thieu)_
- **UNVERIFIED** — cache parser khong bi ghi them trong lan chay — thieu bang chung tu lan chay _(nguon: thieu)_
- **UNVERIFIED** — control: hash index truoc/sau lan chay khong doi — runner cua lan chay khong luu lai hash truoc/sau _(nguon: thieu)_
- **UNVERIFIED** — treatment: hash index truoc/sau lan chay khong doi — runner cua lan chay khong luu lai hash truoc/sau _(nguon: thieu)_
- **UNVERIFIED** — cau hinh hai nhanh giong nhau tru working_dir — thieu bang chung tu lan chay _(nguon: thieu)_
- **UNVERIFIED** — ngan sach context 4000 va cach cat Sources dung thiet lap da dang ky — thieu bang chung tu lan chay _(nguon: thieu)_

## Cong da dang ky truoc (nguong khong doi)

```json
{
 "status": "NOT_EVALUATED",
 "blocking_checks": [
  "raw log chua day du"
 ],
 "graph_only": {
  "passed": null
 },
 "rrf": {
  "passed": null
 }
}
```

## Audit notes

- 3-query engineering smoke test was observed before the full run; no merge decision, metric definition or numerical threshold was changed based on it.
- The RRF gate was corrected at the ANALYSIS layer from graph_top30 to final_chunks because graph_ids is captured before chunk fusion (minirag/operate.py:1489). This is a correction made AFTER the retrieval run was launched; it is NOT a preregistration made before measurement. Preregistered thresholds (+9 / p<0.01; >=0) are unchanged.
- Control arm is NOT the byte-identical committed retrieval index: both arms had their relationship VDB re-embedded with hf_embed at batch=1 per the 17/09/2026 amendment.
- The headline result describes the effect of E1 entity resolution under the deterministic relationship-embedding correction, not the effect of E1 on the originally committed index.
