# MiniRAG Pipeline Audit & Improvement Plan

> **Phạm vi:** chỉ đọc code, trace luồng, audit graph đã dựng. **Không sửa code, không
> re-index, không tốn quota.**
> **Cơ sở:** code thực tế trong repo tại commit `dbfa0d1`, không suy luận từ paper/README.
> Mọi kết luận đều kèm `file:line`.
> **Dữ liệu audit:** index `./LiHua-World-gemini` — 442 tài liệu · 503 chunks · 770 nodes · 1.779 edges.

---

## 1. Executive Summary

MiniRAG trong repo này **chạy đúng như code viết**, nhưng code có bốn khiếm khuyết ở
tầng nền mà audit xác nhận được bằng số:

| # | Phát hiện | Bằng chứng code | Bằng chứng số |
|---|---|---|---|
| 1 | **Cơ chế answer-type-aware không bao giờ kích hoạt** | `operate.py:1423-1424` vs `networkx_impl.py:163` | 3/3 query trace ra 0 ứng viên |
| 2 | **Không có entity resolution** — gộp node bằng so khớp chuỗi chính xác | `operate.py:77` · `operate.py:117` | 27 nhóm trùng / 57 node; `LIHUA`(deg 300) ≠ `LI HUA`(deg 20) |
| 3 | **Tóm tắt mô tả bị tắt** → description phình vô hạn | `operate.py:150-152`, `209-211` (comment out) | description dài nhất **89.170 ký tự**, ghép từ **748 mảnh** |
| 4 | **Graph phân mảnh nặng** | hệ quả của 1–3 | **67 thành phần liên thông**; 59 node cô lập; 348/770 node có degree ≤ 1 |

Ngoài ra có ba lãng phí không ảnh hưởng độ chính xác nhưng đốt quota và thời gian:
`entity_vdb.upsert` gọi **hai lần liên tiếp** (`operate.py:364-381`), `entities_vdb`
**không được dùng** ở mode `mini`, và **LLM cache không bao giờ được ghi** dù
`enable_llm_cache=True`.

**Kết luận định hướng:** chưa cần đụng tới kiến trúc. Ba giả thuyết ưu tiên đều nằm
trong MiniRAG hiện tại, hai trong số đó **không cần index lại**.

---

## 2. Current Architecture

```
minirag/
├── minirag.py        MiniRAG dataclass · insert/ainsert · query/aquery · khởi tạo 8 storage
├── operate.py        chunking · extract_entities · merge/upsert · 3 query mode
├── prompt.py         PROMPTS + delimiter + DEFAULT_ENTITY_TYPES
├── base.py           QueryParam · các lớp Base*Storage
├── utils.py          tokenizer · path scoring · similarity · truncate
├── kg/networkx_impl.py   NetworkXStorage (graph)
├── kg/nano_vector_db_impl.py  NanoVectorDBStorage (4 VDB)
└── llm/              openai.py · hf.py · gemini.py (fork thêm)
```

**Storage backend mặc định** (`minirag.py:131-133`): `JsonKVStorage` ·
`NanoVectorDBStorage` · `NetworkXStorage`.

**Cấu hình index thực tế** (`minirag.py:139-145`): `chunk_token_size=1200` ·
`chunk_overlap_token_size=100` · `tiktoken_model_name="gpt-4o-mini"` ·
`entity_extract_max_gleaning=1` · `entity_summary_to_max_tokens=500`.

---

## 3. Indexing Pipeline

### 3.1 Bảng luồng

| Bước | File:Function | Input | Output | Storage đọc/ghi | LLM | Embed |
|---|---|---|---|---|---|---|
| 0 | `minirag.py:341 insert` → `:345 ainsert` | `str \| list[str]` | — | — | ❌ | ❌ |
| 1 | `minirag.py:413 apipeline_enqueue_documents` | list văn bản | `doc-<md5>` | ghi `doc_status` | ❌ | ❌ |
| 2 | `minirag.py:473 apipeline_process_enqueue_documents` | doc PENDING/FAILED/PROCESSING | chunks | ghi `chunks_vdb`, `full_docs`, `text_chunks`, `doc_status` | ❌ | ✅ |
| 3 | `operate.py:36 chunking_by_token_size` | content, 100, 1200 | list chunk | — | ❌ | ❌ |
| 4 | `minirag.py:363-409` **(bản vá fork)** | mọi doc PROCESSED | chunk chưa trích xuất | đọc/ghi `extracted_chunks.json` | ❌ | ❌ |
| 5 | `operate.py:233 extract_entities` | dict chunk | graph + 3 VDB | ghi tất cả | ✅ | ✅ |
| 5a | `operate.py:265 _process_single_content` | 1 chunk | `maybe_nodes`, `maybe_edges` | — | ✅ ×2 | ❌ |
| 5b | `operate.py:70 _handle_single_entity_extraction` | `record_attributes` | dict entity | — | ❌ | ❌ |
| 5c | `operate.py:91 _handle_single_relationship_extraction` | `record_attributes` | dict edge | — | ❌ | ❌ |
| 6 | `operate.py:117 _merge_nodes_then_upsert` | tên + list node | node_data | đọc/ghi graph | ❌ | ❌ |
| 7 | `operate.py:166 _merge_edges_then_upsert` | src, tgt, list edge | edge_data | đọc/ghi graph | ❌ | ❌ |
| 8 | `operate.py:364-406` | all_entities/relationships | — | ghi `entities_vdb` ×2, `entity_name_vdb`, `relationships_vdb` | ❌ | ✅ |
| 9 | `minirag.py:538 _insert_done` | — | file trên đĩa | `index_done_callback()` cho 8 storage | ❌ | ❌ |

