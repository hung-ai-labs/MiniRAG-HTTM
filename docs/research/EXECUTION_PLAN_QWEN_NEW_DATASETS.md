# Kế hoạch thực thi — đợt Qwen2.5-3B trên MultiHop-RAG và 2WikiMultiHopQA

> Soạn 25/10/2026 trên branch `dev`, HEAD `9c59062`, working tree sạch. Phiên soạn **không** chạy benchmark, không gọi
> Qwen/Gemini/GPT-4o, không dựng index, không sửa code. Đọc kèm [`../../CLAUDE.md`](../../CLAUDE.md) (quy tắc bắt buộc,
> đặc biệt §1b, §3, §4) và [`../../ROADMAP.md`](../../ROADMAP.md).

**Quy ước nhãn** — mọi dòng trạng thái mang một trong ba nhãn:

| Nhãn | Nghĩa |
|---|---|
| **[CÓ SẴN]** | Đã kiểm trong repo/PDF ở phiên soạn, kèm đường dẫn bằng chứng |
| **[CẦN TRIỂN KHAI]** | Chưa tồn tại; tên file/flag ghi ở đây là **đề xuất**, chưa có trong code |
| **[CHƯA XÁC MINH]** | Có thể đúng nhưng chưa có bằng chứng đủ; luôn đi kèm một task xác minh `V-…` |

**Lệnh** trong tài liệu này đều **chưa kiểm thử**. Lệnh gọi script chưa tồn tại được đánh dấu `# [SCRIPT CHƯA TỒN TẠI]`.
Placeholder: `<PYTHON>` (trình thông dịch của venv mỗi người), `<SLM_URL>`, `<JUDGE_MODEL_ID>`, `<RUN_ID>`,
`<BACKUP_ROOT>` (nơi lưu trữ chung), `<PAPER_PDF>` (bản `miniRAG1.pdf`, sha256 ở mục A2). Hai người: **Người 1**
(MultiHop-RAG, đề xuất Tài) và **Người 2** (2WikiMultiHopQA).

---

## A. Trạng thái đã xác minh và khoảng trống

### A1. Repo

| Mục | Trạng thái | Bằng chứng |
|---|---|---|
| Branch `dev`, HEAD `9c59062` "Add 2WikiMultiHopQA and MultiHop-RAG datasets"; `b83f216` là commit ngay trước | [CÓ SẴN] | `git log` |
| Remote `origin` = `hung-ai-labs/MiniRAG-HTTM`. Commit upstream HKUDS cuối cùng trước khi nhóm sửa: **`e204d23`** (16/10/2025); commit đầu của nhóm `9467e4f` (07/09/2026); `git diff e204d23 HEAD -- minirag` ≈ 985 dòng thêm | [CÓ SẴN] | `git log 9467e4f^` |
| `runs/` **chưa** bị gitignore | [CÓ SẴN] | `git check-ignore runs/x` trả rỗng |
| `LiHua-World-qwen-modal/` (15 MB) **đang được commit**; `LiHua-World-gemini/` bị ignore | [CÓ SẴN] | `git ls-files`, `.gitignore` |
| `logs/*.jsonl`, `logs/*.csv` bị ignore (trừ danh sách ngoại lệ) → ví dụ `logs/stage_d/*_ctx.jsonl` mà `reproduce/stage_d/run_one.sh` ghi ra **không** có trong repo | [CÓ SẴN] | `.gitignore`, `ls logs/stage_d` |
| Script hiện có giả định macOS/zsh (`caffeinate`, `pmset` trong `reproduce/stage_d/chain_stage_d.sh`; `#!/bin/zsh` trong `reproduce/slm_env.sh`; `.venv/bin/python`). Máy Windows của Người 1 có `.venv/Scripts/`; thư mục `venv/` là venv copy từ máy khác, không chạy được | [CÓ SẴN] | đọc file, `ls venv/bin` |
| `tests/` chỉ có `test_weaviate.py` — không có test nào cho pipeline | [CÓ SẴN] | `ls tests` |
| Không tồn tại: `PROJECT_STATE.md`, `BASELINE_MANIFEST.yaml`, `EXPERIMENT_HISTORY.md`, `CODE_MAP.md` | [CÓ SẴN] | `find` toàn repo |

### A2. Bài báo đích: `miniRAG1.pdf`

sha256 `a62cad8535e27a9005fa25098ba69908604f3f4158b39f5a7bab00a1d654bd86` (bản ba dataset). Bản khác (`miniRAG.pdf`,
sha256 `6a7e3674…d1f561`) **không** dùng. PDF nằm ngoài repo → task `S-01` đưa một bản vào `<BACKUP_ROOT>` kèm sha256.

**Số tham chiếu (Table 1, Qwen2.5-3B-Instruct, GPT-4o chấm, mean ± sd 3 lượt chấm theo mô tả §4.1)** — đọc từ text
trích xuất `pdftotext -raw`, thứ tự hàng đã đối chiếu:

| Dataset | BM25 | RAPTOR | HippoRAGv2 | GraphRAG | LightRAG | **MiniRAG** |
|---|---|---|---|---|---|---|
| LiHuaWorld | 40,97 ± 5,02 / 24,33 ± 3,92 | 37,49 / 21,73 | 36,58 / 26,77 | / | 41,76 / 30,77 | **46,78 ± 4,55 / 24,33 ± 3,77** |
| MultiHop-RAG | 38,58 ± 2,19 / 23,71 ± 2,78 | 39,50 / 28,18 | 38,56 / 29,84 | / | 21,87 ± 4,03 / 14,71 ± 3,36 | **50,94 ± 4,58 / 35,49 ± 3,87** |
| 2WikiMultiHopQA | 46,32 ± 2,44 / 31,71 ± 4,69 | 43,80 / 34,25 | 45,02 / 38,94 | / | 28,29 ± 5,50 / 21,77 ± 4,02 | **52,30 ± 6,11 / 36,29 ± 4,95** |

(ô dạng `acc / err`, %). Table 2 (ablation, **chỉ LiHuaWorld**), hàng Qwen2.5-3B: MiniRAG 46,93 ± 4,55 / 24,33 ± 3,77;
−I 21,66 ± 6,12 / 15,07 ± 3,30; −Rchunk 42,07 ± 6,59 / 16,48 ± 2,04; −Redge 45,05 ± 1,73 / 17,11 ± 2,98. Lưu ý: acc
MiniRAG LiHua ở Table 1 (46,78) và Table 2 (46,93) **không khớp nhau** trong chính bài báo — ghi cả hai.

⚠ **`README.md:83` và `CLAUDE.md` đang dùng số của phiên bản khác** (MultiHop-RAG Qwen 48,55 / 33,10; LiHua Qwen
48,75 / 26,02). Mọi bảng của đợt này dùng số trên; không trộn hai phiên bản. Việc sửa README/CLAUDE.md là quyết định của
nhóm (mục H), không thuộc phiên này.

**Giao thức bài báo đã đọc được:**

| Nội dung | Trích | Ghi chú |
|---|---|---|
| Chunk 1200 token, overlap 100; vector store nano vector base | Phụ lục B, "Implementation Details" | khớp mặc định code (`minirag/minirag.py:139`) |
| "top-k retrieval to **5 documents**", "maximum token limit **6000** tokens" | Phụ lục B | **không** khớp tên/giá trị nào trong code: `QueryParam.top_k=60` (`minirag/base.py:25`) dùng cho truy vấn vdb thực thể/chunk, chunk vector lấy `top_k/2`; `max_token_for_text_unit=4000`, `max_token_for_node_context=500` (`minirag/base.py:29,35`). Ý nghĩa "5 documents" và "6000 tokens" ánh xạ vào tham số nào là **[CHƯA XÁC MINH]** → `V-03` |
| k dùng cho cả k-hop subgraph lẫn top-k path; độ dài path n (Table A3, A4: k ∈ {4,10,50}, n ∈ {2,4,8}) | Phụ lục A.3 | không ghi giá trị mặc định cho Table 1 → **[CHƯA XÁC MINH]** |
| Embedding SLM: all-MiniLM-L6-v2 | Phụ lục B | khớp `reproduce/gemini_common.py` (`--embedmodel local`) |
| Một model làm cả index, sinh truy vấn, trả lời; không reranker | §4.1 | khớp cấu trúc `llm_model_func` duy nhất |
| Judge GPT-4o, lặp 3 lần có xáo thứ tự, báo mean và variance | §4.1 | |
| Nhãn judge trong thí nghiệm nhất quán: 1 / 0 / −1 (đúng / không chắc / sai) | §4.2 | rubric acc/err/neither của repo tương ứng nhưng **không** phải cùng prompt |
| Đối chiếu judge: 100 cặp Q–A lấy từ "MultihopQA test set" | §4.2 | không rõ là MultiHop-RAG hay 2Wiki |
| **−I**: thay heterogeneous graph indexing bằng indexing dựa trên mô tả (description-based) "tương tự LightRAG và GraphRAG" | §4.4 | không có chi tiết hiện thực |
| **−Ri**: tắt có chọn lọc module khi truy hồi đồ thị: **−Redge** = bỏ thông tin cạnh, **−Rchunk** = bỏ chunk nodes | §4.4, chú thích Table 2 | không có chi tiết hiện thực |
| Cách dựng corpus/split/cỡ mẫu cho MultiHop-RAG và 2Wiki | — | **Không tìm thấy.** Chỉ NQ/TQA (Phụ lục A.1) có mô tả: "randomly sampled supporting documents for 500 questions as the document corpus and randomly selected 100 questions" — đó là dataset khác, không phải bằng chứng cho 2Wiki |

