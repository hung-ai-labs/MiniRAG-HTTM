# Tài liệu dự án MiniRAG-HTTM

> Cập nhật 18/09/2026. Quy tắc bắt buộc: [`../CLAUDE.md`](../CLAUDE.md). Kế hoạch, lịch sử thí nghiệm và đăng ký trước:
> [`../ROADMAP.md`](../ROADMAP.md).

## Đọc gì trước

| Bạn cần | Đọc |
|---|---|
| **Báo cáo tổng hợp 18/09** — chốt B2, chuỗi kiểm nhóm Null, điều phải ghi khi viết bài | [`BAO_CAO_NHOM_18_09_2026.md`](BAO_CAO_NHOM_18_09_2026.md) |
| Kết quả hiện tại so với baseline (acc / err / neither / Null) | [`KET_QUA_HIEN_TAI.md`](KET_QUA_HIEN_TAI.md) |
| Việc của **thành viên 1** — cắt tỉa và chấm lại đường đi | [`phan-cong/THANH_VIEN_1_CAT_TIA_DUONG_DI.md`](phan-cong/THANH_VIEN_1_CAT_TIA_DUONG_DI.md) |
| Việc của **thành viên 1** — chấm tay 40 câu Null (Đ1, ~1 giờ) | [`phan-cong/THANH_VIEN_1_CHAM_LAI_NHOM_NULL.md`](phan-cong/CHAM_LAI_NHOM_NULL.md) |
| Việc của **thành viên 2** — hợp nhất thực thể trùng tên | [`phan-cong/THANH_VIEN_2_HOP_NHAT_THUC_THE.md`](phan-cong/THANH_VIEN_2_HOP_NHAT_THUC_THE.md) |
| Việc của **thành viên 2 (Anh Tài)** — rà 65 nhãn Null (Đ3, ~3 giờ) | [`phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md`](phan-cong/THANH_VIEN_2_RA_NHAN_NULL.md) |
| Đề xuất cải thiện nhóm Null (chẩn đoán B2, kiểm nhãn, kiểm giám khảo) | [`DE_XUAT_CAI_THIEN_NULL.md`](DE_XUAT_CAI_THIEN_NULL.md) |
| Chạy sàng lọc BM25 trên máy mình (Modal và khoá riêng) | [`../reproduce/screening/HUONG_DAN_CHAY.md`](../reproduce/screening/HUONG_DAN_CHAY.md) |
| MiniRAG truy hồi thế nào | [`phase1/RETRIEVAL_FLOW.md`](phase1/RETRIEVAL_FLOW.md) → [`phase1/RETRIEVAL_CODE_MAP.md`](phase1/RETRIEVAL_CODE_MAP.md) → [`phase1/QUERY_TRACE.md`](phase1/QUERY_TRACE.md) |
| Audit pipeline và các giả thuyết G1–G6 | [`phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md`](phase1/MINIRAG_PIPELINE_AND_IMPROVEMENT_PLAN.md) |
| Môi trường Phase 1 (đường Gemini, Windows) | [`phase1/ENVIRONMENT.md`](phase1/ENVIRONMENT.md) |
| Schema `logs/results.json` của runner HD1 | [`phase1/HD_SCHEMA.md`](phase1/HD_SCHEMA.md) |
| Tài liệu cũ đã được thay thế | [`archive/`](archive/README.md) |

## Ai đang làm gì — ranh giới để không đụng nhau

| Người | Việc | Được sửa | Chỉ đọc |
|---|---|---|---|
| Hùng | Sàng lọc BM25: B1 = RRF(đồ thị, vector, BM25), B2 = RRF(vector, BM25) | khối trộn chunk và ghi log trong `_build_mini_query_context`; `_rrf_fuse`, `_bm25_index`, `_keyword_llm`, `minirag_query`; `minirag/bm25.py`; `reproduce/screening/`; `logs/screening/`; tầng D: `reproduce/stage_d/`, `logs/stage_d/` | — |
| Thành viên 1 | Cắt tỉa và chấm lại đường đi; **chấm tay 40 câu Null (Đ1)** | `logs/null_audit/d1_judge_audit/sheet_A.csv`; `minirag/path_rerank.py`; đoạn duyệt đường đi trong `_build_mini_query_context` (chỉ thêm hook, mặc định giống hệt); hàm mới trong `minirag/utils.py`; `reproduce/path/`; `logs/path/` | index chung; `logs/screening/cache/` |
| Thành viên 2 (Anh Tài) | Hợp nhất thực thể trùng tên; **rà 65 nhãn Null (Đ3)** | `logs/null_audit/d3_label_audit/sheet_A.csv`; `reproduce/entity_resolution/`; `logs/entity_resolution/`; index mới `LiHua-World-qwen-entres/` | index chung; toàn bộ `minirag/` |

**Chung cho cả nhóm**
- `LiHua-World-qwen-modal/` là index chung — không ai ghi vào (CLAUDE.md §4).
- Mọi công tắc mới mặc định tắt; không đặt biến thì kết quả phải giống hệt trước.
- Chạy QA trên 200 / 435 / 637 câu cần nhóm duyệt. Mỗi bước chỉ một người chạy.

## Cấu trúc thư mục

```
docs/
├── README.md               ← file này
├── KET_QUA_HIEN_TAI.md     ← bảng kết quả; cập nhật mỗi khi có lượt chính thức mới
├── phan-cong/              ← việc giao cho từng thành viên
├── phase1/                 ← tài liệu tham khảo Phase 1: đọc code, trace, môi trường
└── archive/                ← tài liệu đã lỗi thời, giữ để tra cứu
```
