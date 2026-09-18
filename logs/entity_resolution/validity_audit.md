# E1 -- validity audit (2026-09-18 07:12:59)

Trang thai: **VALID** -- check bat buoc 68 PASS / 0 FAIL / 0 UNVERIFIED

Cong: **EVALUATED**

## Moi check

| trang thai | bat buoc | check | chi tiet | nguon |
|---|---|---|---|---|
| PASS | x | control/graph: dung 180 ban ghi | 180 | raw_log |
| PASS | x | control/graph: khong trung cau hoi | 180 dong / 180 cau | raw_log |
| PASS | x | control/graph: dung va du bo cau hoi cua tap do | khop | raw_log |
| PASS | x | control/graph: schema log du truong | 0 ban ghi thieu | raw_log |
| PASS | x | control/graph: type moi cau khop tap do | 0 | raw_log |
| PASS | x | control/graph: raw log khong chua nhan gold | 0 | raw_log |
| PASS | x | control/graph: fusion dung '', khong tron mode | [''] | raw_log |
| PASS | x | control/graph: graph_ids <= 30 (kwd2chunk chunk_nums = top_k/2) | 0 vuot | raw_log |
| PASS | x | control/graph: ranked_ids == graph_ids (khong tron o mode graph) | 0 lech | raw_log |
| PASS | x | control/graph: moi chunk id trong chunk_ids/vector_ids thuoc corpus | 0 id la | raw_log + kv_store_text_chunks.json |
| PASS |  | control/graph: graph_ids tham chieu chunk khong con trong kho (dac tinh co san cua do thi) | 16 lan, 1 id: ['chunk-c7ec35daa1b937efdeec1effd7d95ede'] | raw_log + kv_store_text_chunks.json |
| PASS | x | control/graph: khong co id la ngoai tap chunk treo thua ke tu do thi | treo thua ke 2 id; ngoai danh sach: [] | raw_log + source_id cua do thi nhanh + kv_store_text_chunks.json |
| PASS | x | treatment/graph: dung 180 ban ghi | 180 | raw_log |
| PASS | x | treatment/graph: khong trung cau hoi | 180 dong / 180 cau | raw_log |
| PASS | x | treatment/graph: dung va du bo cau hoi cua tap do | khop | raw_log |
| PASS | x | treatment/graph: schema log du truong | 0 ban ghi thieu | raw_log |
| PASS | x | treatment/graph: type moi cau khop tap do | 0 | raw_log |
| PASS | x | treatment/graph: raw log khong chua nhan gold | 0 | raw_log |
| PASS | x | treatment/graph: fusion dung '', khong tron mode | [''] | raw_log |
| PASS | x | treatment/graph: graph_ids <= 30 (kwd2chunk chunk_nums = top_k/2) | 0 vuot | raw_log |
| PASS | x | treatment/graph: ranked_ids == graph_ids (khong tron o mode graph) | 0 lech | raw_log |
| PASS | x | treatment/graph: moi chunk id trong chunk_ids/vector_ids thuoc corpus | 0 id la | raw_log + kv_store_text_chunks.json |
| PASS |  | treatment/graph: graph_ids tham chieu chunk khong con trong kho (dac tinh co san cua do thi) | 13 lan, 1 id: ['chunk-c7ec35daa1b937efdeec1effd7d95ede'] | raw_log + kv_store_text_chunks.json |
| PASS | x | treatment/graph: khong co id la ngoai tap chunk treo thua ke tu do thi | treo thua ke 2 id; ngoai danh sach: [] | raw_log + source_id cua do thi nhanh + kv_store_text_chunks.json |
| PASS | x | control/rrf: dung 180 ban ghi | 180 | raw_log |
| PASS | x | control/rrf: khong trung cau hoi | 180 dong / 180 cau | raw_log |
| PASS | x | control/rrf: dung va du bo cau hoi cua tap do | khop | raw_log |
| PASS | x | control/rrf: schema log du truong | 0 ban ghi thieu | raw_log |
| PASS | x | control/rrf: type moi cau khop tap do | 0 | raw_log |
| PASS | x | control/rrf: raw log khong chua nhan gold | 0 | raw_log |
| PASS | x | control/rrf: fusion dung 'rrf', khong tron mode | ['rrf'] | raw_log |
| PASS | x | control/rrf: graph_ids <= 30 (kwd2chunk chunk_nums = top_k/2) | 0 vuot | raw_log |
| PASS | x | control/rrf: moi chunk id trong chunk_ids/vector_ids thuoc corpus | 0 id la | raw_log + kv_store_text_chunks.json |
| PASS |  | control/rrf: graph_ids tham chieu chunk khong con trong kho (dac tinh co san cua do thi) | 16 lan, 1 id: ['chunk-c7ec35daa1b937efdeec1effd7d95ede'] | raw_log + kv_store_text_chunks.json |
| PASS | x | control/rrf: khong co id la ngoai tap chunk treo thua ke tu do thi | treo thua ke 2 id; ngoai danh sach: [] | raw_log + source_id cua do thi nhanh + kv_store_text_chunks.json |
| PASS | x | treatment/rrf: dung 180 ban ghi | 180 | raw_log |
| PASS | x | treatment/rrf: khong trung cau hoi | 180 dong / 180 cau | raw_log |
| PASS | x | treatment/rrf: dung va du bo cau hoi cua tap do | khop | raw_log |
| PASS | x | treatment/rrf: schema log du truong | 0 ban ghi thieu | raw_log |
| PASS | x | treatment/rrf: type moi cau khop tap do | 0 | raw_log |
| PASS | x | treatment/rrf: raw log khong chua nhan gold | 0 | raw_log |
| PASS | x | treatment/rrf: fusion dung 'rrf', khong tron mode | ['rrf'] | raw_log |
| PASS | x | treatment/rrf: graph_ids <= 30 (kwd2chunk chunk_nums = top_k/2) | 0 vuot | raw_log |
| PASS | x | treatment/rrf: moi chunk id trong chunk_ids/vector_ids thuoc corpus | 0 id la | raw_log + kv_store_text_chunks.json |
| PASS |  | treatment/rrf: graph_ids tham chieu chunk khong con trong kho (dac tinh co san cua do thi) | 13 lan, 1 id: ['chunk-c7ec35daa1b937efdeec1effd7d95ede'] | raw_log + kv_store_text_chunks.json |
| PASS | x | treatment/rrf: khong co id la ngoai tap chunk treo thua ke tu do thi | treo thua ke 2 id; ngoai danh sach: [] | raw_log + source_id cua do thi nhanh + kv_store_text_chunks.json |
| PASS | x | graph: vector_ids giong het giua hai nhanh (cung embedding, top_k, kho chunk) | 0 cau lech | raw_log |
| PASS | x | rrf: vector_ids giong het giua hai nhanh (cung embedding, top_k, kho chunk) | 0 cau lech | raw_log |
| PASS | x | control: graph_ids va vector_ids bat bien giua hai mode (chi fusion khac; operate.py:1489) | graph_ids lech 0, vector_ids lech 0 | raw_log |
| PASS | x | treatment: graph_ids va vector_ids bat bien giua hai mode (chi fusion khac; operate.py:1489) | graph_ids lech 0, vector_ids lech 0 | raw_log |
| PASS | x | control/graph: chunk_ids = tien to dai nhat cua ranked_ids co <= 4000 token (A1@4000) | 0 cau lech | tinh lai tu raw log + tiktoken gpt-4o |
| PASS | x | treatment/graph: chunk_ids = tien to dai nhat cua ranked_ids co <= 4000 token (A1@4000) | 0 cau lech | tinh lai tu raw log + tiktoken gpt-4o |
| PASS | x | control/rrf: chunk_ids = tien to dai nhat cua ranked_ids co <= 4000 token (A1@4000) | 0 cau lech | tinh lai tu raw log + tiktoken gpt-4o |
| PASS | x | treatment/rrf: chunk_ids = tien to dai nhat cua ranked_ids co <= 4000 token (A1@4000) | 0 cau lech | tinh lai tu raw log + tiktoken gpt-4o |
| PASS | x | tap do = 180 (159 Single + 21 Multi + 0 Null) | {'Single': 159, 'Multi': 21} | eval_set.py |
| PASS | x | moi cau co gold_chunk_ids khong rong | 0 rong | diag_path2chunk.jsonl |
| PASS | x | moi gold chunk thuoc corpus | 0 id la | kv_store_text_chunks.json |
| PASS | x | TYPE_POOL control == treatment | 47 gia tri | graphml hai nhanh (hien tai) |
| PASS | x | nguon report cua runner duoc xac minh | report goc: dung dau van tay runner v1, cung bo check, dung khung thoi gian, so lieu tinh lai khop raw log; stdout goc cho thay ca bon luot duoc chay | provenance/runner_original |
| PASS | x | ca bon luot duoc CHAY trong cung mot tien trinh, dung thu tu (khong luot nao dung lai) | stdout goc cho thay ca bon luot duoc chay | provenance/runner_original (stdout hoac minirag.log ghi trong lan chay) |
| PASS | x | khong co loi goi LLM trong lan chay truy hoi (ca bon luot) | runner: 0 | provenance/runner_original |
| PASS | x | cache parser: so key khong doi (runner) va file khong bi ghi trong lan chay (filesystem) | runner: 200 -> 200; cache mtime 2026-09-17 22:35:28 <= khoi chay 2026-09-17 22:43:00; noi dung == nguon screening | provenance/runner_original + filesystem |
| PASS | x | control: index khong doi trong ca hai luot (hash truoc/sau cua runner AND 2 mode) | runner: ; moi file index mtime <= moc dong bang 2026-09-17 22:25:55 | provenance/runner_original + filesystem |
| PASS | x | treatment: index khong doi trong ca hai luot (hash truoc/sau cua runner AND 2 mode) | runner: ; moi file index mtime <= moc dong bang 2026-09-17 22:25:55 | provenance/runner_original + filesystem |
| PASS | x | ma runner luc khoi chay duoc dung lai va xac minh | patch(ban_dung_lai) == runner hien tai (11 phep thay the) | provenance/eval_offline_AT_LAUNCH_reconstructed.py |
| PASS | x | ma luc khoi chay: stub LLM cam duoc noi vao MiniRAG | llm_model_func=forbidden_llm | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: cache parser chi-doc cho moi luot | os.environ["MINIRAG_KW_CACHE_ONLY"] = "1" | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: BASE_ENV dat lai truoc moi truy van | os.environ.update(BASE_ENV) | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: BASE_ENV dung thiet lap da dang ky | BASE_ENV = {"MINIRAG_ANSWER_TYPE_FIX": "1", "MINIRAG_PATH2CHUNK_FIX": "0", "MINIRAG_CHUNK_CUT": ""} | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: bo TRUNCATE_SOURCES / MAX_TOKEN_TEXT_UNIT | UNSET_ENV = ("MINIRAG_TRUNCATE_SOURCES", "MINIRAG_MAX_TOKEN_TEXT_UNIT") | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: only_need_context=True | only_need_context=True | ban dung lai da xac minh |
| PASS | x | ma luc khoi chay: khong ghi llm cache vao nhanh | enable_llm_cache=False | ban dung lai da xac minh |
| PASS |  | runner: cau hinh hai nhanh giong nhau (CHI phu mode rrf vi cfg bi ghi de -- bo tro) |  | provenance/runner_original |
| PASS |  | hien tai: hai nhanh ton tai | ['E:\\Sv clone\\MiniRAG\\logs\\entity_resolution\\pair\\control', 'E:\\Sv clone\\MiniRAG\\logs\\entity_resolution\\pair\\entres'] | trang thai hien tai (khong phai bang chung ve lan chay) |

