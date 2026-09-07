# Retrieval Code Map — File → Function → Input → Output → Chức năng

> Đường đi của một câu hỏi qua `mode="mini"`, ánh xạ sang code thật.
> Số dòng theo commit `dbfa0d1`. Xem luồng khái niệm ở
> [`RETRIEVAL_FLOW.md`](RETRIEVAL_FLOW.md).

**Điểm vào:** `minirag/minirag.py` → `aquery()` → `minirag_query()`

---

## Bảng tổng — 7 bước

| # | Bước | File | Function |
|---|---|---|---|
| 0 | Điểm vào | `minirag/operate.py:1409` | `minirag_query` |
| ① | Query Semantic Mapping | `minirag/operate.py:1422-1431` | `minirag_query` *(gọi LLM)* |
| ② | Entity Matching | `minirag/operate.py:1271` | `entity_name_vdb.query` |
| ③ | Starting Entities | `minirag/operate.py:1288-1310` | `get_neighbors_within_k_hops` |
| ④ | Candidate Answer Entities | `minirag/operate.py:1311` | `get_node_from_types` |
| ⑤ | Reasoning Path | `minirag/utils.py:404` · `:416` | `cal_path_score_list` · `edge_vote_path` |
| ⑥ | Topology-Enhanced Retrieval | `minirag/operate.py:1124` | `path2chunk` |
| ⑦ | Chunk Retrieval | `minirag/operate.py:1212` · `:1220` | `scorednode2chunk` · `kwd2chunk` |

---

## ① Query Semantic Mapping

| | |
|---|---|
| **File** | `minirag/operate.py:1409-1447` |
| **Function** | `minirag_query()` |
| **Input** | `query: str` · `PROMPTS["minirag_query2kwd"]` · `TYPE_POOL` (mọi `entity_type` trong đồ thị, lấy từ `NetworkXStorage.get_types()` — `minirag/kg/networkx_impl.py:149`) |
| **Output** | `type_keywords: list[str]` · `entities_from_query: list[str]` **(cắt còn 5)** |
| **Chức năng** | Lời gọi LLM **thứ nhất**. Biến câu hỏi tự nhiên thành hai danh sách: đáp án thuộc loại gì, và câu hỏi nhắc tới thực thể nào. Parse JSON bằng `json_repair`; hỏng thì thử vá lần hai, vẫn hỏng thì trả `PROMPTS["fail_response"]`. |

> ⚠️ `entities_from_query = keywords_data.get("entities_from_query", [])[:5]` — **trần
> 5 thực thể đóng cứng**, xuất hiện ở cả hai nhánh parse.

---

## ② Entity Matching

| | |
|---|---|
| **File** | `minirag/operate.py:1268-1275` (trong `_build_mini_query_context`, bắt đầu ở `:1252`) |
| **Function** | `entity_name_vdb.query(ent, top_k=query_param.top_k)` |
| **Input** | Từng `ent` trong `entities_from_query` · `top_k` (mặc định **60**) |
| **Output** | `nodes_from_query_list: list[list[dict]]` — mỗi dict có `entity_name` và `distance` · `ent_from_query_dict: {ent: [entity_name...]}` |
| **Chức năng** | Nối thực thể trong câu hỏi với node thật trong đồ thị bằng tìm kiếm vector. Kho `entity_name_vdb` **chỉ chứa tên thực thể**, không chứa mô tả. |

> ⚠️ Không có so khớp chuỗi/lexical nào ở đây. Tên riêng lạ hoặc mã số mà embedding
> không nắm được thì trượt hoàn toàn.

---

## ③ Starting Entities

| | |
|---|---|
| **File** | `minirag/operate.py:1277-1310` |
| **Function** | `NetworkXStorage.get_neighbors_within_k_hops()` — `minirag/kg/networkx_impl.py:177` |
| **Input** | `candidate_reasoning_path: {entity_name: {"Score": distance, "Path": []}}` · `k=2` (đóng cứng ở `:1290`) |
| **Output** | `candidate_reasoning_path` với `Path` = danh sách tuple đường đi 2-hop · `imp_ents: list[str]` |
| **Chức năng** | Mở rộng mỗi node khởi đầu ra 2 hop. Node không có đường đi nào bị coi là cụt; sắp xếp theo `Score` rồi **chỉ giữ 20%** (`save_p = max(1, int(len(...) * 0.2))`, dòng `:1301`). Node có đường đi giữ hết. |