### A3. Ba lớp cấu hình — không được gộp làm một

| Tham số | `UPSTREAM_CODE` (code HKUDS tại `e204d23`) | `PAPER_CONFIG` (miniRAG1.pdf) | `GROUP_BASE` (code nhóm hiện tại, như `qwen637_fix`) |
|---|---|---|---|
| Chunk | 1200 / 100 | 1200 / 100 | 1200 / 100 |
| Gleaning | 1 (`minirag.py:144`) | không ghi | 1 |
| Embedding | do người gọi chọn | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 384d |
| `top_k` | 60 | "5 documents" (chưa ánh xạ) | 60 |
| Ngân sách Sources | khai báo 4000 nhưng **không áp** cho Sources ở chế độ mini (`operate.py:1553-1570`, chú thích A1) | "6000 tokens" (chưa ánh xạ) | **A1@4000** áp cho Sources (`operate.py:1571`, mặc định bật) |
| So khớp answer-type | lỗi hoa/thường (`minirag/kg/networkx_impl.py:174-179`) | không ghi | đã vá (`MINIRAG_ANSWER_TYPE_FIX` mặc định `1`) |
| `ainsert` | lỗi O(N²) — trích xuất lại corpus | không ghi | vá bằng `extracted_chunks.json` (`minirag.py:383`) — **không có công tắc tắt** |
| Trộn chunk | chỉ đồ thị (`kwd2chunk`) | đồ thị | chỉ đồ thị |
| Judge | — | GPT-4o × 3 | Gemini (đợt này: Flash, mục B4) |

Hệ quả: **MR_FULL không được định nghĩa chỉ bằng `MINIRAG_TRUNCATE_SOURCES=0 MINIRAG_ANSWER_TYPE_FIX=0`.** Hai công tắc đó
chỉ đưa code về gần `UPSTREAM_CODE` ở hai điểm; nó vẫn khác upstream ở bản vá O(N²) và chưa chứng minh được là
`PAPER_CONFIG`. MR_FULL được chốt ở task `V-03` sau khi ánh xạ top-k/ngân sách; trước đó nó ở trạng thái **[CHƯA XÁC MINH]**.

### A4. Dataset

**MultiHop-RAG** — `dataset/MultiHop-RAG/raw/`

| Mục | Giá trị | Trạng thái |
|---|---|---|
| `corpus.json` | 609 bài, trường `title, author, source, published_at, category, url, body`; sha256 `20b61b5a…ade9e4d28f` | [CÓ SẴN] |
| `MultiHopRAG.json` | 2.556 câu, trường `query, answer, question_type, evidence_list`; sha256 `03cfb492…338515bff` | [CÓ SẴN] |
| Loại câu | comparison 856 · inference 816 · temporal 583 · null 301 | [CÓ SẴN] |
| ID câu hỏi | **không có** | [CÓ SẴN] |
| Split chính thức | **không có** | [CÓ SẴN] |
| Evidence | theo `url` (+ `title`, `fact`); 0 url thiếu trong corpus; null có `evidence_list` rỗng | [CÓ SẴN] |
| Trùng lặp | 0 url/title/body trùng; 0 câu hỏi trùng nguyên văn | [CÓ SẴN] |
| Đáp án | "Yes" 782, "no" 536, null luôn "Insufficient information." (301) | [CÓ SẴN] |
| Kích thước | ≈1,38 triệu token (tiktoken `gpt-4o`, như `operate.py:42`); trung vị 1.672, max 15.738 token/bài; ước lượng thô ≈1.533 chunk @1200/100 (≈3× LiHua 503) | ước lượng — chunker thật chưa chạy → `MHR-03` |
| Thành phần liên thông theo url evidence (2.255 câu có evidence) | **91 thành phần, lớn nhất 1.895 câu (84,0%)** | [CÓ SẴN] — đo offline trong phiên |
| Nhóm theo **nguyên tập** url evidence | 1.041 nhóm, 569 nhóm có >1 câu, nhóm lớn nhất 20 câu | [CÓ SẴN] |

→ Chia theo thành phần liên thông **không khả thi** cho MultiHop-RAG (một thành phần nuốt 84%). Phương án thay thế phải
được chọn ở `MHR-04` (mục B3).

**2WikiMultiHopQA** — `dataset/2WikiMultiHopQA/raw/`

| Mục | Giá trị | Trạng thái |
|---|---|---|
| Archive | 6 phần `data_ids_april7.zip.part-0*`; zip ráp lại khớp sha256 `95DF2BF5…5529EEF` trong README | [CÓ SẴN] |
| `extracted/` (gitignored) | `train.json` 708 MB, `dev.json` 58 MB, `test.json` 54 MB, `id_aliases.json` | [CÓ SẴN] |
| dev | 12.576 câu, **có** `answer`, `supporting_facts`, `evidences`, `answer_id`; loại compositional 5.236 · comparison 3.040 · bridge_comparison 2.751 · inference 1.549; 0 câu trùng | [CÓ SẴN] |
| test chính thức | 12.576 câu, **không có** answer/supporting_facts/evidences → không chấm được | [CÓ SẴN] |
| Corpus | **không có corpus chung**: mỗi câu kèm 10 đoạn (setting distractor); mỗi title ứng với đúng một văn bản trong dev | [CÓ SẴN] |
| Cỡ corpus khi gộp 10 đoạn của N câu dev ngẫu nhiên (seed 13) | N=200 → 1.446 đoạn / 144k token; 500 → 3.324 / 342k; 1.000 → 6.360 / 663k; 2.000 → 11.564 / 1,23M | [CÓ SẴN] — đo offline |
| Thành phần liên thông (N=500) | theo title **gold** (`supporting_facts`): 482 thành phần, lớn nhất 3 câu · theo **mọi** title trong context: 117 thành phần, lớn nhất 304 câu | [CÓ SẴN] |
| Thành phần liên thông (N=1.000) | gold: 907, lớn nhất 6 · mọi context: 185, lớn nhất 723 | [CÓ SẴN] |
| Cách tác giả dựng corpus 2Wiki | **không có trong PDF** (A2) | [CHƯA XÁC MINH] → `V-02` |

→ Với 2Wiki, nhóm theo title gold khả thi trên mẫu đã đo; nhóm theo mọi title context thì không. Phải đo lại trên pool
thực tế (`2W-04`).

### A5. Pipeline hiện có và khoảng trống ghi log

