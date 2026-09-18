# E1 — hướng dẫn tái tạo

Toàn bộ vòng E1 chạy offline trên CPU. Không gọi LLM, không sinh, không chấm.

## 0. Thứ tự phụ thuộc

```
merge_entities.py            →  LiHua-World-qwen-entres/        (gộp thực thể)
check_embedding_parity.py    →  cổng parity embedding
reembed_relationships_pair.py→  logs/entity_resolution/pair/{control,entres}/   (hai nhánh)
eval_offline.py              →  logs/entity_resolution/eval/*.jsonl             (raw log)
report_e1.py                 →  báo cáo + audit  (KHÔNG chạy truy hồi)
```

## 1. Gộp thực thể

```bash
.venv/Scripts/python.exe reproduce/entity_resolution/merge_entities.py --dry-run
.venv/Scripts/python.exe reproduce/entity_resolution/merge_entities.py
```

Đọc `LiHua-World-qwen-modal/`, không bao giờ ghi vào đó. Danh sách gộp lấy từ
`merge_review.csv` (18 MERGE, 3 REJECT). Kết quả kèm `logs/entity_resolution/merge_report.json`
và `integrity_report.txt`.

## 2. Cổng parity embedding

```bash
.venv/Scripts/python.exe reproduce/entity_resolution/check_embedding_parity.py
```

Ghi `logs/entity_resolution/embedding_parity.json`. Kết quả đã biết:
`BLOCKER_PADDING_REGIME`. Nhúng lại như hiện tại cho trung vị cosine 0,68 so với vector đã commit;
khi quét độ dài pad thì trung vị đạt 1,000000 (nhỏ nhất 0,979563 trên 30 bản ghi). Đây là **bằng chứng
hỗ trợ mạnh giả thuyết batch-padding dependence** — vector đã commit phụ thuộc chuỗi dài nhất trong lô
lúc index — chứ không phải chứng minh tuyệt đối rằng hàm nhúng, model và `content` đúng trên toàn bộ
kho. Đây là lý do có bước 3.

## 3. Dựng hai nhánh (bắt buộc trước khi đo)

```bash
.venv/Scripts/python.exe reproduce/entity_resolution/reembed_relationships_pair.py --force --verify-deterministic
```

Nhúng lại **toàn bộ** `vdb_relationships` của cả hai nhánh bằng `hf_embed` + `batch = 1`, giữ
nguyên orientation `src_id`/`tgt_id` của bản ghi cũ. Ghi `reembed_pair_report.{json,txt}`.
Hai nhánh tạo ra là:

```
logs/entity_resolution/pair/control/    (chưa gộp)
logs/entity_resolution/pair/entres/     (đã gộp E1)
```

⚠️ Chỉ hai thư mục này được dùng cho kết quả chính. **Không** dùng trực tiếp
`LiHua-World-qwen-modal/` hay `LiHua-World-qwen-entres/` để đo — chúng còn ở chế độ nhúng theo lô
trước amendment 17/09/2026.

## 4. Chạy truy hồi (tốn ~4 giờ CPU)

```bash
cp logs/screening/cache/kw_cache.jsonl logs/entity_resolution/cache/kw_cache.jsonl
.venv/Scripts/python.exe reproduce/entity_resolution/eval_offline.py --resume
```

Sinh bốn raw log trong `logs/entity_resolution/eval/`:
`control_graph.jsonl`, `treatment_graph.jsonl`, `control_rrf.jsonl`, `treatment_rrf.jsonl`.

`--resume` chỉ dùng lại một luồng `(arm, mode)` **đã hoàn tất** đủ 180 dòng đúng bộ câu hỏi.
Không hỗ trợ resume giữa chừng một arm: arm đang dở sẽ chạy lại từ đầu.

**Hai phiên bản runner — đừng nhầm:**

- **Lần chạy của kết quả hiện tại** (khởi chạy 2026-09-17 22:43) dùng runner **v1**. Runner v1
  **không ghi** `run_manifest.json`. Bằng chứng về lần chạy đó lấy từ report do chính runner v1
  ghi ra, stdout của tiến trình, dấu vết filesystem và dữ liệu nguồn — xem mục 5. Mã runner lúc
  khởi chạy được dựng lại và lưu ở
  `logs/entity_resolution/provenance/eval_offline_AT_LAUNCH_reconstructed.py`.