## Audit notes

- 3-query engineering smoke test was observed before the full run; no merge decision, metric definition or numerical threshold was changed based on it. Its n=3 pass counts for mode=graph were printed to the operator.
- The RRF gate was corrected at the ANALYSIS layer from graph_top30 to final_chunks because graph_ids is captured before chunk fusion (minirag/operate.py:1489). The correction was applied to eval_offline.py at 2026-09-17 22:52:08 (file mtime), after the full run was launched at 22:43:00 (process output file ctime) and before the first full-run raw log existed (control_graph.jsonl ctime 23:25:45). It is NOT a preregistration made before measurement. Preregistered thresholds (+9 / p<0.01; >=0) are unchanged.
- The running retrieval process keeps the launch-time code in memory, so it still writes reports with the uncorrected RRF gate. Those reports are preserved under provenance/runner_original/ as run evidence and are superseded by this report for gate conclusions.
- Report-layer changes (fail-closed gating, provenance verification) do not change the merge list, the retrieval implementation, the sample, the metric definitions or the numerical thresholds.
- Control arm is NOT the byte-identical committed retrieval index: both arms had their relationship VDB re-embedded with hf_embed at batch=1 per the 17/09/2026 amendment.
- Headline result: effect of E1 entity resolution under the deterministic relationship-embedding correction.