| Thành phần | Hành vi hiện tại | Khoảng trống so với yêu cầu |
|---|---|---|
| `reproduce/gemini_common.py` `build_rag()` | chunk 1200/100, gleaning 1 (mặc định thư viện), embedding local 384d, `llm_model_func=gemini_complete`, `llm_model_max_token_size=200`, `llm_model_max_async=8`, `embedding_func_max_async=4` | không lưu cấu hình ra manifest |
| `llm_model_max_token_size=200` | grep tĩnh: trường khai báo ở `minirag/minirag.py:169`, **không thấy chỗ nào trong `minirag/` đọc nó** (ngoài `minirag/api/minirag_server.py` truyền vào). Giới hạn sinh thực tế khi chạy SLM đến từ `MINIRAG_MAX_TOKENS` (`minirag/llm/gemini.py:298`, `slm_env.sh modal` đặt 1024) | Có ảnh hưởng runtime hay không là **[CHƯA XÁC MINH]** → `V-05` (kiểm bằng log `max_tokens` thực gửi). Không suy từ tên biến |
| Số lời gọi indexing | đọc tĩnh `operate.py:276-292`: gleaning=1 → 1 lời gọi trích xuất + 1 gleaning/chunk, không gọi `if_loop` (thoát ở dòng 284); tóm tắt description bị comment (`operate.py:155,214`) | Số thực tế (retry tenacity tới 1800 s ở `gemini.py`, tài liệu thất bại làm lại, cache) **[CHƯA XÁC MINH]** → đo trong `index_requests.jsonl` ở pilot. CLAUDE.md ghi "~2,2 lời gọi/tài liệu" cho LiHua (503 chunk/442 tài liệu × 2 ≈ 2,28 — nhất quán với đọc tĩnh, chưa đo lại) |
| `reproduce/Step_0_index.py` | chỉ đọc `.txt`; `--evidence` theo định dạng LiHua; `rag.insert(text)` từng file | không loader JSON; doc ID = md5 nội dung (`minirag.py:438`), chunk ID theo hash nội dung → mapping `dataset doc_id ↔ doc-…` phải tự ghi; không log request |
| `reproduce/Step_1_QA.py` | đọc CSV `Question`/`Gold Answer`; **resume theo số dòng đã có**; lỗi → ghi chuỗi `"Error"` như câu trả lời | không query_id; không config hash; không lưu messages/context; lỗi hạ tầng lẫn vào answer (stage D phải kiểm `"Error"` bằng script riêng) |
| `reproduce/Step_2_evaluate.py` | 3 lượt, xáo thứ tự seed `13+run`; `judge_failed` không ghi file (đúng); model mặc định `gemini-flash-lite-latest` | nhãn không khớp → **mặc định `neither`** (`reproduce/Step_2_evaluate.py:108`, vi phạm yêu cầu `parse_failed`); không lưu raw response, không lưu model trả về; khoá bằng văn bản câu hỏi; Type đọc từ query set LiHua |
| `minirag/llm/gemini.py` | backend OpenAI-compatible dùng chung cho Gemini và vLLM; `MINIRAG_SLM_SEED` gửi `seed` theo request | không log request/response; không lưu `response.model`, usage token |
| `MINIRAG_CONTEXT_LOG` (`operate.py:1580-1628`) | ghi `query, n_chunks, sources_tok, entities_tok, fusion, chunk_ids, ranked_ids, graph_ids, vector_ids, bm25_ids, bm25_ms, context_sha256, graph_seeds, graph_paths, retrieval_ms` | **không** ghi văn bản context, đầu ra parser từ khoá, điểm số; không ghi gì khi thoát sớm |
| Thoát sớm | (1) parse JSON từ khoá hỏng → `fail_response` (`operate.py:1655-1676`, chỉ `print`); (2) đồ thị không ra node hoặc cạnh → `None` → `fail_response` (`operate.py:1522-1526`, xảy ra **cả ở B2**) | không có bản ghi, không phân biệt được với câu trả lời thật |
| `kv_store_llm_response_cache.json` | 0 entry dù `enable_llm_cache=True` | cache hit/miss không quan sát được |
| `reproduce/screening/screen_variant.py` | có `mcnemar_p`, `append_jsonl`, hash context/prompt | gắn chặt LiHua (assert `logs/devset.csv`, gold từ `logs/diag_path2chunk.jsonl`); chỉ tái dùng hàm |
| `reproduce/modal_slm.py` | vLLM 0.11.0, A10G, `MAX_MODEL_LEN=32768`, `max_containers=1`, `@modal.concurrent(max_inputs=32)`, tên phục vụ `minirag-slm`; model `Qwen/Qwen2.5-3B-Instruct` **không ghim revision** | thông số sampling mặc định của server **[CHƯA XÁC MINH]** → `V-04` |

### A6. Ánh xạ cấu hình kế hoạch → code

| ID | Ánh xạ | Trạng thái |
|---|---|---|
| GROUP_BASE | `MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=` (như `BASE_ENV` trong `reproduce/screening/screen_variant.py`), `MINIRAG_CHUNK_FUSION` trống, A1@4000 mặc định, mode `mini`, `top_k` 60, `response_type` mặc định | [CÓ SẴN] |
| B2_FULL | GROUP_BASE + `MINIRAG_CHUNK_FUSION=vector_bm25`: RRF k=60 (`operate.py:1245`) của vector top-30 và BM25 top-30 (`minirag/bm25.py`, tách từ `[a-z0-9]+`, k1 1,2, b 0,75) trên nguyên câu hỏi; Entities vẫn từ đồ thị; vẫn thoát `None` khi đồ thị rỗng | [CÓ SẴN] |
| B2_NO_BM25 | `MINIRAG_CHUNK_FUSION=vector` = `list(chunks_ids)` (vector top-30). RRF của một bảng giữ nguyên thứ tự nên về lý thuyết trùng "B2 bỏ BM25" | [CÓ SẴN], tương đương **[CHƯA XÁC MINH]** → kiểm bằng fixture `S-07` |
| B2_NO_VECTOR | BM25 thuần — chưa có giá trị `MINIRAG_CHUNK_FUSION` tương ứng (giá trị lạ → `ValueError`, `operate.py:1519`) | [CẦN TRIỂN KHAI] |
| B2_NO_ENT | B2 nhưng bảng Entities rỗng, Sources giữ nguyên byte | [CẦN TRIỂN KHAI] |
| HYBRID_NO_GRAPH | RRF(vector, BM25) không gọi parser từ khoá, không truy hồi đồ thị, không thoát `None` của đồ thị; gần `naive_query` (`operate.py:1081`, mode `naive` ở `minirag.py:583`) | [CẦN TRIỂN KHAI] |
| MR_FULL | phụ thuộc `V-03` (A3) | [CHƯA XÁC MINH] |
| MR_MINUS_I / RCHUNK / REDGE | định nghĩa mức khái niệm có trong PDF (A2), hiện thực không có. Quan sát code: prompt `entity_extraction` hiện dùng **đã** yêu cầu description cho entity và relationship (`minirag/prompt.py:13`), `entity_extraction_noDes` chỉ còn trong comment (`operate.py:251`) và không được định nghĩa trong `prompt.py` → ranh giới "MiniRAG indexing" với "description-based indexing" trong code **không rõ** | [CHƯA XÁC MINH] → `V-01`; chặn mọi lượt MR_MINUS_* |

---

## B. Giao thức chung — khoá ở P0, trước khi hai người tách việc

### B1. Model và phục vụ

- Model: `Qwen/Qwen2.5-3B-Instruct` làm **cả** trích xuất index, gleaning, phân tích câu hỏi, sinh câu trả lời.
- Phục vụ: vLLM qua `reproduce/modal_slm.py` [CÓ SẴN] hoặc endpoint OpenAI-compatible tương đương. Trước pilot phải ghim:
  HF revision (commit hash), vLLM version, `max_model_len`, dtype, GPU, và thông số sampling thực tế (`V-04`).
- Endpoint **có thể dùng chung** giữa hai người. Điều kiện: lịch chạy ghi trong `docs/research/RUN_SCHEDULE.md`
  [CẦN TRIỂN KHAI], mỗi lượt ghi `endpoint_id`, `concurrency` phía client, khung giờ, và người chạy vào `run_manifest.json`.
  Không đo latency khi người kia đang chạy trên cùng endpoint (`max_containers=1` → hai luồng tranh cùng một GPU).
- `MINIRAG_MAX_TOKENS=1024` như `slm_env.sh modal`; seed sinh qua `MINIRAG_SLM_SEED` theo danh sách cố định.
- `max_model_len` 32768 phải đủ cho prompt dài nhất đo ở pilot (MR_FULL không cắt Sources có thể tràn — đã xảy ra ở LiHua
  5–8% câu, CLAUDE.md §1).

### B2. Index

- Chunk 1200/100, gleaning 1, embedding `sentence-transformers/all-MiniLM-L6-v2` 384d, entity types mặc định
  (`prompt.py:10`). Một index cho mỗi `(dataset, corpus_id, model_revision, index_config_hash)`; mọi cấu hình retrieval
  dùng chung index đó. −I (nếu được định nghĩa) có index riêng.
- `llm_model_max_token_size=200` giữ như LiHua để so sánh được, kèm kết luận của `V-05`.
- Thư mục index: `indexes/<dataset_id>-qwen-<corpus_id>/` [CẦN TRIỂN KHAI] — **không** đặt trong `LiHua-World-*`, không
  ghi vào index LiHua (CLAUDE.md §4). Sau P1 index đóng băng: checksum từng file, chỉ đọc.

### B3. Corpus, split, lấy mẫu

**MultiHop-RAG**
- Corpus: toàn bộ 609 bài, mỗi bài một tài liệu `title + published_at + source + body` — định dạng chính xác chốt ở
  `MHR-02` và ghi vào manifest (cách paper đưa metadata vào văn bản là **[CHƯA XÁC MINH]**).