### 3.2 Chunking — `operate.py:36`

Cắt theo **token tuyệt đối**, cửa sổ trượt `max_token_size - overlap_token_size` = 1100
token, không tôn trọng ranh giới câu/lượt chat. Với LiHua-World (log chat), **một chunk
có thể cắt ngang giữa lượt hội thoại**.

`content` được `.strip()` tại `:50` — nên `compute_mdhash_id` hash **nội dung đã strip**.

### 3.3 Entity extraction — `operate.py:265`

**Vòng gleaning** (`:274-287`) với `entity_extract_max_gleaning=1`:

```
i=0: gọi continue_prompt (LLM #2) → final_result += glean_result
     i == max_gleaning-1 → break
```

→ **đúng 2 lời gọi LLM mỗi chunk**. Nhánh `entiti_if_loop_extraction` (`:282`)
**không bao giờ chạy** khi gleaning = 1.

**Parse** (`:289-303`): tách theo `record_delimiter` `##` và `completion_delimiter`
`<|COMPLETE|>` (`prompt.py:2-4`), rồi mỗi record qua regex `re.search(r"\((.*)\)", record)`
tại `:297`.

> 🔴 `.*` là **greedy**. Nếu một record chứa nhiều cặp ngoặc hoặc LLM trả về sai định
> dạng, regex nuốt từ dấu `(` đầu tiên tới dấu `)` **cuối cùng**, ghép nhiều record
> thành một. Đây là nguồn sinh node rác — xem §7.2.

### 3.4 Normalization — chỉ có `.upper()`

| Trường | Xử lý | File:line |
|---|---|---|
| `entity_name` | `clean_str(record_attributes[1].upper())` | `operate.py:77` |
| `entity_type` | `clean_str(record_attributes[2].upper())` | `operate.py:80` |
| `src_id` / `tgt_id` | `clean_str(...upper())` | `operate.py:98-99` |

`clean_str` (`utils.py:174`) chỉ gỡ HTML unescape và ký tự điều khiển — **không** bỏ dấu
câu, **không** chuẩn hoá khoảng trắng, **không** so khớp mờ.

> 🔴 **Không tồn tại bước entity resolution nào trong toàn bộ pipeline.**

### 3.5 Merge — `operate.py:117` / `:166`

Gộp node bằng khoá `entity_name` **so khớp chuỗi chính xác** (`:127 get_node(entity_name)`).

- `entity_type` (`:135-141`): lấy type xuất hiện **nhiều nhất** (majority vote).
- `description` (`:143-145`): `GRAPH_FIELD_SEP.join(sorted(set(...)))` — **nối vô hạn**.
- Dòng `:150-152` gọi `_handle_entity_relation_summary` **bị comment out**.

> 🔴 `_handle_entity_relation_summary` (`operate.py:57`) được định nghĩa nhưng **chỉ
> xuất hiện trong comment** ở `:150` và `:209` → **dead code**. Hệ quả đo được:
> description dài nhất **89.170 ký tự** ghép từ **748 mảnh `<SEP>`**; 255 node có > 1 mảnh.

Trong `_merge_edges_then_upsert:199-208`: nếu cạnh trỏ tới node chưa tồn tại, code
**tự tạo node** với `entity_type='"UNKNOWN"'`. Các node này **không đi qua bước 8**,
nên không nằm trong VDB nào.

**Số đo:** graph có 770 node, `vdb_entities_name` chỉ có **754** → đúng **16 node
`UNKNOWN`** không thể được tìm thấy bởi Entity Matching.

### 3.6 Embedding & VDB — `operate.py:364-406`

> 🔴 **Khối `entity_vdb.upsert` bị lặp hai lần** (`:364-372` và `:373-381`). Cùng khoá
> `ent-<md5(entity_name)>`, khác `content`: lần đầu `entity_name + description` (dính
> liền), lần sau `entity_name + " " + description`. Lần sau **ghi đè** lần đầu.
> → **nhân đôi chi phí embedding của entities_vdb một cách vô ích.**

### 3.7 Complexity

**Upstream O(N²):** `minirag.py:363-377` dựng lại `inserting_chunks` từ **mọi** document
ở trạng thái `PROCESSED`, không chỉ document vừa thêm. Chèn N document lần lượt →
trích xuất lại toàn bộ corpus N lần. Chi tiết ở §6.

**Chi phí LLM sau khi vá:** 2 lời gọi/chunk × 503 chunk ≈ **1.006** lời gọi lý thuyết;
thực đo **653** (do một số chunk trùng nội dung giữa các file).

---

## 4. Query / Retrieval Pipeline

Điểm rẽ nhánh: `minirag.py:559 aquery` → theo `param.mode`.

