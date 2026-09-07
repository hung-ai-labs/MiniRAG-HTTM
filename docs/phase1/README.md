# Phase 1 — Hùng: Baseline + Retrieval + Query Trace

Năm đầu ra bắt buộc của Phase 1.

| # | Đầu ra | File |
|---|---|---|
| 1 | Baseline Config | [`../../baseline.yaml`](../../baseline.yaml) |
| 2 | Baseline Status | [`BASELINE_STATUS.md`](BASELINE_STATUS.md) |
| 3 | Retrieval Flow | [`RETRIEVAL_FLOW.md`](RETRIEVAL_FLOW.md) |
| 4 | Retrieval Code Map | [`RETRIEVAL_CODE_MAP.md`](RETRIEVAL_CODE_MAP.md) |
| 5 | Query Trace | [`QUERY_TRACE.md`](QUERY_TRACE.md) |
| + | **Pipeline Audit & Improvement Plan** | [`MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md) |

## Đọc theo thứ tự nào

`BASELINE_STATUS` cho biết nhóm đã chạy tới đâu và kết quả ra sao →
`RETRIEVAL_FLOW` giải thích MiniRAG hoạt động thế nào →
`RETRIEVAL_CODE_MAP` ánh xạ từng bước sang file/hàm cụ thể →
`QUERY_TRACE` cho thấy ba câu hỏi thật đi qua hệ thống.

## Số liệu chính

- Baseline (corpus 442, dev set 200 câu, 3 lượt judge): **acc 57,33 ± 1,53 · err 21,00 ± 2,00**
- Sàn nhiễu judge: **sd 1,53** → chênh lệch dưới ~3 điểm không kết luận được
- Điểm yếu rõ nhất: **Multi-hop acc 42,86% / err 42,86%**

## Phát hiện đáng chú ý

Query Trace xác nhận **bước ④ Candidate Answer Entities luôn trả về 0 ứng viên** do
lệch chữ hoa/thường khi so khớp `entity_type` — cơ chế answer-type-aware của MiniRAG
đang không chạy. Chi tiết ở cuối [`QUERY_TRACE.md`](QUERY_TRACE.md).

## Sinh lại Query Trace

```bash
TRACE_FILE=./logs/trace_queries.txt .venv/bin/python reproduce/Step_5_trace.py --workingdir ./LiHua-World-gemini
```

⚠️ Lệnh này **ghi đè** `QUERY_TRACE.md`. Phần "Nhận xét" ở cuối file viết tay — nhớ
dán lại sau khi chạy (trong file có dấu mốc `<!-- PHẦN DƯỚI VIẾT TAY -->`).