- query_id: `mhr-<chỉ số 0-based trong MultiHopRAG.json>`, kèm sha256 câu hỏi để phát hiện file nguồn đổi.
- Split: không có split chính thức → **test nội bộ** (gọi là `internal_test`, không phải test chính thức). Quy tắc nhóm
  **chưa khoá**. Số đo ở A4 cho thấy thành phần liên thông theo url không khả thi; ứng viên cho `MHR-04`: nhóm theo nguyên
  tập url evidence (1.041 nhóm) cộng nhóm gần trùng văn bản; null chia ngẫu nhiên phân tầng. Chỉ khoá sau khi `MHR-04` báo
  cáo phân bố nhóm, tỷ lệ loại câu mỗi phía, và số cặp câu dev–test chia chung tài liệu evidence (rò rỉ còn lại phải ghi
  vào Limitations, vì corpus vốn dùng chung).

**2WikiMultiHopQA**
- Test chính thức không có nhãn → mọi đánh giá dùng câu lấy từ **dev chính thức**, chia thành `internal_dev` và
  `internal_test`. Báo cáo phải ghi rõ "test nội bộ tách từ dev chính thức".
- Corpus: bài báo không mô tả (A2). Đề xuất của nhóm — **chuyển đổi benchmark, không phải tái hiện chính xác**: chọn ngẫu
  nhiên (seed công bố) một pool N câu từ dev chính thức; corpus = hợp **cả 10 đoạn** (gold + distractor) của mọi câu
  trong pool; mỗi đoạn một tài liệu `Title\n<các câu nối bằng dấu cách>`; `internal_dev` và `internal_test` đều lấy từ pool
  và truy vấn trên cùng corpus. N chốt ở `2W-03` theo số chunk đo thật và ngân sách (A4 cho cỡ tham chiếu).
- Nhóm split ứng viên: thành phần liên thông theo title gold. Khoá sau khi `2W-04` đo lại trên pool thực tế.
- `id_aliases.json` chỉ dùng phía chấm (alias của đáp án), không vào generation.

**Chung**
- Phát hiện gần trùng (chuẩn hoá chữ thường/dấu câu + Jaccard 5-gram ký tự, ngưỡng ghi trong manifest) chỉ để **gắn nhóm**,
  không tự xoá câu.
- Smoke/pilot lấy mẫu có seed, phân tầng theo loại câu **của chính dataset đó** (không áp nhãn Single/Multi/Null của LiHua).
- ID test nội bộ lưu trong `split_manifest.json`; danh sách câu test chỉ mở ở P8 (mục E). Câu dev có thể xem tự do.

### B4. Judge, rubric, parser, số lượt lặp

- Phát triển: **Gemini Flash** (không phải Flash-Lite). ID model chính xác **[CHƯA XÁC MINH]** → `V-06`; ghim bản có version
  nếu API cung cấp, lưu trường `model` trong response. Khác judge LiHua (Flash-Lite) có chủ đích → số hai dataset mới
  không so trực tiếp với số LiHua.
- Rubric `rubric_v1` [CẦN TRIỂN KHAI], một bản cho cả hai dataset: giữ định nghĩa accurate/error/neither của
  `reproduce/Step_2_evaluate.py` (khớp §4.1 bài báo), thêm hướng dẫn cho câu yes/no, câu so sánh, câu null của MultiHop-RAG
  ("Insufficient information." là đáp án đúng), và alias 2Wiki. Đầu ra JSON `{"label": "accurate|error|neither"}`; không
  parse được → `parse_failed` (không bao giờ thành `neither`); API hỏng sau số lần thử giới hạn → `judge_failed`, lượt chưa
  hoàn tất. Đổi rubric → tăng version và chấm lại mọi nhánh được so.
- Từ chối (refusal) là trường riêng `refusal_detected` theo quy tắc ghi trong rubric, không suy từ `neither`.
- Lặp: smoke/pilot 1 lượt sinh × 1 lượt chấm. Cấu hình đưa vào kết luận dev: 3 lượt sinh (seed `101/202/303`, như
  `reproduce/stage_d/chain_stage_d.sh`) × số lượt chấm chốt trước mỗi đợt (đề xuất 3, theo bài báo). Ghi riêng sd giữa lượt
  sinh và sd giữa lượt chấm; không gộp dưới một dấu ±.
- Cuối (P8): GPT-4o **chỉ chấm**, trên cùng tập câu trả lời đã đóng băng của mọi nhánh được báo cáo. Gọi API trả phí cần
  nhóm duyệt (CLAUDE.md §1). Không so số Gemini chấm với số GPT-4o chấm.

### B5. ID, schema, resume

- Khoá bản ghi: `dataset_id, experiment_id, run_id, query_id, gen_repeat, seed, judge_pass, attempt, request_id`, kèm
  `config_hash` (sha256 của run config chuẩn hoá) và `index_hash`, `split_hash`, `timestamp` (UTC ISO-8601).
- Resume = bỏ qua khoá `(query_id, gen_repeat, config_hash)` đã có bản ghi `status=ok`; thử lại được thì tăng `attempt`.
  Không resume theo số dòng, không ghép theo văn bản câu hỏi. Thư mục run có `config_hash` khác → từ chối ghi tiếp.
- Metric chỉ dùng bản ghi `status=ok` cuối cùng của mỗi khoá.

### B6. Metrics và thống kê

- Acc = accurate / n_valid; Err = error / n_valid; Neither = neither / n_valid; báo kèm `n_valid`, `n_expected`,
  `n_parse_failed`, `n_infra_failed`, `n_early_exit` (theo lý do). Err không mặc định bằng 1 − Acc.
- So sánh hai cấu hình: ghép theo `query_id`; với một lượt sinh dùng McNemar chính xác, báo `b lên / c xuống, p`
  (tái dùng `mcnemar_p` trong `reproduce/screening/screen_variant.py`); với nhiều lượt dùng paired bootstrap theo query giữ
  nguyên các lượt trong query. Không coi verdict lặp là mẫu độc lập. Biên tương đương (nếu cần kết luận "không kém hơn")
  chọn và ghi trước khi xem kết quả. Quy tắc đọc nhiễu sinh của CLAUDE.md §3 áp dụng.
- Retrieval: MultiHop-RAG — Evidence Recall@k theo tài liệu (url) và theo chunk chứa `fact` (ánh xạ ở `MHR-07`);
  2Wiki — theo đoạn trong `supporting_facts`. Full Evidence Success@k = mọi evidence của câu có trong Sources. Cột Evidence
  chỉ dùng để chấm, không bao giờ vào hệ thống.

### B7. Lưu trữ, backup

- Run: `runs/<dataset_id>/qwen/<experiment_id>/<run_id>/` (mỗi run một thư mục mới, có `status`: planned · running ·
  partial · completed · failed · invalid). Manifest cấp dataset: `runs/<dataset_id>/dataset_manifest.json`,
  `runs/<dataset_id>/split_manifest.json`.
- `runs/` và `indexes/` phải vào `.gitignore` trước lượt đầu (task `S-02`). Gitignore **không** có nghĩa là bỏ lưu: mỗi mốc
  (index đóng băng, run completed) đóng gói + sha256, chép lên `<BACKUP_ROOT>`, mở thử và so checksum, rồi mới được dọn bản
  local. Việc có commit index như `LiHua-World-qwen-modal/` hay không là quyết định nhóm (mục H).
- Không bao giờ ghi API key, header `Authorization`, URL có token vào log.

---

## C. Việc chung trước khi tách (S) và hai luồng dataset

### C0. Việc chung — S

Mỗi task chung có một người làm và người còn lại review. Không task nào ở C1/C2 bắt đầu P1 trước khi `S-01`…`S-09` xong.

**S-01 · Khoá protocol và nguồn** — Người 1 làm, Người 2 review
- Phụ thuộc: —
- Đầu vào: tài liệu này, `<PAPER_PDF>`, kết quả `V-01`…`V-06`
- Hành động: tạo `docs/research/PROTOCOL_QWEN_NEW_DATASETS.md` [CẦN TRIỂN KHAI] chép các quyết định mục B đã chốt; đưa PDF
  lên `<BACKUP_ROOT>/paper/`.
- Lệnh dự kiến: `sha256sum <PAPER_PDF>` (phải ra `a62cad85…54bd86`)
- Đầu ra: protocol v1, sha256 PDF trong protocol
- Nghiệm thu: hai người cùng ký tên + ngày trong protocol; mọi mục B có giá trị hoặc ghi rõ "chưa chốt, chặn bước …"