---

## ④ Candidate Answer Entities

| | |
|---|---|
| **File** | `minirag/operate.py:1311-1313` |
| **Function** | `NetworkXStorage.get_node_from_types()` — `minirag/kg/networkx_impl.py:160` |
| **Input** | `type_keywords` từ bước ① |
| **Output** | `node_datas_from_type: list[dict]` → `maybe_answer_list: list[str]` |
| **Chức năng** | Duyệt **toàn bộ node** trong đồ thị, giữ node có `entity_type` khớp. Đây là tập "đáp án có thể", dùng làm thước đo chấm điểm đường đi ở ⑤. |

> 🔴 **BUG ĐÃ XÁC NHẬN — bước này luôn trả về danh sách rỗng.**
> Đồ thị lưu `entity_type` là `'"EVENT"'` (HOA). `get_types()` `.lower()` nó thành
> `event` trước khi đưa vào prompt (`networkx_impl.py:155`), nên LLM trả về chữ
> thường. Nhưng `get_node_from_types` so sánh `data['entity_type'].strip('"')` —
> tức `EVENT` HOA — với danh sách chữ thường → **không bao giờ khớp**.
> `get_types()` có trả sẵn `TYPE_POOL_w_CASE` nhưng `operate.py:1423` gán rồi
> **không dùng**. Xem [`QUERY_TRACE.md`](QUERY_TRACE.md) để thấy cả 3 query đều ra 0.
>
> ⚠️ Quét tuyến tính `self._graph.nodes(data=True)`, **không có index theo type**.

---

## ⑤ Reasoning Path

Hai lượt chấm điểm cộng dồn.

### ⑤a `cal_path_score_list`

| | |
|---|---|
| **File** | `minirag/utils.py:404-413` |
| **Input** | `candidate_reasoning_path` (③) · `maybe_answer_list` (④) |
| **Output** | `{entity: {"Score": float, "Path": {tuple_đường: [số_node_đích]}}}` |
| **Chức năng** | Với mỗi đường đi, **đếm** số node thuộc tập đáp án nằm trên đó, qua `count_elements_in_tuple` (`utils.py:389`). |

### ⑤b `edge_vote_path`

| | |
|---|---|
| **File** | `minirag/utils.py:416-437` |
| **Input** | `scored_reasoning_path` (⑤a) · `goodedge` — lọc từ `relationships_vdb.query(originalquery, top_k=len(ent_from_query) * top_k)` (`operate.py:1320-1329`), chỉ giữ cạnh có `src_id` hoặc `tgt_id` nằm trong `imp_ents` |
| **Output** | `scored_edged_reasoning_path` (mỗi đường giờ có `[đếm_node, đếm_cạnh]`) · `pairs_append: {tuple_đường: [cạnh...]}` |
| **Chức năng** | Tìm kiếm vector trên quan hệ bằng **câu hỏi gốc**, rồi bỏ phiếu: đường đi nào chứa cạnh vừa tìm được (`is_continuous_subsequence`, `utils.py:341`) thì cộng phiếu. |

> ⚠️ Cả hai lượt đều là **phép đếm**, không đo tương đồng ngữ nghĩa. Đường đi qua 3
> node đúng loại nhưng lạc đề vẫn thắng đường đi qua 1 node đúng chính xác.

---

## ⑥ Topology-Enhanced Retrieval

| | |
|---|---|
| **File** | `minirag/operate.py:1124-1209` |
| **Function** | `path2chunk()` |
| **Input** | `scored_edged_reasoning_path` · `pairs_append` · `query` · `max_chunks=3` (truyền ở `:1341`) |
| **Output** | `scored_edged_reasoning_path` với `v["Path"]` **thay bằng danh sách chunk ID** |
| **Chức năng** | Đi ngược từ đồ thị về văn bản. Mỗi node/cạnh có `source_id` trỏ chunk gốc; gom lại, nhân trọng số `total_score = scorelist[0] + scorelist[1] + 1` (`:1186`), giữ `most_common(3)`. Node không có đường đi nào thì lấy thẳng chunk của chính nó (`:1194-1203`). |