### 4.1 So sánh ba mode

| | `naive` | `light` | `mini` |
|---|---|---|---|
| Function | `operate.py:1076 naive_query` | `operate.py:918 hybrid_query` | `operate.py:1409 minirag_query` |
| Query preprocess | ❌ không | ✅ `keywords_extraction` → hl/ll keywords | ✅ `minirag_query2kwd` → answer_type + entities |
| Số lời gọi LLM | **1** | **2** | **2** |
| VDB dùng | `chunks_vdb` | `entities_vdb`, `relationships_vdb` | `entity_name_vdb`, `relationships_vdb`, `chunks_vdb` |
| Duyệt đồ thị | ❌ | 1-hop qua `get_node_edges` | ✅ **2-hop** `get_neighbors_within_k_hops` |
| `top_k` dùng ở | `:1084` | `:490`, `:762` | `:1271`, `:1322`, `:1375`, `:1378` |
| Token budget | `max_token_for_text_unit` `:1094` | `text_unit` `:634,911` · `global` `:673,787` · `local` `:875` | **chỉ** `max_token_for_node_context` `:1367` |
| Dedup/rank | ❌ | truncate theo token | ✅ `kwd2chunk` cộng điểm |
| Prompt cuối | `naive_rag_response` `:1100` | `rag_response` `:986` | `rag_response` `:1470` |
| `response_type` | `:1102` | `:988` | `:1472` |

> 🔴 **Ở mode `mini`, `max_token_for_text_unit` KHÔNG được dùng ở bất kỳ đâu.** Chỉ
> bảng `Entities` bị cắt (`:1364-1368`, `max_token_for_node_context=500`,
> `base.py:35`). Bảng `Sources` đi thẳng vào prompt **không giới hạn token**.
> → Tham số `--maxtokentextunit` **vô tác dụng** với baseline hiện tại.

> 🔴 **`entities_vdb` được truyền vào `_build_mini_query_context` nhưng không dùng lần
> nào** (đếm: chỉ xuất hiện ở chữ ký hàm). Cùng số phận với tham số `embedder`.
> → VDB 754 vector, 1,6 MB, embed **hai lần** lúc index, **không phục vụ mode mini**.

### 4.2 Sơ đồ mode `mini`

```
Query
 │
 ├─ minirag_query:1423   get_types() → TYPE_POOL (đã .lower())
 ├─ minirag_query:1426   LLM #1 (minirag_query2kwd)
 │                        → type_keywords · entities_from_query[:5]   ← TRẦN 5 CỨNG
 │
 ▼ _build_mini_query_context:1252
 ├─ :1271  entity_name_vdb.query(ent, top_k=60)        [vector lookup]
 ├─ :1288  get_neighbors_within_k_hops(key, 2)         [graph traversal]
 ├─ :1301  giữ 20% node cụt điểm cao nhất
 ├─ :1311  get_node_from_types(type_keywords)          [🔴 luôn trả 0 — §7.1]
 ├─ :1317  cal_path_score_list  (utils.py:404)         [đếm node đích → luôn 0]
 ├─ :1320  relationships_vdb.query(top_k=len(ents)*60) [vector lookup]
 ├─ :1332  edge_vote_path       (utils.py:416)         [đếm phiếu cạnh]
 ├─ :1336  path2chunk(max_chunks=3)                    [candidate collection]
 ├─ :1364  truncate Entities theo max_token_for_node_context=500
 ├─ :1373  scorednode2chunk
 ├─ :1375  chunks_vdb.query(top_k=30)                  [vector lookup]
 └─ :1377  kwd2chunk(chunk_nums=30)                    [×2 và ×10 đóng cứng]
 │
 ▼ context = "-----Entities-----" CSV + "-----Sources-----" CSV
 ├─ :1471  rag_response.format(context_data, response_type)
 └─ :1474  LLM #2 → answer
```

### 4.3 Hằng số đóng cứng trong mode `mini`

| Giá trị | Ý nghĩa | File:line |
|---|---|---|
| `[:5]` | Trần thực thể từ câu hỏi | `operate.py:1431`, `:1445` |
| `2` | Số hop | `operate.py:1290` |
| `0.2` | Tỷ lệ giữ node cụt | `operate.py:1301` |
| `max_chunks=3` | Chunk mỗi thực thể | `operate.py:1341` |
| `* 2` | Hệ số thực thể khớp đầu | `operate.py:1229` |
| `* 10` | Hệ số chunk trùng hai nguồn | `operate.py:1236` |
| `top_k / 2` | Số chunk cuối | `operate.py:1375`, `:1378` |

---

## 5. Storage Map