- **Runner v2** (sau khi áp `patch_runner_v2`) ghi `run_manifest.json` schema 2 cho **các lần chạy
  sau**: sha256 cache trước/sau, sha256 raw log, sha256 mã lúc bắt đầu, hash index trước/sau và env
  **theo từng luồng**. Luồng được dùng lại qua `--resume` chỉ ghi số dòng và sha256 raw log, không
  mang env/hash/số lời gọi LLM của invocation mới. Runner v2 không tự tính cổng mà gọi `report_e1`.
  Áp patch v2 **không** bổ sung được manifest cho lần chạy 22:43.

## 5. Tái tạo báo cáo từ raw log (không chạy lại truy hồi)

```bash
# lần đầu sau khi tiến trình truy hồi kết thúc: trỏ tới stdout của tiến trình để bảo toàn
E1_PROCESS_OUTPUT=<đường_dẫn_stdout_của_tiến_trình> .venv/Scripts/python.exe reproduce/entity_resolution/report_e1.py
# các lần sau: không cần biến, bằng chứng đã nằm trong kho lưu trữ
.venv/Scripts/python.exe reproduce/entity_resolution/report_e1.py
```

Thứ tự `report_e1.build_and_write()`:

1. **Bảo toàn** report gốc của runner và stdout vào
   `logs/entity_resolution/provenance/runner_original/`, kèm `PRESERVED.json`. Chỉ chép **một lần**,
   không bao giờ ghi đè. Report JSON chỉ được lưu nếu đúng dấu vân tay runner v1, nên report do chính
   `report_e1` sinh ra không bao giờ lọt vào kho bằng chứng. Hash trong `PRESERVED.json` ghi **lúc bảo
   toàn**, chỉ dùng để phát hiện kho bị sửa về sau — không phải hash trước lần chạy.
2. **Xác minh nguồn** report runner, đọc **từ kho lưu trữ**: đúng cấu trúc và bộ tên check của
   runner v1, hai report cùng bộ check, ghi trong khung 15 phút sau raw log cuối, số liệu tính lại
   khớp bốn raw log, stdout cho thấy cả bốn luồng được **chạy** (không dùng lại) và không có traceback.
3. **Check** ba trạng thái PASS / FAIL / UNVERIFIED, mỗi check ghi nguồn. Ngân sách 4.000 token được
   **tính lại** từ raw log và nội dung chunk; tham số giống nhau giữa hai nhánh được suy ra từ
   `vector_ids` trùng khớp.
4. **Fail-closed:** còn check bắt buộc nào FAIL hoặc UNVERIFIED thì chỉ ghi
   `validity_audit.{json,md}`, cổng `NOT_EVALUATED`, `passed = null`, exit code 2, và **dừng trước**
   khi tính kết quả chính hay per-query.
5. Chỉ khi mọi check bắt buộc PASS mới sinh:

```
logs/entity_resolution/eval_graph_report.json
logs/entity_resolution/eval_rrf_report.json
logs/entity_resolution/eval_summary.md
logs/entity_resolution/per_query_graph.jsonl
logs/entity_resolution/per_query_rrf.jsonl
```

## 6. Kiểm thử (không cần raw log thật)

```bash
.venv/Scripts/python.exe reproduce/entity_resolution/test_report_layer.py
.venv/Scripts/python.exe reproduce/entity_resolution/test_provenance.py
.venv/Scripts/python.exe reproduce/entity_resolution/eval_set.py
```

`test_report_layer.py`: FAIL/UNVERIFIED chặn cổng; cổng RRF đọc `final_chunks`; full-evidence là
tập con thật sự; McNemar khớp exact two-sided binomial tính độc lập.

`test_provenance.py` (thư mục tạm, dữ liệu tổng hợp): manifest thiếu `cache_before/after` không PASS;
report không rõ nguồn không được dùng làm bằng chứng; luồng dùng lại không nhận provenance của
invocation mới; đủ 180 dòng nhưng sai question ID vẫn ra audit và không crash; chạy report-only hai
lần vẫn truy xuất được bằng chứng gốc; kho lưu trữ bị sửa thì bị phát hiện.

## 7. Vì sao cổng RRF đọc `final_chunks`

`minirag/operate.py:1489` chụp `graph_chunk_ids` **trước** nhánh fusion (`:1495-1504`), và RRF chỉ
thay `final_chunk_id`. Nên `graph_ids` giống hệt nhau ở cả hai mode, còn tác động của RRF chỉ hiện
ra ở `chunk_ids` (sau fusion và sau cắt token A1@4000). Cổng graph-only vẫn đọc `graph_top30`.
Ngưỡng đã đăng ký không đổi.