**S-02 · Chuẩn bị repo** — Người 2 làm, Người 1 review
- Phụ thuộc: —
- Hành động: mỗi người một branch/worktree (`research/mhr-qwen`, `research/2wiki-qwen` — đề xuất); thêm `runs/`, `indexes/`,
  `dataset/*/processed/` vào `.gitignore`; tạo bốn file trạng thái trong `docs/research/` (`PROJECT_STATE.md`,
  `BASELINE_MANIFEST.yaml`, `EXPERIMENT_HISTORY.md`, `CODE_MAP.md`). `baseline.yaml` gốc **không** sửa (CLAUDE.md §2).
- Lệnh dự kiến: `git worktree add ../MiniRAG-mhr -b research/mhr-qwen dev`; `git check-ignore -v runs/x indexes/x`
- Đầu ra: `.gitignore` cập nhật, bốn file khung
- Nghiệm thu: `git check-ignore` khớp cả hai đường dẫn; `git status` sạch trên `dev` sau merge

**S-03 · Môi trường** — mỗi người tự làm trên máy mình
- Hành động: ghi `docs/research/env/<người>.md` [CẦN TRIỂN KHAI]: OS, Python, `pip freeze` (so với `requirements.lock.txt`),
  CPU/RAM/GPU local, backend Qwen, phần cứng phục vụ. Script mới viết bằng Python thuần, không phụ thuộc zsh/macOS.
- Lệnh dự kiến: `<PYTHON> -m pip freeze > runs/_env/<người>_freeze.txt`
- Nghiệm thu: import được `minirag`, `tiktoken`, `transformers`; tải được all-MiniLM-L6-v2

**S-04 · Logger request LLM** — Người 1
- Hành động: bọc `llm_model_func` (không sửa `gemini_complete_if_cache`) thành `reproduce/research/llm_logging.py`
  [CẦN TRIỂN KHAI]: ghi JSONL ngay sau mỗi lời gọi — phase (`extract`/`glean`/`kw_parse`/`answer`/`judge`), messages đủ,
  kwargs (`max_tokens`, `seed`, …), response thô, `response.model`, usage, latency, attempt, lỗi; bỏ key/header.
  Phase truyền qua `contextvars`.
- Nghiệm thu: fixture `tests/research/test_llm_logging.py` [CẦN TRIỂN KHAI] với LLM giả: (a) request gửi đi giống hệt khi
  bật/tắt logger; (b) không có chuỗi key trong log; (c) process bị kill giữa chừng → các dòng đã ghi đọc được.

**S-05 · Log truy hồi đầy đủ và đường thoát sớm** — Người 1
- Hành động: thêm công tắc mới, **mặc định tắt**, ví dụ `MINIRAG_RETRIEVAL_LOG=<jsonl>` [CẦN TRIỂN KHAI] trong
  `minirag/operate.py`: bản ghi gồm đầu ra parser từ khoá (thô + đã parse), ứng viên/hạng/điểm từng nhánh, chunk được chọn,
  điểm cắt A1, văn bản context cuối, và bản ghi cho **mọi** đường thoát (`kw_parse_failed`, `no_nodes`, `no_edges`).
  `MINIRAG_CONTEXT_LOG` cũ giữ nguyên trường.
- Nghiệm thu: fixture index nhỏ đóng băng; không đặt biến → context và prompt sha256 trùng trước khi sửa; đặt biến → mọi
  câu có đúng một bản ghi, kể cả câu thoát sớm.

**S-06 · Runner index / QA / judge / metrics dùng chung** — Người 1 (index, QA), Người 2 (judge, metrics)
- Hành động [CẦN TRIỂN KHAI]:
  - `reproduce/research/index_run.py` — đọc `docs.jsonl` chuẩn hoá, chèn từng tài liệu, ghi `index_manifest.json`,
    `index_requests.jsonl` (qua S-04), `events.jsonl`, mapping `doc_id ↔ doc-<md5>` và `chunk_id → doc_id`.
  - `reproduce/research/qa_run.py` — đọc `queries.jsonl` + `run_config.yaml`, đặt env theo config, khoá resume B5, ghi
    `generation.jsonl`, `retrieval.jsonl` (qua S-05), `events.jsonl`; lỗi hạ tầng → `status=infra_failed`, không thành answer.
  - `reproduce/research/judge_run.py` — rubric version, JSON parser, `parse_failed`/`judge_failed`, raw response, `pass_id`,
    xáo thứ tự theo seed.
  - `reproduce/research/metrics.py` — `per_question.csv`, `metrics.json`, McNemar, bootstrap, bảng mục 8 kế hoạch nghiên cứu.
  - `reproduce/research/check_run.py` — đếm dự kiến/thực tế, ID duy nhất, checksum, không trộn config.
  - Tái dùng: `build_rag`/`build_query_param` (`reproduce/gemini_common.py`), `mcnemar_p` (`reproduce/screening/screen_variant.py`),
    `BM25Index` (`minirag/bm25.py`).
- Nghiệm thu: `tests/research/` chạy offline với LLM giả: resume sau kill không lặp câu; đổi config → bị từ chối; judge trả
  rác → `parse_failed`; metric tính lại từ `per_question.csv` khớp `metrics.json`.

**S-07 · Ba công tắc ablation B2** — Người 2
- Hành động [CẦN TRIỂN KHAI], đều mặc định tắt: `MINIRAG_CHUNK_FUSION=bm25` (B2_NO_VECTOR); `MINIRAG_DROP_ENTITIES=1`
  (B2_NO_ENT — giữ nguyên Sources, chỉ thay bảng Entities bằng header rỗng); `MINIRAG_NO_GRAPH=1` hoặc mode riêng
  (HYBRID_NO_GRAPH — không gọi parser/đồ thị). Tên là đề xuất.
- Nghiệm thu (fixture): B2_NO_BM25 (`vector`) cho thứ tự chunk trùng `_rrf_fuse(chunks_ids)`; B2_NO_ENT có Sources
  byte-identical với B2 trên cùng câu (dựng context một lần, so sha256 phần Sources); HYBRID_NO_GRAPH không phát sinh lời gọi
  phase `kw_parse` và vẫn ghi bản ghi truy hồi; mặc định (không biến) → sha256 context không đổi.

**S-08 · Fixture offline** — Người 2
- Hành động: `tests/research/fixtures/` [CẦN TRIỂN KHAI] — 5 tài liệu, 6 câu, LLM giả trả kết quả trích xuất cố định.
- Nghiệm thu: toàn bộ `tests/research` chạy không mạng: `<PYTHON> -m pytest tests/research -q` (chưa kiểm thử)

**S-09 · Kiểm chéo schema** — cả hai
- Hành động: mỗi người chạy runner trên fixture, đổi file cho nhau, người kia ghép `generation`/`judge`/`per_question`
  bằng `query_id` và tính lại metric.
- Nghiệm thu: hai người ra cùng số; ghi vào `EXPERIMENT_HISTORY.md`.

**Task xác minh V** (chặn bước phụ thuộc ghi ở mỗi task)

| ID | Người | Xác minh | Cách làm | Chặn |
|---|---|---|---|---|
| V-01 | Người 1 + Người 2 | Hiện thực −I, −Rchunk, −Redge | tìm trong repo upstream `HKUDS/MiniRAG` (branch, issue, script), đối chiếu §4.4; nếu không có, hỏi tác giả; ghi một định nghĩa hiện thực cho mỗi biến thể hoặc "không đủ căn cứ — không chạy" | mọi lượt MR_MINUS_* |
| V-02 | Người 2 | Cách tác giả dựng corpus/sample 2Wiki và MultiHop-RAG | đọc lại toàn PDF + repo upstream + issue; nếu không có → giữ nhãn "chuyển đổi benchmark" ở B3 | khoá N của 2Wiki (`2W-03`), cột "tái hiện" trong báo cáo |
| V-03 | Người 1 | Ánh xạ "top-k = 5 documents", "6000 tokens", k và n của bài báo vào tham số code | đọc `minirag/operate.py` (`_build_mini_query_context`, `kwd2chunk`, chỗ dùng `top_k`) và `minirag/base.py`; viết bảng tương ứng hoặc ghi "không ánh xạ được" | định nghĩa MR_FULL |
| V-04 | Người 1 | Sampling mặc định của vLLM với Qwen (temperature, top_p, repetition penalty) và HF revision | đọc tài liệu vLLM 0.11.0 + `generation_config.json` của revision đã ghim; xác nhận bằng một request smoke có log | P2 |
| V-05 | Người 1 | `llm_model_max_token_size=200` có ảnh hưởng runtime không | log `max_tokens` thực gửi ở pilot index (S-04); kiểm có đầu ra trích xuất nào bị cắt ở 200 token | kết luận chất lượng đồ thị ở P1 |
| V-06 | Người 2 | ID model Gemini Flash | gọi API liệt kê model (metadata, không tốn quota sinh) bằng khoá riêng; ghim ID; một request thử lưu `response.model` | P2 |