Chỗ duy nhất trong toàn luồng có gì đó **hơi giống lexical**: khi một node có > 5 mô
tả, `calculate_similarity(descriptionlist_node, query, k=max_ids)` dùng
**Levenshtein** (`utils.py:466`) chọn ra khoảng một nửa mô tả gần câu hỏi nhất
(`:1170-1179`).

---

## ⑦ Chunk Retrieval

### ⑦a `scorednode2chunk`

| | |
|---|---|
| **File** | `minirag/operate.py:1212-1217` |
| **Input** | `ent_from_query_dict` (②) · `scored_edged_reasoning_path` (⑥) |
| **Output** | `ent_from_query_dict` **sửa tại chỗ**: `{ent: [{"Score":…, "Path":[chunk_id…]}, …]}` |
| **Chức năng** | Nối ngược thực thể trong câu hỏi với các chunk mà đường đi của nó dẫn tới. |

### ⑦b `kwd2chunk`

| | |
|---|---|
| **File** | `minirag/operate.py:1220-1249` |
| **Input** | `ent_from_query_dict` (⑦a) · `chunks_ids` từ `chunks_vdb.query(originalquery, top_k=int(top_k/2))` (`:1375`) · `chunk_nums=int(top_k/2)` |
| **Output** | `final_chunk_id: list[str]` |
| **Chức năng** | Trộn hai nguồn — chunk từ đồ thị và chunk từ tìm kiếm vector trực tiếp — rồi cộng điểm chọn ra chunk cuối cùng. |

Hai hệ số **đóng cứng**:

| Dòng | Quy tắc | Ý nghĩa |
|---|---|---|
| `:1229` | `score = d["Score"] * 2` | Thực thể khớp **đầu tiên** được ưu tiên gấp đôi |
| `:1236` | `score = score * 10` | Chunk đứng **đầu đường đi** *và* cũng có trong kết quả vector → ×10 |

---

## Đóng gói context và sinh câu trả lời

| | |
|---|---|
| **File** | `minirag/operate.py:1379-1400` |
| **Input** | `final_chunk_id` → `text_chunks_db.get_by_id()` · `entites_section_list` |
| **Output** | Chuỗi context: `-----Entities-----` (CSV) + `-----Sources-----` (CSV) |
| **Chức năng** | Bảng `Entities` **bị cắt theo token** (`truncate_list_by_token_size`, `max_token_for_node_context`, `:1364`). Bảng `Sources` **KHÔNG bị cắt**. Context ghép xong đi vào lời gọi LLM **thứ hai** để sinh câu trả lời. |

---

## Bảng tham số: chỉnh được vs đóng cứng

| Tham số | Giá trị mặc định | Chỉnh qua |
|---|---|---|
| `top_k` | 60 | `QueryParam(top_k=…)` hoặc env `TOP_K` |
| `max_token_for_text_unit` | 4000 | `QueryParam` |
| `max_token_for_global_context` | 4000 | `QueryParam` |
| `max_token_for_local_context` | 4000 | `QueryParam` |
| `response_type` | `"Multiple Paragraphs"` | `QueryParam` |
| `cosine_better_than_threshold` | 0.2 | cấu hình storage |
| **Trần thực thể từ câu hỏi** | **5** | ❌ đóng cứng `operate.py:1431` |
| **Số hop** | **2** | ❌ đóng cứng `operate.py:1290` |
| **Tỷ lệ giữ node cụt** | **20%** | ❌ đóng cứng `operate.py:1301` |
| **`max_chunks` mỗi node** | **3** | ❌ đóng cứng `operate.py:1341` |
| **Hệ số thực thể đầu** | **×2** | ❌ đóng cứng `operate.py:1229` |
| **Hệ số chunk trùng nguồn** | **×10** | ❌ đóng cứng `operate.py:1236` |

Sáu dòng cuối là **điểm can thiệp rẻ nhất** cho Phase 2: đổi được ngay, không cần
index lại.
