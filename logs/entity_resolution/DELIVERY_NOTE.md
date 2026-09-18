# E1 — Entity Resolution: bàn giao kết quả offline

**Ngày:** 18/09/2026 · **Nhánh:** `tv2/entity-resolution` · **Người chạy:** thành viên 2

Kết quả chính đo **tác động của E1 dưới cùng một chính sách deterministic relationship embedding ở
cả hai nhánh**. Chưa đo chất lượng câu trả lời cuối cùng. Không chạy sinh, chấm hay QA.

> **Ghi chú khi merge vào `dev` (18/09, Hùng):** hai bản sao index của cặp control/treatment
> (`logs/entity_resolution/pair/control/`, `pair/entres/`) **không đưa vào git** — khoảng 30 MB và dựng lại được từ
> `LiHua-World-qwen-entres/` cùng `reproduce/entity_resolution/`. Đã thêm vào `.gitignore`. Mọi thứ khác giữ nguyên.

---

## 1. Câu hỏi và câu trả lời

**Hỏi:** Gộp thực thể trùng tên có giúp giữ đủ chunk bằng chứng cho nhiều câu hỏi hơn không?

**Đáp: Không.** Trên 180 câu dev có evidence, xếp hạng đồ thị top-30 giữ đủ bằng chứng cho
**103/180 câu ở control và 102/180 ở treatment**, net **−1** (2 câu lên, 3 câu xuống),
McNemar exact **p = 1,0**. Cấu trúc đồ thị đẹp lên đúng như dự đoán, nhưng truy hồi bằng chứng
thì không.

## 2. Cổng đã đăng ký trước

| Cổng | Chỉ số | Ngưỡng | Kết quả | Kết luận |
|---|---|---|---|---|
| Graph-only | `graph.graph_top30.ALL` | net ≥ +9 **và** p < 0,01 | net **−1**, p = 1,0 | **TRƯỢT** |
| RRF | `rrf.final_chunks.ALL` | net ≥ 0 | net **0**, p = 1,0 | ĐẠT ở mức tối thiểu |

Cổng RRF đạt chỉ vì ngưỡng là "không xấu đi". Không có cải thiện nào: 2 câu lên, 2 câu xuống.

## 3. Kết quả đầy đủ

Validity: **VALID**, 68/68 check bắt buộc PASS (`validity_audit.md`).

### mode = graph (`MINIRAG_CHUNK_FUSION=""`)

| Chỉ số | Tập | n | control | treatment | lên | xuống | net | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| graph_top30 | ALL | 180 | 103 (57,2%) | 102 (56,7%) | 2 | 3 | −1 | 1,0 |
| graph_top30 | Single | 159 | 95 (59,7%) | 94 (59,1%) | 1 | 2 | −1 | 1,0 |
| graph_top30 | Multi | 21 | 8 (38,1%) | 8 (38,1%) | 1 | 1 | 0 | 1,0 |
| final_chunks | ALL | 180 | 74 (41,1%) | 77 (42,8%) | 6 | 3 | +3 | 0,51 |
| final_chunks | Single | 159 | 69 (43,4%) | 71 (44,7%) | 5 | 3 | +2 | 0,73 |
| final_chunks | Multi | 21 | 5 (23,8%) | 6 (28,6%) | 1 | 0 | +1 | 1,0 |

### mode = rrf (`MINIRAG_CHUNK_FUSION=rrf`)

| Chỉ số | Tập | n | control | treatment | lên | xuống | net | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| graph_top30 | ALL | 180 | 103 (57,2%) | 102 (56,7%) | 2 | 3 | −1 | 1,0 |
| final_chunks | ALL | 180 | 112 (62,2%) | 112 (62,2%) | 2 | 2 | 0 | 1,0 |
| final_chunks | Single | 159 | 98 (61,6%) | 98 (61,6%) | 1 | 1 | 0 | 1,0 |
| final_chunks | Multi | 21 | 14 (66,7%) | 14 (66,7%) | 1 | 1 | 0 | 1,0 |

`graph_top30` giống hệt nhau ở hai mode vì `graph_ids` được chụp **trước** bước fusion
(`minirag/operate.py:1489`). Đó là lý do cổng RRF phải đọc `final_chunks`.

Multi chỉ mô tả, n = 21, không dùng làm cổng.

## 4. Cấu trúc trước và sau merge