### C1. Luồng A — MultiHop-RAG (Người 1)

Thư mục: `runs/multihop_rag/`, `indexes/multihop_rag-qwen-full609/`, dữ liệu chuẩn hoá `dataset/MultiHop-RAG/processed/`.

**MHR-01 · Kiểm kê dữ liệu thô** — phụ thuộc S-02
- Đầu vào: `dataset/MultiHop-RAG/raw/{corpus.json,MultiHopRAG.json}`
- Lệnh dự kiến: `sha256sum dataset/MultiHop-RAG/raw/*.json`
- Đầu ra: phần "source" của `dataset_manifest.json`
- Nghiệm thu: sha256 khớp A4; 609 bài, 2.556 câu; đếm loại khớp A4

**MHR-02 · Chuẩn hoá** — phụ thuộc MHR-01, S-01
- Hành động: `reproduce/research/prepare_multihop_rag.py` [SCRIPT CHƯA TỒN TẠI] → `docs.jsonl` (`doc_id`=url), `queries.jsonl`
  (`query_id`, câu hỏi, loại — **không** có đáp án), `gold.jsonl` (đáp án, evidence url/fact) tách riêng.
- Lệnh dự kiến: `<PYTHON> reproduce/research/prepare_multihop_rag.py --raw dataset/MultiHop-RAG/raw --out dataset/MultiHop-RAG/processed  # [SCRIPT CHƯA TỒN TẠI]`
- Nghiệm thu: query_id duy nhất; mọi url evidence ánh xạ tới một `doc_id`; `queries.jsonl` không chứa trường gold

**MHR-03 · Đo chunk thật (offline)** — phụ thuộc MHR-02
- Hành động: chạy `chunking_by_token_size` (`operate.py:42`) trên 609 bài, không gọi LLM
- Đầu ra: số chunk, phân bố token, ước lượng tĩnh số lời gọi = chunk × 2 (A5)
- Nghiệm thu: số liệu ghi vào `dataset_manifest.json`, thay ước lượng ≈1.533 ở A4

**MHR-04 · Thiết kế split** — phụ thuộc MHR-02
- Hành động: `reproduce/research/split_groups.py` [SCRIPT CHƯA TỒN TẠI] báo cáo phân bố nhóm cho từng quy tắc ứng viên
  (thành phần liên thông theo url; nguyên tập url; + gần trùng), tỷ lệ loại câu hai phía, số cặp dev–test chung evidence.
  Chọn quy tắc **sau** khi đọc báo cáo; ghi lý do.
- Đầu ra: `split_manifest.json` (seed, quy tắc, ID dev, ID test nội bộ, nhóm), `split_report.md`
- Nghiệm thu: không ID nào ở cả hai phía; mỗi nhóm nằm trọn một phía; phân bố loại câu chênh ≤ mức chốt trước

**MHR-05 · Pilot index corpus con** — phụ thuộc S-04…S-08, V-04, MHR-03
- Hành động: index ~20–30 bài chọn có seed (kiểm kỹ thuật, không phải benchmark)
- Lệnh dự kiến: `<PYTHON> reproduce/research/index_run.py --dataset multihop_rag --subset pilot30 --workingdir indexes/multihop_rag-qwen-pilot30  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: index pilot, `index_requests.jsonl`, số lời gọi/chunk thực tế, thời gian, lỗi
- Nghiệm thu: mọi chunk có ≥1 cặp request extract+glean có response; không response nào bị cắt cụt chưa giải thích (V-05);
  dự toán index toàn bộ từ số đo; **dừng và báo nhóm** nếu dự toán vượt trần (G3)

**MHR-06 · Index chính thức** — phụ thuộc MHR-05 và nhóm duyệt dự toán
- Lệnh dự kiến: `<PYTHON> reproduce/research/index_run.py --dataset multihop_rag --subset full609 --workingdir indexes/multihop_rag-qwen-full609  # [SCRIPT CHƯA TỒN TẠI]`
- Đầu ra: index, `index_manifest.json` (thống kê node/cạnh/chunk, checksum từng file), log
- Nghiệm thu: 609/609 tài liệu `processed`; mọi chunk có `full_doc_id` hợp lệ; mọi chunk có trong `vdb_chunks.json`; node
  đồ thị trỏ về chunk tồn tại; backup + checksum (B7); đánh dấu chỉ đọc

**MHR-07 · Ánh xạ evidence → chunk** — phụ thuộc MHR-06
- Hành động: với mỗi `fact`, tìm chunk chứa (khớp chuỗi sau chuẩn hoá; ghi tỷ lệ không khớp)
- Đầu ra: `gold_chunks.jsonl` (chỉ dùng chấm truy hồi)
- Nghiệm thu: tỷ lệ fact ánh xạ được báo cáo; fact không khớp liệt kê, không đoán

**MHR-08 · Smoke 10–20 câu dev** — phụ thuộc MHR-06, V-06, S-09
- Cấu hình: GROUP_BASE và B2_FULL, 1 lượt sinh × 1 lượt chấm
- Lệnh dự kiến: `<PYTHON> reproduce/research/qa_run.py --config configs/research/multihop_rag/b2_full.yaml --split dev --sample smoke20 --seed 101  # [SCRIPT CHƯA TỒN TẠI]` rồi `judge_run.py` và `check_run.py` tương ứng
- Nghiệm thu: retrieval/generation/judge ghép đúng `query_id`; có đủ loại câu; đường thoát sớm (nếu có) được ghi

**MHR-09 · Pilot 50–100 câu dev** — phụ thuộc MHR-08
- Cấu hình: GROUP_BASE, B2_FULL, MR_FULL (nếu V-03 đã chốt), 1 lượt sinh
- Đầu ra: `report.md` từng run: acc/err/neither/parse_failed, latency p50/p95, token, số lời gọi, dự toán cho P4–P6
- Nghiệm thu: n_valid = n_expected hoặc danh sách thiếu có lý do; dự toán ghi vào G3

**MHR-10 · Ablation trên cùng mẫu dev** — phụ thuộc MHR-09, S-07, (V-01 cho MR_MINUS_*)
- Thứ tự: B2_NO_BM25 → B2_NO_VECTOR → B2_NO_ENT → HYBRID_NO_GRAPH → MR_MINUS_* (nếu định nghĩa được)
- Nghiệm thu: mỗi ablation so với **bản đầy đủ tương ứng** (B2_FULL hoặc MR_FULL), McNemar ghép cặp; kết quả âm vẫn ghi

**MHR-11 · Phân tích và một điều chỉnh** — phụ thuộc MHR-10
- Hành động: failure taxonomy trên dev; nếu đề xuất điều chỉnh: đủ 5 bước CLAUDE.md §1b, đổi **một** thành phần, đăng ký
  trước trong `EXPERIMENT_HISTORY.md`
- Nghiệm thu: giả thuyết ghi trước khi chạy; không dùng câu test nội bộ

**MHR-12 · Xác nhận dev** — phụ thuộc MHR-11
- Cấu hình đã chọn × 3 lượt sinh (101/202/303) × số lượt chấm chốt trước, trên toàn bộ dev nội bộ
- Nghiệm thu: định nghĩa "completed" (F2); người kia kiểm chéo một mẫu

**MHR-13 · Bàn giao** — phụ thuộc MHR-12
- Đầu ra: protocol + manifest, index + log trích xuất, run artifact, script tái lập, `per_question.csv`, metrics, `report.md`,
  cập nhật bốn file trạng thái; backup đã kiểm

### C2. Luồng B — 2WikiMultiHopQA (Người 2)

Thư mục: `runs/2wiki/`, `indexes/2wiki-qwen-<corpus_id>/`, `dataset/2WikiMultiHopQA/processed/`.

**2W-01 · Kiểm kê dữ liệu thô** — phụ thuộc S-02
- Lệnh dự kiến: `cat dataset/2WikiMultiHopQA/raw/data_ids_april7.zip.part-* > <tạm>/data_ids_april7.zip && sha256sum <tạm>/data_ids_april7.zip`
  (README có lệnh Windows tương ứng); `sha256sum dataset/2WikiMultiHopQA/raw/extracted/*.json`
- Nghiệm thu: zip khớp `95DF2BF5…5529EEF`; dev 12.576 câu có nhãn; ghi nhận test không có nhãn vào manifest