| Storage | File trên đĩa | Key | Value/schema | Tạo lúc | Query lúc | Mode dùng |
|---|---|---|---|---|---|---|
| `doc_status` | `kv_store_doc_status.json` | `doc-<md5>` | status, content, chunks_count, timestamps | `minirag.py:470`, `:523` | `minirag.py:369`, `:484-486` | — (index) |
| `full_docs` | `kv_store_full_docs.json` | `doc-<md5>` | `{content}` | `minirag.py:520` | *(không đọc lúc query)* | — |
| `text_chunks` | `kv_store_text_chunks.json` | `chunk-<md5>` | content, tokens, chunk_order_index, full_doc_id | `minirag.py:521` | `:1379` (mini), `:1089` (naive) | cả 3 |
| `chunks_vdb` | `vdb_chunks.json` — **503 vector, 384d** | `chunk-<md5>` | vector + content | `minirag.py:519` | `:1375` (mini), `:1084` (naive) | mini, naive |
| `entities_vdb` | `vdb_entities.json` — **754 vector** | `ent-<md5(name)>` | `entity_name`, content = name+description | `operate.py:372` **và `:381`** | `:490` (local), `:762` phụ trợ | **chỉ light** |
| `entity_name_vdb` | `vdb_entities_name.json` — **754 vector** | `Ename-<md5(name)>` | content = **chỉ tên** | `operate.py:391` | `:1271` | **chỉ mini** |
| `relationships_vdb` | `vdb_relationships.json` — **1.779 vector** | `rel-<md5(src+tgt)>` | src_id, tgt_id, content = keywords+src+tgt+desc | `operate.py:406` | `:1320` (mini), `:762` (light) | mini, light |
| `chunk_entity_relation_graph` | `graph_chunk_entity_relation.graphml` — **770 node / 1.779 edge** | tên thực thể | node: entity_type, description, source_id · edge: weight, description, keywords, source_id | `operate.py:158`, `:212` | `:1288`, `:1311`, `:1423` | mini, light |
| `llm_response_cache` | `kv_store_llm_response_cache.json` | — | — | khởi tạo `minirag.py:238` | **không bao giờ** | — |
| *(fork)* `extracted_chunks.json` | — | — | list chunk id đã trích xuất | `minirag.py:408` | `minirag.py:385` | — |

**Xác nhận: có 4 VDB**, đúng như tên gọi trong `minirag.py:274-299`.

> 🔴 **LLM cache không bao giờ được ghi.** `minirag.py:301-307` bọc `llm_model_func`
> với `hashing_kv=self.llm_response_cache`, nhưng **cả hai backend đều vứt nó đi**:
> `openai.py:109` và `gemini.py:270` cùng gọi `kwargs.pop("hashing_kv", None)` mà không
> đọc/ghi cache. Đây là **hành vi upstream**, không phải lỗi của fork — `openai.py`
> không hề bị sửa. File `kv_store_llm_response_cache.json` vì thế **rỗng 2 byte**.

---

## 6. Fork vs Upstream Differences

So sánh `MiniRag-Base` (upstream `e204d23`) ↔ `HEAD`:

```
main.py                    |   2 +-      ← chỉ thụt lề comment, KHÔNG phải thay đổi hành vi
minirag/llm/__init__.py    |  31 ++-     ← import chịu lỗi + export gemini
minirag/llm/gemini.py      | 408 ++++    ← MỚI: backend Gemini + key pool
minirag/minirag.py         |  24 ++-     ← BẢN VÁ O(N²)
reproduce/*                |  ~1100 ++   ← pipeline đo, không ảnh hưởng thư viện
```

> ✅ **`operate.py`, `prompt.py`, `base.py`, `utils.py`, `kg/*` — KHÔNG SỬA MỘT DÒNG NÀO.**
> (`git diff MiniRag-Base..HEAD -- minirag/operate.py` trả về rỗng.)
> Nghĩa là **mọi phát hiện ở §7–§9 đều là hành vi upstream**, không phải do fork gây ra.

### 6.1 Bản vá O(N²) — `minirag.py:379-409`

**Upstream làm gì:** `ainsert` dựng `inserting_chunks` từ
`doc_status.get_docs_by_status(DocStatus.PROCESSED)` — tức **toàn bộ** document đã xử lý
từ trước tới nay (`minirag.py:363-377`) — rồi truyền thẳng vào `extract_entities`.

**Fork làm gì:** thêm 23 dòng lưu tập chunk id đã trích xuất vào
`extracted_chunks.json`, lọc bỏ trước khi gọi `extract_entities`.

**Khác biệt hành vi:**

| | Upstream | Fork |
|---|---|---|
| Chèn 442 doc lần lượt | trích xuất lại corpus 442 lần → ~68.000 lời gọi | **653** lời gọi |
| Mỗi chunk được trích xuất | nhiều lần, mỗi lần LLM trả kết quả hơi khác | **đúng 1 lần** |

**Ảnh hưởng tới graph:** vì `_merge_nodes_then_upsert` gộp `description` bằng
`sorted(set(...))`, việc trích xuất lặp của upstream **vô tình gom thêm entity và mô tả**
qua các lần chạy khác nhau. Đồ thị của fork **thưa hơn upstream** — đây là đánh đổi có ý
thức, phải ghi vào Limitations.

**Ảnh hưởng tới reproducibility:** fork **tốt hơn**. Upstream cho kết quả phụ thuộc
**thứ tự và số lần** chèn document; fork thì không.

---

## 7. Graph Construction Risks

### 7.1 🔴 `get_node_from_types` không bao giờ khớp