| | Trước (control) | Sau (treatment) |
|---|---:|---:|
| Node | 1.556 | 1.538 |
| Cạnh | 1.509 | 1.463 |
| Thành phần liên thông | 746 | 738 |
| Thành phần lớn nhất | 771 | 761 |
| Node cô lập | 717 | 709 |
| Nhóm trùng tên sau chuẩn hoá | 21 | 3 (đúng 3 nhóm REJECT) |
| Bậc `"LIHUA"` | 331 | 363 |

18 nhóm gộp, 46 cạnh bị gộp trùng, 0 self-loop, 63/63 integrity check PASS.

**Đây chính là điểm mấu chốt:** cấu trúc cải thiện đúng như giả thuyết, nhân vật chính hết bị chẻ
đôi, nhưng số câu giữ đủ bằng chứng không nhúc nhích. Chỉ 5 trong 180 câu đổi kết quả ở graph
top-30, và đổi theo hai chiều gần như cân bằng.

## 5. Workload

| mode | arm | chỉ số | mean | median | p95 | max |
|---|---|---|---:|---:|---:|---:|
| graph | control | graph_paths | 19.632 | 19.995 | 31.566 | 36.741 |
| graph | treatment | graph_paths | 21.910 | 22.307 | 35.154 | 40.612 |
| graph | control | graph_seeds | 96,1 | 96,5 | 149 | 176 |
| graph | treatment | graph_seeds | 95,4 | 96,0 | 148 | 174 |
| graph | control | retrieval_ms | 13.968 | 12.158 | 28.422 | 47.936 |
| graph | treatment | retrieval_ms | 14.343 | 11.722 | 35.848 | 49.604 |
| rrf | control | retrieval_ms | 10.001 | 8.355 | 20.784 | 31.114 |
| rrf | treatment | retrieval_ms | 129.879 | 7.180 | 20.695 | 11.245.501 |

Gộp hub làm **số đường đi tăng khoảng 11,6%** (19.632 → 21.910 trung bình), đúng như rủi ro tài
liệu giao việc đã lường. Số seed không đổi.

**Hai cảnh báo khi đọc cột thời gian:**