**2W-02 · Chuẩn hoá dev** — phụ thuộc 2W-01, S-01
- Hành động: `reproduce/research/prepare_2wiki.py` [SCRIPT CHƯA TỒN TẠI] → `paragraphs.jsonl` (doc_id = title), `queries.jsonl`
  (`query_id` = `_id` gốc), `gold.jsonl` (answer, aliases từ `id_aliases.json`, supporting_facts, evidences)
- Nghiệm thu: `_id` duy nhất; mỗi title một văn bản; mọi title trong supporting_facts có trong context của câu

**2W-03 · Chọn pool N và corpus** — phụ thuộc 2W-02, V-02
- Hành động: tính số đoạn, token, chunk (offline, như MHR-03) cho vài N; chọn N theo số đo + ngân sách G3; ghi rõ đây là
  "chuyển đổi benchmark do nhóm đề xuất" nếu V-02 không ra bằng chứng
- Đầu ra: `corpus_manifest.json` (seed, N, danh sách query pool, danh sách đoạn), `corpus_id`
- Nghiệm thu: corpus gồm **cả** gold và distractor của mọi câu pool; không đoạn nào ngoài 10 đoạn của các câu pool

**2W-04 · Thiết kế split** — phụ thuộc 2W-03
- Hành động: `split_groups.py` [SCRIPT CHƯA TỒN TẠI] trên pool: phân bố thành phần theo title gold (và đối chứng theo mọi
  title context), tỷ lệ 4 loại câu hai phía; chọn quy tắc sau khi đọc báo cáo
- Đầu ra: `split_manifest.json` (`internal_dev`, `internal_test`), `split_report.md`
- Nghiệm thu: như MHR-04; ghi rõ test là test nội bộ

**2W-05 · Pilot index** — phụ thuộc S-04…S-08, V-04, 2W-03
- Hành động: index ~200 đoạn (seed) bằng `index_run.py` [SCRIPT CHƯA TỒN TẠI]; đo lời gọi/chunk thật (đoạn ~100 token → mỗi
  đoạn một chunk, cần xác nhận); kiểm BM25 với tên có dấu (tách từ `[a-z0-9]+` của `minirag/bm25.py` cắt "Żuławski" thành
  mảnh ASCII) — **ghi giới hạn, không chỉnh tokenizer** vì đặc tả BM25 đã chốt
- Nghiệm thu: như MHR-05; dự toán index toàn pool

**2W-06 · Index chính thức** — phụ thuộc 2W-05, nhóm duyệt dự toán — nghiệm thu như MHR-06

**2W-07 · Ánh xạ supporting_facts → chunk** — phụ thuộc 2W-06 — đầu ra `gold_chunks.jsonl`

**2W-08 … 2W-13** — giống MHR-08 … MHR-13 (smoke, pilot, ablation, phân tích, xác nhận dev, bàn giao) với
`configs/research/2wiki/*.yaml` [CẦN TRIỂN KHAI], loại câu compositional/comparison/bridge_comparison/inference.
Không có loại null → bảng refusal chỉ báo từ chối sai trên câu có đáp án.

---

## D. Ma trận thí nghiệm

| ID | Nhóm | Cấu hình / flag | Index | Implementation | So với |
|---|---|---|---|---|---|
| MR_FULL | gốc paper (mở rộng) | chốt ở V-03 | chung | [CHƯA XÁC MINH] | — (mốc ablation MiniRAG) |
| MR_MINUS_I | ablation gốc (mở rộng) | description-based indexing — chốt ở V-01 | **riêng** | [CHƯA XÁC MINH] | MR_FULL |
| MR_MINUS_RCHUNK | ablation gốc (mở rộng) | bỏ chunk nodes khi truy hồi đồ thị — **không** đồng nghĩa xoá Sources | chung | [CHƯA XÁC MINH] | MR_FULL |
| MR_MINUS_REDGE | ablation gốc (mở rộng) | bỏ thông tin cạnh khi truy hồi — **không** đồng nghĩa bỏ Entities khỏi prompt | chung | [CHƯA XÁC MINH] | MR_FULL |
| GROUP_BASE | baseline nhóm | A6 | chung | [CÓ SẴN] | MR_FULL (báo chênh, không gọi là đóng góp) |
| B2_FULL | cải tiến nhóm | `MINIRAG_CHUNK_FUSION=vector_bm25` | chung | [CÓ SẴN] | GROUP_BASE, MR_FULL |
| B2_NO_BM25 | ablation nhóm | `MINIRAG_CHUNK_FUSION=vector` | chung | [CÓ SẴN] (tương đương kiểm ở S-07) | B2_FULL |
| B2_NO_VECTOR | ablation nhóm | đề xuất `MINIRAG_CHUNK_FUSION=bm25` | chung | [CẦN TRIỂN KHAI] | B2_FULL |
| B2_NO_ENT | ablation nhóm | đề xuất `MINIRAG_DROP_ENTITIES=1` | chung | [CẦN TRIỂN KHAI] | B2_FULL |
| HYBRID_NO_GRAPH | đối chứng | đề xuất `MINIRAG_NO_GRAPH=1` | chung (không dùng đồ thị) | [CẦN TRIỂN KHAI] | B2_FULL |

- Áp MR_MINUS_* lên hai dataset mới là **thí nghiệm mở rộng**: không thay thế phần tái hiện Table 2 trên LiHuaWorld còn
  thiếu.
- B2_NO_ENT vẫn chạy đồ thị phía trước (vẫn có đường thoát `None`); chỉ HYBRID_NO_GRAPH bỏ đồ thị hoàn toàn.
- Không chạy cấu hình nào khi định nghĩa còn [CHƯA XÁC MINH].

---

## E. Kế hoạch chạy

| Giai đoạn | Việc (cả hai luồng) | Task | Cổng chuyển |
|---|---|---|---|
| P0 | Protocol, repo, môi trường, logger, runner, flag, fixture, xác minh | S-01…S-09, V-01…V-06, MHR-01…04, 2W-01…04 | fixture xanh; split khoá; MR_FULL đã định nghĩa hoặc ghi "chặn"; model ID judge ghim |
| P1a | Pilot index corpus con | MHR-05, 2W-05 | lời gọi/chunk đo được; không lỗi chưa giải thích; dự toán được duyệt |
| P1b | Index chính thức, đóng băng, backup | MHR-06/07, 2W-06/07 | kiểm liên kết doc–chunk–graph–vector; checksum; backup mở được |
| P2 | Smoke 10–20 câu dev | MHR-08, 2W-08 | ghép ID đúng; không parse lỗi bị che |
| P3 | Pilot 50–100 câu dev: GROUP_BASE, MR_FULL, B2_FULL | MHR-09, 2W-09 | báo cáo lỗi, latency, chi phí đo thật |
| P4 | Ablation lần lượt trên cùng mẫu dev | MHR-10, 2W-10 | mỗi lượt có đối chứng và báo cáo riêng |
| P5 | Phân tích, một điều chỉnh, chạy lại dev | MHR-11, 2W-11 | đăng ký trước; không dùng test nội bộ |
| P6 | Xác nhận dev × 3 lượt sinh | MHR-12, 2W-12 | "completed" theo F2; kiểm chéo |
| P7 | Tổng hợp hai dataset; chuyển SLM khác | MHR-13, 2W-13 | kết quả + giới hạn ghi đủ (không cần kết quả dương) |
| P8 | Đóng băng phương pháp; chạy test nội bộ; GPT-4o chấm | sau các đợt SLM | nhóm duyệt chi phí; mọi nhánh cùng giao thức cuối |

Quy mô smoke/pilot là vận hành, không đủ để kết luận khoa học. Không index lại cho ablation retrieval khi index không đổi.
Đổi model sinh trên index Qwen là thiết kế riêng, không phải tái hiện end-to-end SLM khác.

**LiHuaWorld — không chạy lại trong đợt này; việc còn thiếu ghi riêng:** tái hiện Table 2 (−I, −Rchunk, −Redge) phụ thuộc
V-01; chấm GPT-4o cho baseline/B2 LiHua thuộc P8; đối chiếu lại số tham chiếu trong `CLAUDE.md`/`README.md` với
miniRAG1.pdf.

---

## F. Artifact và bàn giao

### F1. Artifact mỗi run