| Nơi | Giá trị |
|---|---|
| Lưu trong graph | `'"EVENT"'` — HOA (`operate.py:80` `.upper()`) |
| `get_types()` trả `TYPE_POOL` | `['event',…]` — thường (`networkx_impl.py:155` `.lower()`) |
| Prompt đưa LLM | `TYPE_POOL` bản **thường** (`operate.py:1424`) |
| LLM trả về | `['concept','person','event']` — thường |
| `get_node_from_types` so | `data['entity_type'].strip('"')` = `EVENT` **in** `['event',…]` → ❌ |

`get_types()` trả **hai** danh sách; `TYPE_POOL_w_CASE` được gán ở `operate.py:1423`
rồi **không dùng ở đâu** (grep toàn file chỉ ra 2 dòng).

**Hệ quả dây chuyền:** `maybe_answer_list` rỗng → `cal_path_score_list` (`utils.py:411`)
đếm 0 cho **mọi** đường đi → `scorelist[0]` luôn = 0 → điểm đường đi chỉ còn phiếu cạnh.
**Nửa thuật toán chấm điểm của MiniRAG đang không hoạt động.**

### 7.2 🔴 Node rác từ parse

Regex greedy `re.search(r"\((.*)\)", record)` (`operate.py:297`) + delimiter `<|>`
(`prompt.py:2`) sinh ra node còn dính mảnh delimiter:

```
TIRIONFORDRING"|
COMMUNITY GARDEN"|>
WOLFGANGSCHULZ":
REXXARREMARRIER"|"REXXARREMAR
MALFURIONSTORMRAGE"|>"ILLIDANSTORMRAGE AND MALFURIONSTORMRAGE DISCUSS LAYOUT IDEAS…
```

**5 node** chứa ký tự phân cách lỗi. Ngoài ra **8 node có tên dài ≥ 7 từ** — là cả một
câu, không phải thực thể:

```
PEDRI PLAYS AS A MIDFIELDER FOR BARCA, WITH EXPECTATIONS OF BECOMING A GAME-CHANGER…
CHAESONG-HWA PREPARES TO PRACTICE THE SONG 'LET IT BE' AND LOOKS FORWARD TO PERFORMING IT.
```

**Không có bước validation nào** giữa `_handle_single_entity_extraction:77` và
`_merge_nodes_then_upsert:158` — bất cứ chuỗi nào không rỗng đều thành node.

### 7.3 🔴 Không có entity resolution

`operate.py:127` `get_node(entity_name)` — khoá chuỗi chính xác.

| Cùng một thực thể | Các node riêng biệt (degree) |
|---|---|
| Li Hua | `LIHUA` (**300**) · `LI HUA` (20) |
| Adam Smith | `ADAMSMITH` (49) · `ADAM SMITH` (3) · `MR. SMITH` (299)* |
| Chae Song-hwa | `CHAESONG-HWA` (88) · `CHAE SONG-HWA` (2) |
| Wolfgang Schulz | `WOLFGANGSCHULZ` (108) · `WOLFGANGSCHULZ":` (0) |

\* `MR. SMITH` có thể là người khác — cần kiểm chứng thủ công, không tự động gộp được.

**Tổng: 27 nhóm trùng / 57 node** khi chuẩn hoá bằng `lower()` + bỏ ký tự không
alphanumeric.

### 7.4 🔴 Description phình vô hạn

`_handle_entity_relation_summary` (`operate.py:57`) bị comment ở `:150-152` và `:209-211`.

| Chỉ số description node | Giá trị |
|---|---|
| Dài nhất | **89.170 ký tự** |
| Số mảnh `<SEP>` nhiều nhất | **748** |
| p95 | 2.547 ký tự |
| Trung vị | 118 ký tự |
| Số node có > 1 mảnh | 255 |

**Ảnh hưởng lan sang retrieval:** `path2chunk:1164` tách description theo `<SEP>` rồi
`:1173` chạy `calculate_similarity` (Levenshtein, `utils.py:466`) trên toàn bộ danh
sách — với node `LIHUA` là **748 phép so chuỗi cho một node, mỗi query**. Điều kiện
`len(text_units_node) == len(descriptionlist_node)` ở `:1170` cũng dễ sai khi hai danh
sách lệch nhau, khiến nhánh lọc bị bỏ qua hoàn toàn.

### 7.5 Graph fragmentation — số đo

| Chỉ số | Giá trị | Nhận xét |
|---|---|---|
| Thành phần liên thông | **67** | 1 khối lớn 693 node + 59 node cô lập + 7 cụm nhỏ |
| Node cô lập (degree 0) | **59 (7,7%)** | Path discovery **không bao giờ chạm tới** |
| Node degree ≤ 1 | **348 (45%)** | Gần nửa đồ thị gần như không có đường đi |
| Degree cao nhất | **300** (`LIHUA`) | Hình sao, không phải mạng |
| Degree trung bình | 4,62 | |
| Self-loop | 3 | |
| Node không có trong VDB nào | **16** | Node `UNKNOWN` từ `operate.py:206` |

**Phân bố `entity_type`:** `EVENT` 256 · `PERSON` 245 · `ORGANIZATION` 166 ·
`LOCATION` 80 · `UNKNOWN` 16 · `CONCEPT` 4 · `TECHNOLOGY` 3.

