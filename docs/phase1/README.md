# Phase 1 — Baseline, Retrieval, Query Trace

> Cập nhật 15/09/2026. Mục lục toàn bộ docs: [`../README.md`](../README.md). Kết quả hiện tại:
> [`../KET_QUA_HIEN_TAI.md`](../KET_QUA_HIEN_TAI.md).

Đầu ra của Phase 1. Đây là tài liệu **tham khảo**: phần lớn viết trên index Gemini tại commit `dbfa0d1`, trước khi chuyển sang
Qwen2.5-3B.

| # | Đầu ra | File | Còn dùng được không |
|---|---|---|---|
| 1 | Baseline Config | [`../../baseline.yaml`](../../baseline.yaml) | ✅ mốc đóng băng, không sửa |
| 2 | Baseline Status | [`../archive/BASELINE_STATUS.md`](../archive/BASELINE_STATUS.md) | 🗄️ lưu trữ — thay bằng `KET_QUA_HIEN_TAI.md` |
| 3 | Retrieval Flow | [`RETRIEVAL_FLOW.md`](RETRIEVAL_FLOW.md) | ✅ luồng khái niệm; số dòng đã lệch |
| 4 | Retrieval Code Map | [`RETRIEVAL_CODE_MAP.md`](RETRIEVAL_CODE_MAP.md) | ✅ như trên |
| 5 | Query Trace | [`QUERY_TRACE.md`](QUERY_TRACE.md) | ✅ sinh tự động trên index Gemini |
| + | Pipeline Audit & Improvement Plan (G1–G6) | [`MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md) | ✅ đầu file ghi trạng thái từng giả thuyết |
| + | Nhược điểm & giải pháp | [`../archive/NHUOC_DIEM_VA_GIAI_PHAP.docx`](../archive/NHUOC_DIEM_VA_GIAI_PHAP.docx) | 🗄️ lưu trữ |
| + | Kế hoạch triển khai | [`../archive/KE_HOACH_TRIEN_KHAI.md`](../archive/KE_HOACH_TRIEN_KHAI.md) | 🗄️ lưu trữ — việc còn lại đã giao ở [`../phan-cong/`](../phan-cong/) |
| T1 | Environment Guide | [`ENVIRONMENT.md`](ENVIRONMENT.md) | ⚠️ đường Gemini, mới xác minh trên Windows |
| HD | Schema log kết quả | [`HD_SCHEMA.md`](HD_SCHEMA.md) | ✅ dùng bởi `reproduce/run_eval_demo.py` |

## Phát hiện của Phase 1 — trạng thái hiện tại

- Query Trace phát hiện bước ④ Candidate Answer Entities **luôn trả về 0 ứng viên** do lệch hoa/thường khi so `entity_type`.
  **Đã sửa (G1), nhưng trên 637 câu bản vá không tăng điểm:** Gemini 24 lên / 29 xuống, p = 0,583; Qwen 44 lên / 40 xuống,
  p = 0,744. Báo cáo như kết quả phủ định.
- Số Phase 1 (Gemini, dev 200: acc 57,33 ± 1,53) và quy tắc "chênh dưới 3 điểm không kết luận được" **đã được thay**: baseline
  chính thức giờ là Qwen2.5-3B trên 637 câu (acc 51,02), và so hai cấu hình bằng McNemar ([`CLAUDE.md`](../../CLAUDE.md) §3).

## Sinh lại Query Trace

```bash
TRACE_FILE=./logs/trace_queries.txt .venv/bin/python reproduce/Step_5_trace.py --workingdir ./LiHua-World-gemini
```

⚠️ Lệnh này **ghi đè** `QUERY_TRACE.md`. Phần "Nhận xét" ở cuối file viết tay — nhớ dán lại sau khi chạy (trong file có dấu mốc
`<!-- PHẦN DƯỚI VIẾT TAY -->`).