1. Hai bản ghi trong `treatment_rrf` (câu #46 và #47) có `retrieval_ms` là 10.706 s và 11.246 s.
   Đó là **máy bị suspend** giữa chừng, không phải chi phí truy hồi. Chúng làm hỏng cột mean và
   max của dòng đó. Loại đúng hai điểm này thì mean là 8.017 ms, median 7.165 ms, max 47.054 ms.
   Không bản ghi nào khác trong bốn lượt có hiện tượng này.
2. Bốn lượt chạy **tuần tự** trong một tiến trình theo thứ tự graph trước, rrf sau. Vì vậy mode
   graph gánh phần khởi động nguội và luôn chậm hơn mode rrf ở cùng một nhánh. **Không dùng các
   con số này để so độ trễ giữa hai nhánh.** Nếu nhóm cần số độ trễ dùng được thì phải đo xen kẽ
   riêng, đúng như cổng thời gian tầng C của quy trình sàng lọc đã làm.

## 6. Hai nhánh thí nghiệm

```
logs/entity_resolution/pair/control/    (chưa gộp)
logs/entity_resolution/pair/entres/     (đã gộp E1)
```

⚠️ Đây là hai nhánh **duy nhất** cho kết quả chính. **Không** dùng `LiHua-World-qwen-modal/` hay
`LiHua-World-qwen-entres/` để đo: chúng còn ở chế độ nhúng theo lô trước amendment 17/09/2026.

Lý do có amendment: `hf_embed` (`minirag/llm/hf.py:177-188`) lấy mean qua **cả vị trí padding** và
bỏ `attention_mask`, nên vector đã commit phụ thuộc chuỗi dài nhất trong lô lúc index. Bản gộp E1
phải nhúng lại 143/1.463 bản ghi quan hệ, tạo ra hai chế độ nhúng lẫn lộn trong cùng một kho, đúng
trên đường `relationships_vdb.query`. Cách xử lý: nhúng lại **toàn bộ** kho quan hệ ở **cả hai**
nhánh bằng cùng `hf_embed` + batch = 1, giữ nguyên orientation `src_id`/`tgt_id`. Kiểm chứng: 1.320
quan hệ chung không bị E1 đụng có cosine tối thiểu 0,9999999999999996 và max_abs_diff **0,0** giữa
hai nhánh; dựng lại lần hai cho vector y hệt.

## 7. Giới hạn

1. **Control không phải index đã commit nguyên bản.** Cả hai nhánh đều đã nhúng lại kho quan hệ.
   Không so trực tiếp được với số V3 hay sàng lọc cũ.
2. **Chưa đo chất lượng câu trả lời.** Đây là phép đo truy hồi offline. Cổng trượt nên không đề
   xuất chạy QA.
3. **Thời gian không dùng để so hai nhánh** (xem mục 5).
4. **`vdb_entities` của nhánh treatment** còn 18 bản ghi nhúng theo lô 18 từ bước gộp. Kho này
   **không** được truy vấn ở chế độ mini (`operate.py` chỉ dùng `entity_name_vdb`, `relationships_vdb`
   và `chunks_vdb`), nên không ảnh hưởng kết quả. Sẽ thành vấn đề nếu sau này ai chạy chế độ light.
5. **Đồ thị Qwen đã commit có tham chiếu chunk chết.** `graph_chunk_entity_relation.graphml` có 18
   tham chiếu `source_id` tới `chunk-c7ec35daa1b937efdeec1effd7d95ede`, một chunk có trong
   `extracted_chunks.json` nhưng không có trong `kv_store_text_chunks.json`. Nó lọt vào `graph_ids`
   qua `kwd2chunk` rồi bị loại ở `operate.py:1518`, nên chiếm một suất trong top-30 ở 13 đến 16 câu
   mỗi lượt mà không bao giờ vào context. Nó **không** phải nhãn gold. Đây là lỗi có sẵn của index,
   không do E1, và ảnh hưởng cả hai nhánh.
6. **Tie-break `entity_type`** khi hoà giữ giá trị của node canonical. Ảnh hưởng đúng 2 nhóm
   (`"HERE COMES THE SUN"`, `"SET LIST"`).
7. **Một lượt sinh duy nhất cho mỗi cấu hình.** Truy hồi là tất định nên không có nhiễu lấy mẫu ở
   đây, nhưng kết luận vẫn chỉ nói về truy hồi.

## 8. Artifacts

| Đường dẫn | Nội dung |
|---|---|
| `reproduce/entity_resolution/merge_entities.py` | gộp thực thể, 6 phase, 63 integrity check |
| `reproduce/entity_resolution/check_embedding_parity.py` | cổng parity embedding |
| `reproduce/entity_resolution/reembed_relationships_pair.py` | dựng hai nhánh, batch = 1 |
| `reproduce/entity_resolution/eval_offline.py` | runner truy hồi offline |
| `reproduce/entity_resolution/report_e1.py` | phân tích, provenance, fail-closed |
| `reproduce/entity_resolution/eval_set.py` | chặn tập đo 180 = 159 + 21 + 0 |
| `reproduce/entity_resolution/test_report_layer.py`, `test_provenance.py` | kiểm thử lớp báo cáo |
| `reproduce/entity_resolution/HUONG_DAN_TAI_TAO.md` | hướng dẫn tái tạo |
| `logs/entity_resolution/eval/*.jsonl` | 4 raw log, mỗi file 180 câu |
| `logs/entity_resolution/eval_{graph,rrf}_report.json` | kết quả ghép cặp |
| `logs/entity_resolution/per_query_{graph,rrf}.jsonl` | kết quả từng câu kèm gold dùng để chấm |
| `logs/entity_resolution/eval_summary.md` | tóm tắt |
| `logs/entity_resolution/validity_audit.{json,md}` | 68 check bắt buộc, kèm nguồn bằng chứng |
| `logs/entity_resolution/merge_report.json`, `integrity_report.txt` | kiểm toàn vẹn merge |
| `logs/entity_resolution/reembed_pair_report.{json,txt}` | dựng hai nhánh, 83 check |
| `logs/entity_resolution/embedding_parity.json` | bằng chứng batch-padding |
| `logs/entity_resolution/graph_stats_*.txt` | cấu trúc trước và sau |
| `logs/entity_resolution/provenance/` | bằng chứng gốc của lần chạy, không ghi đè |
| `LiHua-World-qwen-entres/` | index đã gộp, trước khi nhúng lại |

## 9. Bằng chứng tính hợp lệ

68/68 check bắt buộc PASS, mỗi check ghi nguồn. Những cái đáng kể:

- Bốn lượt **đều được chạy** trong một tiến trình, đúng thứ tự, không lượt nào dùng lại. Bằng
  chứng: stdout gốc và `minirag.log` do chính tiến trình ghi, có dấu thời gian từng truy vấn.
- **Không lời gọi LLM nào.** `llm_model_func` là stub ném `RuntimeError`; runner báo 0 lời gọi.
- **Cache parser** không bị ghi: mtime 22:35:28 nằm trước lúc khởi chạy 22:43:00, nội dung trùng
  khít nguồn `logs/screening/`.
- **Index hai nhánh không đổi**: hash trước/sau do runner đo, cộng mtime mọi file index đều cũ hơn
  mốc đóng băng 22:25:55.
- **Ngân sách 4.000 token** được **tính lại** từ raw log và nội dung chunk cho cả 4 lượt.
- **`vector_ids` trùng khớp** giữa hai nhánh ở cả hai mode, và `graph_ids` bất biến giữa hai mode
  trong cùng một nhánh.
- Report của runner được xác minh nguồn rồi mới dùng: đúng dấu vân tay, đúng khung thời gian, số
  liệu tính lại khớp raw log.

**Ghi nhận trung thực về quá trình:** có xem kết quả smoke test 3 câu trước lần chạy đầy đủ; không
thay đổi danh sách gộp, định nghĩa metric hay ngưỡng nào dựa trên nó. Cổng RRF được sửa ánh xạ từ
`graph_top30` sang `final_chunks` lúc 22:52:08, tức là **sau** khi lần chạy khởi động lúc 22:43:00
và **trước** khi raw log đầu tiên tồn tại lúc 23:25:45. Đó là sửa lỗi ánh xạ sau khi đã khởi chạy
đo, không phải đăng ký trước. Ngưỡng không đổi.

## 10. Đề xuất nội dung cập nhật ROADMAP

> Maintainer chép đoạn này vào ROADMAP. Tôi không sửa file ngoài boundary.

```
### E1 Entity Resolution — kết quả phủ định (18/09/2026)

Gộp 18 nhóm node chỉ khác cách viết tên trên đồ thị Qwen đã commit. Cấu trúc cải thiện đúng
như giả thuyết: 1.556 → 1.538 node, 746 → 738 thành phần liên thông, 717 → 709 node cô lập,
21 → 3 nhóm trùng tên (3 nhóm còn lại là REJECT hợp lệ), bậc "LIHUA" 331 → 363.

Truy hồi bằng chứng KHÔNG cải thiện. Trên 180 câu dev có evidence, đo ghép cặp giữa hai nhánh
đã chuẩn hoá cùng chính sách nhúng quan hệ:
- graph top-30 giữ đủ bằng chứng: 103 → 102 câu, net −1 (2 lên / 3 xuống), McNemar p = 1,0.
  Cổng đăng ký trước là net ≥ +9 và p < 0,01 → TRƯỢT.
- chế độ rrf, chunk cuối: 112 → 112 câu, net 0 → cổng "không xấu đi" đạt ở mức tối thiểu.
- Multi (n = 21): không đổi ở graph top-30.
Gộp hub làm số đường đi tăng khoảng 11,6%.

Kết luận: lỗi của đồ thị KHÔNG nằm ở tên trùng. Chỉ 5/180 câu đổi kết quả và đổi gần như cân
bằng hai chiều. Không chạy QA. Không chuyển sang gộp mờ trong cùng thí nghiệm E1.

Phát hiện phụ (đáng xử lý riêng):
1. hf_embed lấy mean qua cả vị trí padding và bỏ attention_mask, nên mọi vector đã commit phụ
   thuộc thành phần lô lúc index. Mọi thí nghiệm nào nhúng lại một phần kho đều dính confound
   này. Chi tiết: logs/entity_resolution/embedding_parity.json.
2. Đồ thị Qwen có 18 tham chiếu source_id tới một chunk không còn trong kv_store_text_chunks,
   chiếm một suất top-30 ở 13-16 câu mỗi lượt mà không bao giờ vào context.
3. Chỉ 1.425/1.556 node có bản ghi trong vdb_entities: node do _merge_edges_then_upsert tạo ra
   làm đầu mút cạnh không bao giờ được ghi vào VDB.
```

## 11. Bước tiếp theo đề xuất

1. **Không chạy QA.** Cổng graph-only trượt, nên theo đăng ký trước thì dừng ở đây.
2. **Không chuyển sang gộp mờ** trong cùng thí nghiệm E1. Nếu nhóm muốn thử E2 thì phải đăng ký
   trước như một thí nghiệm riêng.
3. Ba phát hiện phụ ở mục 10 đáng mở issue riêng. Phát hiện số 1 ảnh hưởng **mọi** thí nghiệm sau
   này có động vào VDB.
4. Nếu cần số độ trễ dùng được, đo xen kẽ riêng chứ không lấy lại số ở mục 5.