> ⚠️ `prompt.py:5` chỉ cho phép 4 loại `["organization","person","location","event"]`,
> nhưng graph có `CONCEPT` và `TECHNOLOGY` → **LLM không tuân thủ ràng buộc prompt và
> không có validation nào chặn lại**.

---

## 8. Retrieval Risks

| # | Rủi ro | Bằng chứng | Hệ quả |
|---|---|---|---|
| R1 | Answer-type scoring chết | §7.1 | Mất nửa cơ chế xếp hạng đường đi |
| R2 | `top_k=60` + ngưỡng cosine 0.2 quá lỏng | `base.py:25`; trace: `LI HUA` khớp `CINQUE TERRE` @ 0,344 | context_precision **0,316** |
| R3 | Bùng nổ đường đi | trace query 1: 138 thực thể → **22.879 đường**, chỉ 971 có phiếu | 96% chấm điểm vô ích |
| R4 | Trần 5 thực thể | `operate.py:1431` | Câu multi-hop bị cắt cụt từ bước ① |
| R5 | Bảng `Sources` không giới hạn token | chỉ `:1364` cắt `Entities` | Context phình, nhiễu |
| R6 | Hệ số ×2 / ×10 không có cơ sở | `operate.py:1229`, `:1236` | Không giải thích được trong báo cáo |
| R7 | Embedding không hiểu thứ tự thời gian | trace: `20260301` khớp mạnh nhất `20260107_15:00` @ 0,679 | Sai câu hỏi trước/sau |
| R8 | Không có lexical/BM25 ở bất kỳ đâu | toàn bộ luồng dùng dense vector | Thực thể hiếm, mã số bị trượt |

---

## 9. Generation / Evaluation Risks

| # | Rủi ro | Bằng chứng | Hệ quả |
|---|---|---|---|
| G1 | Không có cơ chế "không biết" | `rag_response` có câu *"If you don't know the answer, just say so"* nhưng không có ngưỡng tin cậy nào trong code | **Null err 31,67%** |
| G2 | `response_type="Multiple Paragraphs"` | `base.py:22` | Câu trả lời dài dòng, judge dễ chấm lệch |
| G3 | Hậu xử lý khác nhau giữa mode | `naive:1109-1119` và `light:994-1003` có bước strip; **`mini` không có** (`:1474-1479`) | So sánh giữa mode không hoàn toàn công bằng |
| G4 | LLM cache không hoạt động | `gemini.py:270` · `openai.py:109` | Mọi lần chạy lại đều tốn quota đầy đủ |
| G5 | Sàn nhiễu judge sd **1,53** | đo 3 lượt trên dev 200 | Chênh lệch < 3 điểm không kết luận được |

---

## 10. Failure Map

| Stage | Failure mode | Biểu hiện | Bằng chứng | Metric bị ảnh hưởng | Re-index? |
|---|---|---|---|---|---|
| Chunking | Cắt ngang lượt hội thoại | Ngữ cảnh đứt đoạn | `operate.py:36-53` không theo ranh giới câu | recall | ✅ Có |
| Entity extraction | LLM trả sai định dạng | Node rác `WOLFGANGSCHULZ":` | `operate.py:297` regex greedy; 5 node | multi-hop recall | ✅ Có |
| Entity extraction | Tên thực thể là cả câu | 8 node là câu văn | không có validation sau `:77` | precision | ✅ Có |
| Entity extraction | LLM vượt 4 type cho phép | `CONCEPT`, `TECHNOLOGY` | `prompt.py:5` vs phân bố thật | answer-type matching | ✅ Có |
| **Entity merge** | **Không có entity resolution** | `LIHUA`(300) ≠ `LI HUA`(20) | `operate.py:127`; 27 nhóm / 57 node | **multi-hop** | ✅ Có |
| Entity merge | Description phình | 89.170 ký tự / 748 mảnh | `operate.py:150-152` comment out | latency, context noise | ✅ Có |
| Edge merge | Node `UNKNOWN` ngoài VDB | 16 node không tìm thấy được | `operate.py:206` | recall | ✅ Có |
| Graph | Phân mảnh | 67 component, 59 node cô lập | audit | multi-hop recall | ✅ Có |
| Embedding | Lãng phí — upsert 2 lần | Tốn gấp đôi quota entities_vdb | `operate.py:364-381` | *(chỉ chi phí)* | ✅ Có |
| **Retrieval** | **Answer-type pool luôn rỗng** | 0 ứng viên ở 3/3 query | `operate.py:1423-1424` | **multi-hop, acc** | ❌ **Không** |
| Retrieval | `top_k` quá lớn | Chunk nhiễu | `base.py:25`; RAGAS 0,316 | context precision | ❌ Không |
| Retrieval | Trần 5 thực thể | Câu nhiều thực thể bị cắt | `operate.py:1431` | multi-hop | ❌ Không |
| Retrieval | Sources không cắt token | Context phình | thiếu truncate sau `:1379` | context precision | ❌ Không |
| Retrieval | Không có lexical | Trượt thực thể hiếm, ngày tháng | toàn luồng dense | recall | ❌ Không |
| Generation | Không có ngưỡng "không biết" | Bịa khi thiếu dữ liệu | Null err 31,67% | **err** | ❌ Không |
| Generation | Response dài | Judge chấm lệch | `base.py:22` | acc | ❌ Không |
| Evaluation | Sàn nhiễu 1,53 | Cải tiến nhỏ không đo được | 3 lượt judge | mọi metric | ❌ Không |

