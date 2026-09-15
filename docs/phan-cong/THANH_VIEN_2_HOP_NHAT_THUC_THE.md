# Thành viên 2 — Hợp nhất thực thể trùng tên trong đồ thị

> Giao 15/09/2026 · mã cũ: **G2 + G6** ([`../phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](../phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md)),
> cụm B ([`../archive/KE_HOACH_TRIEN_KHAI.md`](../archive/KE_HOACH_TRIEN_KHAI.md)), task **15c** trong [`ROADMAP.md`](../../ROADMAP.md) ·
> loại: **Designed Mechanism hợp lệ** ([`CLAUDE.md`](../../CLAUDE.md) §1b).
> Chạy song song được với sàng lọc BM25 (Hùng) và việc của thành viên 1 — **đọc mục 8 trước khi viết code**.

## 1. Việc cần làm

Gộp các node chỉ khác nhau ở cách viết tên (`LIHUA` / `LI HUA`) **trên chính đồ thị Qwen đã commit**, ghi ra một index mới, rồi
đo xem xếp hạng đồ thị có giữ được nhiều chunk đáp án hơn không. Không index lại; phần gộp không cần GPU.

## 2. Observed Problem — đo 15/09 trên `LiHua-World-qwen-modal`

Tái tạo: `.venv/bin/python reproduce/entity_resolution/graph_stats.py` → `logs/entity_resolution/graph_stats_qwen_modal.txt`.

| Quan sát | Số |
|---|---|
| Kích thước | 1.556 node · 1.509 cạnh |
| Thành phần liên thông | **746**; thành phần lớn nhất 771 node |
| Node cô lập (bậc 0) — không đường đi nào chạm tới | **717** (46%) |
| Nhóm trùng tên sau chuẩn hoá | **21 nhóm, 42 node** |
| Nhân vật chính bị chẻ đôi (bậc) | `LIHUA` 331 · `LI HUA` 62 — `WOLFGANGSCHULZ` 122 · `WOLFGANG SCHULZ` 8 — `CHAESONG-HWA` 71 · `CHAE SONG-HWA` 4 — `YURIKOYAMAMOTO` 63 · `YURIKO YAMAMOTO` 10 — `ADAMSMITH` 46 · `ADAM SMITH` 1 |
| Tên rác (không có chữ hay số) | 5 — toàn emoji |
| Giá trị `entity_type` khác nhau | **47**, trong khi prompt khai báo 4 (organization, person, location, event); 124 node `UNKNOWN` |
| Độ dài mô tả node | trung vị 110 · dài nhất **50.846** ký tự |

**Trong code** (`minirag/operate.py`):
- Tên chỉ được `.upper()` rồi `clean_str` (`:82`; đầu mút cạnh `:103–104`). Khoảng trắng hay gạch nối khác nhau là thành node khác.
- `_merge_nodes_then_upsert` (`:122`) gộp theo tên đúng từng ký tự (`get_node(entity_name)`, `:132`).
- Bước tóm tắt mô tả `_handle_entity_relation_summary` đã bị comment (`:155`, `:214`), nên mô tả phình không giới hạn.
- Regex tham lam `re.search(r"\((.*)\)", record)` (`:302`).

## 3. Giả thuyết

Nhân vật bị chẻ đôi làm đứt đường đi 2 hop và chia phiếu giữa hai node. Gộp các node cùng khoá chuẩn hoá thì:
- Chỉ số cấu trúc **chắc chắn** đẹp lên — đó là toán học, không phải kết quả.
- **Câu hỏi thật:** xếp hạng đồ thị có giữ nhiều chunk đáp án hơn không, nhất là câu Multi? Nếu có, đồ thị có bắt đầu đóng góp
  khi trộn với vector không? (Hiện vector thuần ngang V3 — Limitations 10 trong ROADMAP.)

## 4. Vì sao gộp trên đồ thị đã có, không index lại

Trích xuất bằng LLM là ngẫu nhiên: index lại, kể cả không đổi gì, cũng ra đồ thị khác. So "index mới có gộp" với index cũ sẽ lẫn
tác động của việc gộp với nhiễu trích xuất. Gộp trên chính đồ thị đã commit giữ nguyên mọi thứ khác, nên thí nghiệm **đổi đúng
một biến**. Cách làm lúc index (sửa `_merge_nodes_then_upsert`) để sau, khi đã biết gộp có ích.

## 5. Cơ chế vòng 1 — E1: gộp theo khoá chuẩn hoá trùng khớp tuyệt đối

Viết `reproduce/entity_resolution/merge_entities.py`:

1. Copy `LiHua-World-qwen-modal/` sang `LiHua-World-qwen-entres/`. **Chỉ ghi vào bản copy.**
2. Khoá so trùng = `norm_key()` trong `graph_stats.py` (bỏ ngoặc kép bao ngoài, casefold, bỏ ký tự không phải chữ hay số). Chỉ gộp
   khi khoá **trùng tuyệt đối** — không gộp mờ. In danh sách 21 nhóm, rà tay, **commit danh sách trước khi gộp**.
3. Tên giữ lại: tên có bậc cao nhất trong nhóm, dùng đúng id node như trong graphml (kể cả dấu ngoặc kép).
4. **Node:** nối `description` và `source_id` bằng `GRAPH_FIELD_SEP` như `_merge_nodes_then_upsert`; `entity_type` lấy loại xuất hiện
   nhiều nhất trong nhóm.
5. **Cạnh:** đổi đầu mút sang tên giữ lại. Cạnh trùng cặp thì gộp như `_merge_edges_then_upsert` (`:171`): cộng `weight`, nối
   `description`, `keywords`, `source_id`. Bỏ cạnh tự vòng sinh ra do gộp, ghi lại số lượng.
6. **VDB** — tạo lại đúng định dạng của khối cuối `extract_entities` (`operate.py`, khoảng dòng 370–412):

   | Kho | id | content |
   |---|---|---|
   | `vdb_entities_name` | `compute_mdhash_id(tên, prefix="Ename-")` | `tên` |
   | `vdb_entities` | `compute_mdhash_id(tên, prefix="ent-")` | `tên + " " + description` (upstream ghi hai lần cùng id, bản sau thắng) |
   | `vdb_relationships` | `compute_mdhash_id(src + tgt, prefix="rel-")` | `keywords + " " + src + " " + tgt + " " + description`, kèm trường `src_id`, `tgt_id` |

   Tìm bản ghi cũ theo trường `entity_name`, `src_id`, `tgt_id` trong kho — **đừng tự tính lại id cũ theo thứ tự đầu mút**. Xoá bằng
   `NanoVectorDBStorage.delete(ids)`, rồi upsert bản mới. Dựng storage bằng `build_rag()` trỏ vào thư mục mới để dùng đúng hàm nhúng
   local `all-MiniLM-L6-v2`.
7. Không đụng `kv_store_text_chunks.json`, `vdb_chunks.json`, `kv_store_full_docs.json`: chunk id giữ nguyên, nên nhãn chunk đáp án
   `logs/diag_path2chunk.jsonl` dùng lại được.

**Kiểm toàn vẹn — bắt buộc đạt trước khi đo:**
- `get_types()` (đã sắp xếp) giống hệt index gốc. Nếu khác, prompt parser đổi và mất ghép cặp.
- Mọi node có bản ghi `Ename-` và `ent-`; mọi cạnh có bản ghi `rel-`; không còn bản ghi nào trỏ tới tên đã bị gộp.
- `graph_stats.py` trên index mới báo 0 nhóm trùng.
- Số chunk và danh sách chunk id giống hệt index gốc.

**Không làm ở vòng 1** — mỗi thứ là một biến riêng: bỏ 5 node emoji (G6, để vòng E2); ép `entity_type` về 4 loại (đổi so khớp
answer-type); bật lại tóm tắt mô tả (G5, cần gọi LLM, là đóng góp Efficiency riêng); gộp mờ.

## 6. Đo thế nào — offline, không sinh, không chấm

- **Câu hỏi:** 180 câu dev có evidence; nhãn chỉ dùng để chấm.
- **Hai index:** `LiHua-World-qwen-modal` (gốc) và `LiHua-World-qwen-entres` (đã gộp). **Hai chế độ:** đồ thị thuần và
  `MINIRAG_CHUNK_FUSION=rrf`.
- **Ghép cặp parser:** cache riêng, khởi tạo từ cache sàng lọc. Chạy index gốc trước để điền cache, rồi chạy index mới với
  `MINIRAG_KW_CACHE_ONLY=1`. Báo thiếu cache nghĩa là `TYPE_POOL` đã đổi → dừng, sửa bước 4 của cơ chế.

```bash
mkdir -p logs/entity_resolution/cache
cp logs/screening/cache/kw_cache.jsonl logs/entity_resolution/cache/kw_cache.jsonl
export MINIRAG_KW_CACHE=$PWD/logs/entity_resolution/cache/kw_cache.jsonl
SCREEN_SCRIPT=reproduce/entity_resolution/eval_offline.py reproduce/screening/run_screen.sh
SCREEN_SCRIPT=reproduce/entity_resolution/eval_offline.py MINIRAG_KW_CACHE_ONLY=1 \
  reproduce/screening/run_screen.sh --workingdir ./LiHua-World-qwen-entres
```

  `run_screen.sh` tự nạp endpoint và khoá (cài đặt: [`reproduce/screening/HUONG_DAN_CHAY.md`](../../reproduce/screening/HUONG_DAN_CHAY.md)
  bước 1–2, không cần khoá Gemini). `--workingdir` truyền thêm sẽ đè giá trị mặc định. Số liệu từng câu lấy bằng
  `MINIRAG_CONTEXT_LOG=<file.jsonl>` (`graph_ids`, `chunk_ids`, `graph_seeds`, `graph_paths`, `retrieval_ms`).
- **Dùng lại code:** được `import screen_variant` để lấy `evidence()`, `mcnemar_p()`, `dev_rows()`, `gold_map()`. **Đừng gọi**
  `contexts()`, `run_query()`, `set_env()` của nó — các hàm này ép cache parser trỏ vào `logs/screening/` của Hùng.

| Chỉ số | Cách tính |
|---|---|
| Cấu trúc | `graph_stats.py` trước / sau |
| Chunk đáp án | tỉ lệ nằm trong 30 chunk đồ thị (`graph_ids`); tỉ lệ nằm trong `chunk_ids` sau cắt 4.000 |
| Câu đủ đáp án | ghép cặp từng câu giữa hai index, McNemar |
| Theo loại | tách Single và Multi |
| Khối lượng, thời gian | `graph_seeds`, `graph_paths`, `retrieval_ms` — gộp hub có thể làm tăng số đường; chỉ ghi lại, không tự cắt tỉa (việc của thành viên 1) |

**Gợi ý cổng** — chốt chính thức ở mục 7:
- Kiểm toàn vẹn đạt hết. Trượt thì không đo tiếp.
- Đồ thị thuần: câu đủ đáp án net ≥ +9 **và** p < 0,01 → đủ để xin nhóm chạy QA. Chế độ `rrf`: net ≥ 0.
- Multi báo riêng, không làm cổng (chỉ 21 câu).

**Chạy QA sau đó** cần nhóm duyệt và phối hợp với Hùng: V3 canary đông lạnh gắn với index gốc, nên index mới cần một lượt đông lạnh
V3 riêng (khoảng 120 lượt sinh và 100 lượt chấm).

## 7. Đăng ký trước — điền và commit TRƯỚC khi đo truy hồi

```
Ngày chốt:
Danh sách nhóm gộp đã rà tay (đường dẫn file):
Nhóm bị loại khỏi danh sách và lý do:
Chỉ số chính:
Cổng (số cụ thể):
Dự báo (con số mong đợi, viết trước khi đo):
Trượt cổng thì ghi gì vào ROADMAP:
```

## 8. Ranh giới — để không đụng Hùng và thành viên 1

**Được tạo / sửa**
- `reproduce/entity_resolution/` — đã có `graph_stats.py`; thêm `merge_entities.py`, `eval_offline.py`.
- `logs/entity_resolution/`.
- `LiHua-World-qwen-entres/` — index mới; commit sau khi qua kiểm toàn vẹn (khoảng 20 MB).

**Không được sửa**
- Toàn bộ `minirag/`. Vòng 1 không cần sửa thư viện; nếu thật sự cần, báo Hùng trước.
- `LiHua-World-qwen-modal/` — index chung, chỉ đọc (CLAUDE.md §4).
- `reproduce/screening/`, `logs/screening/` — **Hùng**.
- `minirag/path_rerank.py`, `reproduce/path/`, `logs/path/` — **thành viên 1**.

**Git:** làm trên nhánh `tv2/entity-resolution` tách từ `dev`; mở PR vào `dev` sau khi có báo cáo offline.

## 9. Chi phí, rủi ro, nếu không ăn thua

- **Chi phí:** CPU; nhúng lại vài chục bản ghi bằng model local; khoảng 100 lời gọi parser trên Modal của bạn. Không tốn lượt chấm.
- **Rủi ro:** gộp nhầm hai người khác nhau — vòng 1 chỉ gộp khoá trùng tuyệt đối và rà tay cả 21 nhóm. Gộp hub (`LIHUA` 331 + 62)
  làm bùng số đường và thời gian dựng context. Đổi `TYPE_POOL` làm mất ghép cặp parser.
- **Nếu không ăn thua:** cấu trúc đẹp lên mà truy hồi không đổi là kết quả phủ định hợp lệ — nó cho biết lỗi của đồ thị không
  nằm ở tên trùng. Ghi vào ROADMAP.