| File | Nội dung bắt buộc | Ghi lúc | Git? |
|---|---|---|---|
| `dataset_manifest.json` | source, sha256, số tài liệu/câu, loại câu, mapping doc, chuyển đổi đã áp | P0 | có (nhỏ) |
| `split_manifest.json` | seed, quy tắc, nhóm, ID dev; ID test nội bộ (bản đầy đủ chỉ ở `<BACKUP_ROOT>`) | P0 | chỉ phần dev |
| `index_manifest.json` | corpus_id, chunking, model+revision, embedding, prompt sha256, commit, checksum file, thống kê, lỗi | P1 | có |
| `index_requests.jsonl` | messages, kwargs, response thô, chunk_id, model, latency, attempt, cache | ngay sau mỗi request | không — backup |
| `run_manifest.json` | experiment/run ID, config + `config_hash`, seed, prompt/rubric version, env, index/split hash, endpoint, concurrency, lệnh chạy, `status` | đầu run, cập nhật cuối run | có |
| `retrieval.jsonl` | query_id, parser output thô/parse, ứng viên/hạng/điểm từng nhánh, chunk chọn, truncation, lý do thoát sớm | ngay sau mỗi câu | không — backup |
| `generation.jsonl` | messages gửi Qwen, context đầy đủ (Entities + Sources), response thô, answer xử lý, status | ngay sau mỗi câu | không — backup |
| `judge.jsonl` | rubric version, đầu vào judge, model trả về, response thô, label, pass_id, lỗi | ngay sau mỗi verdict | không — backup |
| `events.jsonl` | start/end, lỗi, timeout, retry, resume, checkpoint, thoát sớm | ngay khi xảy ra | không — backup |
| `per_question.csv`, `metrics.json` | ghép cặp được; metric tính lại được từ per_question | cuối run | có |
| `report.md` | kết luận, giới hạn, lên/xuống, chi phí, lệnh tái lập, quyết định tiếp | cuối run | có |

Ghi từng dòng rồi flush; process chết thì phần đã xong dùng lại được. Gold/evidence ở `gold.jsonl` riêng, không đi vào
generation.

### F2. Một run chỉ "completed" khi

- đủ câu dự kiến, hoặc có danh sách thiếu kèm lý do phân loại;
- request/context/answer/judge ghép được bằng ID; không lỗi parse bị che;
- manifest và checksum index/split khớp protocol;
- metric tính lại được từ per-question;
- báo cáo nêu cả lên lẫn xuống, ví dụ lỗi có bằng chứng, giới hạn;
- có lệnh tái lập, backup đã kiểm, người còn lại kiểm chéo một mẫu.

### F3. Bàn giao mỗi benchmark

Protocol + manifest; index/checkpoint + `index_requests.jsonl`; raw run artifact; script tái lập; `per_question.csv`; metrics;
`report.md`; ledger trong `docs/research/EXPERIMENT_HISTORY.md`. Sau mỗi thí nghiệm cập nhật `docs/research/PROJECT_STATE.md`,
`docs/research/BASELINE_MANIFEST.yaml`, `docs/research/EXPERIMENT_HISTORY.md`, và `docs/research/CODE_MAP.md` khi code đổi —
ghi rõ artifact nằm ở đâu và ai chịu trách nhiệm.

---

## G. Phân công, phụ thuộc, ngân sách

### G1. Phân công

| | Người 1 | Người 2 |
|---|---|---|
| Luồng | A — MultiHop-RAG (MHR-01…13) | B — 2WikiMultiHopQA (2W-01…13) |
| Việc chung | S-01, S-04, S-05, S-06 (index, QA); V-01 (cùng), V-03, V-04, V-05 | S-02, S-06 (judge, metrics), S-07, S-08; V-01 (cùng), V-02, V-06 |
| Review | S-02, S-07, S-08 | S-01, S-04, S-05 |
| Kiểm chéo | S-09; một mẫu run của Người 2 ở P6 | S-09; một mẫu run của Người 1 ở P6 |

Mỗi người làm trọn luồng của mình (dữ liệu → index → baseline → cải tiến → ablation → chấm → báo cáo), không chia một người
chỉ code, một người chỉ chấm.

### G2. Phụ thuộc và tránh tranh chấp

- Thống nhất trước khi tách: B1–B7, schema F1, rubric v1, runner S-06, flag S-07. Sau `S-09` hai luồng độc lập.
- Index, thư mục run, dữ liệu chuẩn hoá: riêng mỗi người; không ai ghi vào thư mục của người kia hay index LiHua.
- Endpoint: dùng chung được (B1) khi có lịch và ghi concurrency; đo latency chỉ khi không có tải khác, cùng phần cứng,
  phân biệt warm/cold, đo riêng thời gian model và toàn pipeline.
- Thay đổi code chung (`minirag/`, `reproduce/research/`) đi qua review của người kia; mọi công tắc mới mặc định tắt.

### G3. Ngân sách

- Trần tổng cho compute: **dưới 1 triệu VND** cho cả đợt. Trước mỗi pilot/run lớn: kiểm phần còn lại, đặt trần cho lượt
  đó, dừng khi chạm trần.
- Công thức (không phải dự toán):
  - Lời gọi index ≈ số chunk × (1 + gleaning) + retry — đọc tĩnh A5; số thật lấy từ pilot P1a.
  - Số answer = số câu × số cấu hình cần sinh × số lượt sinh; số lời gọi QA ≈ số answer × 2 (parser + sinh; HYBRID_NO_GRAPH
    chỉ 1).
  - Số verdict = số answer × số lượt chấm + retry + audit.
- Cỡ tham chiếu (đọc tĩnh, **chưa đo**): MultiHop-RAG ≈ 1.533 chunk → ≈ 3.066 lời gọi index; 2Wiki pool 500 câu → 3.324 đoạn
  → ≈ 6.650 lời gọi nếu mỗi đoạn một chunk. Không quy đổi ra USD/giờ khi chưa có số đo pilot.
- Tham chiếu LiHua (CLAUDE.md): 1.406 lời gọi trong 30–60 phút trên A10G — số của dataset khác, chỉ để đối chiếu, không
  dùng làm dự toán.
- Gemini: không mặc định miễn phí; ghi quota/khoá dùng cho mỗi lượt chấm. GPT-4o (P8) cần nhóm duyệt.

---

## H. Còn thiếu — và chặn bước nào

| # | Thiếu | Chặn | Task xử lý |
|---|---|---|---|
| 1 | Hiện thực −I/−Rchunk/−Redge | MR_MINUS_* (P4) | V-01 |
| 2 | Cách tác giả dựng corpus/sample MultiHop-RAG và 2Wiki | khoá N 2Wiki (2W-03); cột "tái hiện" trong báo cáo | V-02 |
| 3 | Ánh xạ top-k/ngân sách bài báo vào code | định nghĩa MR_FULL (P3) | V-03 |
| 4 | Sampling vLLM và HF revision | P2 | V-04 |
| 5 | Ảnh hưởng của `llm_model_max_token_size=200` | kết luận chất lượng đồ thị (P1) | V-05 |
| 6 | ID model Gemini Flash | P2 | V-06 |
| 7 | Nơi backup chung `<BACKUP_ROOT>` và quyền truy cập | đánh dấu completed (P1b trở đi) | nhóm chốt ở S-01 |
| 8 | Ngân sách còn lại thực tế | P1b, P3 | nhóm chốt trước MHR-06/2W-06 |
| 9 | Có commit index mới vào Git như LiHua hay chỉ backup ngoài | P1b | nhóm chốt ở S-02 |
| 10 | Có sửa số tham chiếu trong `README.md`/`CLAUDE.md` theo miniRAG1.pdf không | không chặn đợt Qwen; chặn viết báo cáo | nhóm quyết |
| 11 | Định dạng văn bản tài liệu MultiHop-RAG (metadata nào đưa vào) | MHR-02 | ghi quyết định vào protocol S-01 |

Tên người cụ thể không chặn bước nào: tài liệu dùng Người 1 / Người 2.

---

## I. Thứ tự tóm tắt và việc đầu tiên

**Thứ tự:** S-01/S-02/S-03 song song → V-01…V-06 cùng S-04…S-08 → S-09 → kiểm kê/chuẩn hoá/split từng dataset → pilot index →
index chính thức + đóng băng → smoke → pilot GROUP_BASE/MR_FULL/B2_FULL → ablation từng cái → phân tích + một điều chỉnh →
xác nhận dev 3 lượt sinh → tổng hợp → (sau các đợt SLM) đóng băng + test nội bộ + GPT-4o.

**Người 1 bắt đầu được ngay:** `S-01` (soạn protocol từ mục B) và `MHR-01` (sha256 + đếm dữ liệu thô) — cả hai không cần
API, không cần code mới. Tiếp theo `V-03` (đọc code ánh xạ top-k/ngân sách).

**Người 2 bắt đầu được ngay:** `S-02` (worktree, `.gitignore`, bốn file trạng thái) và `2W-01` (ráp zip, kiểm sha256) — không
cần API. Tiếp theo `V-02` (tìm cách tác giả dựng corpus 2Wiki).