---

## 11. Improvement Hypotheses

### H1 — Kích hoạt lại answer-type matching

**Problem:** `get_node_from_types` không bao giờ khớp, làm chết nửa cơ chế chấm điểm
đường đi của MiniRAG.

**Evidence from code:** `operate.py:1423` gán `TYPE_POOL_w_CASE` rồi không dùng;
`:1424` đưa bản `.lower()` vào prompt; `networkx_impl.py:163` so khớp phân biệt
hoa/thường với `entity_type` được `.upper()` ở `operate.py:80`. Query Trace: **0 ứng
viên ở cả 3 query**.

**Expected mechanism:** `maybe_answer_list` có nội dung → `cal_path_score_list`
(`utils.py:411`) bắt đầu trả điểm khác 0 → đường đi dẫn tới node đúng loại đáp án được
xếp trên → `path2chunk` lấy chunk đúng hơn.

**Expected metric impact:** Multi-hop acc (hiện 42,86%) và overall acc. Không đoán con
số — đây chính là thứ cần đo.

**Requires re-index:** ❌ **Không.** Chỉ đổi cách so khớp lúc query.

**Cost:** Low — 1 lời gọi query lại trên dev 200 (~200 lời gọi LLM).

**How to validate:** Chạy dev set 200 trước/sau, judge 3 lượt. Ngưỡng kết luận **3
điểm** (sàn nhiễu 1,53). Kèm assert: `len(node_datas_from_type) > 0`.

**Priority:** **P0**

---

### H2 — Chuẩn hoá thực thể lúc merge (entity resolution)

**Problem:** Cùng một người bị chẻ thành 2–3 node, mỗi node giữ một phần chunk. Đường
đi multi-hop đứt ngay tại chỗ chẻ.

**Evidence from code:** `operate.py:127` gộp bằng chuỗi chính xác; `clean_str`
(`utils.py:174`) không chuẩn hoá khoảng trắng/dấu câu. Audit: **27 nhóm / 57 node**;
`LIHUA` degree 300 vs `LI HUA` degree 20.

**Expected mechanism:** Thêm khoá chuẩn hoá (`lower()` + bỏ ký tự không alphanumeric)
trước khi `get_node`. Node gộp lại → degree tăng → `get_neighbors_within_k_hops` tìm
được đường mà trước đây đứt.

**Expected metric impact:** Multi-hop recall. Đây là ý tưởng **mượn từ GraphRAG**
(entity resolution) — mượn đúng một cơ chế, **không** thay kiến trúc.

**Requires re-index:** ✅ **Có** — thay đổi cách dựng graph.

**Cost:** Medium — 1 lần index lại (~653 lời gọi, ~1,5 giờ) + đo lại.

**How to validate:** So audit trước/sau: số component, số node cô lập, số nhóm trùng.
Rồi mới đo acc. **Phải đóng băng thành `baseline_v2.yaml` riêng**, không ghi đè baseline
hiện tại.

**Priority:** **P1**

---

### H3 — Giới hạn token cho bảng Sources + hạ `top_k`

**Problem:** RAGAS đo `context_precision = 0,316` — 2/3 chunk đưa vào prompt là rác.

**Evidence from code:** Chỉ bảng `Entities` bị cắt (`operate.py:1364-1368`, 500 token).
Bảng `Sources` (`:1379-1390`) **không qua `truncate_list_by_token_size`**.
`max_token_for_text_unit` **không được dùng ở mode mini** (xem §4.1). `top_k=60` với
ngưỡng cosine 0,2 (`base.py:25`).

**Expected mechanism:** Bớt chunk nhiễu → LLM ít bị dẫn lạc → giảm err, đặc biệt nhóm
Null (hiện 31,67%).

**Expected metric impact:** context_precision ↑, err ↓. Acc có thể **giảm** nếu cắt quá
tay — đây là đánh đổi cần quét.

**Requires re-index:** ❌ **Không.**

**Cost:** Low — quét `top_k` ∈ {10, 20, 40, 60} trên dev 200.

**How to validate:** Quét `top_k`, đo cả acc/err **và** RAGAS context_precision. Ghi
nhận cả trường hợp acc giảm — đó là negative finding hợp lệ.

**Priority:** **P1**

---

### H4 — Lexical retrieval (BM25) song song dense

**Problem:** Không có lexical matching ở bất kỳ đâu. Thực thể hiếm, mã ngày tháng bị
trượt.

**Evidence from code:** Toàn bộ `_build_mini_query_context` chỉ dùng vector query
(`:1271`, `:1320`, `:1375`). Trace: `20260301` khớp mạnh nhất với `"20260107_15:00"`
(0,679) — **embedding không phân biệt được ngày**.

**Expected mechanism:** BM25 trên tên thực thể + nội dung chunk, hợp nhất với dense.

**Expected metric impact:** Câu hỏi có mã ngày/tên riêng — nhóm Single và Multi có mốc
thời gian.

**Requires re-index:** ❌ **Không** (BM25 dựng từ `text_chunks` đã có).

**Cost:** Medium — code mới, nhưng không tốn quota LLM.

**How to validate:** Tách riêng tập câu hỏi **có chứa mã ngày** (regex trên `Evidence`),
đo riêng nhóm đó trước/sau.

**Priority:** **P2** — sau khi H1 và H3 cho thấy trần thật của hệ thống hiện tại.

---

### H5 — Bật lại tóm tắt description

**Problem:** Description 89.170 ký tự / 748 mảnh làm `path2chunk` chạy Levenshtein trên
748 chuỗi mỗi node mỗi query.

**Evidence from code:** `operate.py:150-152` và `:209-211` comment out
`_handle_entity_relation_summary`. `entity_summary_to_max_tokens=500` (`minirag.py:145`)
được khai báo nhưng vô dụng.

**Expected mechanism:** Description ngắn lại → `path2chunk:1173` nhanh hơn, nhánh lọc
`:1170` hoạt động đúng → `entities_vdb` embed nội dung sạch hơn.

**Expected metric impact:** Chủ yếu **latency**. Acc có thể tăng nhẹ. ⚠️ Rủi ro: tóm tắt
làm **mất thông tin**, có thể giảm recall.

**Requires re-index:** ✅ **Có**, và **tốn thêm LLM** (mỗi node dài = 1 lời gọi).

**Cost:** High.

**Priority:** **P2** — chỉ làm nếu latency thành vấn đề, hoặc gộp chung lần index của H2.

---

### H6 — Dọn node rác lúc extraction

**Problem:** 5 node dính delimiter, 8 node là cả câu, 16 node `UNKNOWN` ngoài VDB.

**Evidence from code:** `operate.py:297` regex greedy; không có validation giữa `:77` và
`:158`; `:206` tạo node `UNKNOWN` không qua bước 8.

**Expected mechanism:** Thêm validation (độ dài tên, ký tự cấm) sau `:77`; đưa node
`UNKNOWN` vào `entity_name_vdb`.

**Expected metric impact:** Nhỏ (13/770 node ≈ 1,7%), nhưng **rẻ** và làm graph sạch để
đo các giả thuyết khác chính xác hơn.

**Requires re-index:** ✅ **Có** — gộp chung lần index của H2.

**Cost:** Low nếu đi cùng H2.

**Priority:** **P2**

---

### Không đề xuất: thay MiniRAG bằng GraphRAG

Bằng chứng hiện tại **không** cho thấy graph cần cấu trúc community. Nó cho thấy graph
đang **dựng sai ở khâu cơ bản** (không resolution, không validation, không tóm tắt).
Sửa nền trước. Ý tưởng duy nhất mượn từ GraphRAG lúc này là **entity resolution** (H2).

Nếu sau H1 + H2 mà multi-hop vẫn kém, lúc đó community-based retrieval mới là hướng có
cơ sở — và phải là **thêm vào MiniRAG**, không phải thay thế.

---

## 12. Recommended Experiment Order

| Thứ tự | Giả thuyết | Re-index | Chi phí | Lý do xếp trước |
|---|---|---|---|---|
| 1 | **H1** answer-type matching | ❌ | Low | Sửa nhỏ nhất, ảnh hưởng lớn nhất, không phá baseline |
| 2 | **H3** top_k + giới hạn Sources | ❌ | Low | Chung index với H1, quét được ngay |
| 3 | *(chốt)* Đóng băng `baseline_v2.yaml` | — | — | H1+H3 đổi hành vi query → cần mốc mới |
| 4 | **H2** entity resolution *(+H6 chung một lần index)* | ✅ | Medium | Chỉ index lại **một lần** cho cả hai |
| 5 | **H4** BM25 | ❌ | Medium | Cần biết trần của graph đã sạch trước |
| 6 | **H5** tóm tắt description | ✅ | High | Chỉ khi latency thành vấn đề |

**Ba nguyên tắc bắt buộc:**

1. **Mỗi lần một biến.** H1 và H3 tuy cùng không cần index lại nhưng phải đo **tách
   riêng** — gộp lại thì không biết cái nào tạo ra hiệu quả.
2. **Ngưỡng kết luận 3 điểm.** Sàn nhiễu judge sd = 1,53. Chênh lệch dưới ~3 điểm phải
   rerun nhiều lượt mới dám khẳng định.
3. **Đừng ghi đè index baseline.** Mọi thí nghiệm cần index lại phải dùng
   `--workingdir` mới. `./LiHua-World-gemini` là mốc so sánh, giữ nguyên.

---

## Phụ lục — Lệnh tái tạo audit

```bash
.venv/bin/python -c "import networkx as nx; g=nx.read_graphml('LiHua-World-gemini/graph_chunk_entity_relation.graphml'); print(g.number_of_nodes(), g.number_of_edges(), nx.number_connected_components(g))"
```

Toàn bộ số liệu trong tài liệu này lấy từ `graph_chunk_entity_relation.graphml` và 4
file `vdb_*.json` trong `./LiHua-World-gemini`, **không chạy LLM, không tốn quota**.
