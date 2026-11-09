# Câu Null dùng ngân sách Sources thế nào (log-only, 20 câu Null dev)

09/11/2026. Chỉ truy hồi, offline, không sinh câu trả lời, không có nhãn (Null không có chunk đáp án). Tái tạo:
`null_budget.py --name c0|p_ff|p_d05f` rồi `null_analysis.py`; số liệu ở `logs/graph_repair/p_pack/null_summary.json`.
Cache từ khoá có sẵn cho cả 20 câu Null (200/200 câu dev), nên không cần gọi model.

| Trung vị | 20 câu Null | 180 câu có đáp án |
|---|---:|---:|
| thực thể xuất phát | 175 | 150,5 |
| ứng viên chunk | 128 | 109,5 |
| điểm chunk số 1 | **26,0** | 20,2 |
| chunk vào Sources (C0) | 7 | 6 |
| token Sources (C0) | 3.539 | 3.692 |
| phần điểm top-30 mà Sources giữ (C0) | 0,59 | 0,57 |

**Điểm đồ thị không tố cáo câu Null.** Câu Null có điểm chunk số 1 *cao hơn*, nhiều thực thể xuất phát hơn, và dùng ngân sách gần như giống câu thường. Đồ thị tìm được "nhiều thứ trông liên quan" cho câu không có đáp án; không có tín hiệu điểm nào tách được Null (n = 20, mô tả, không kiểm định). Điều này khớp với kết luận đã chốt ở CLAUDE.md: đừng mở lại hướng verifier/từ chối.

## P-FF và P-D05F đổi Sources của câu Null thế nào

| | P-FF Null | P-FF thường | P-D05F Null | P-D05F thường |
|---|---:|---:|---:|---:|
| câu có tập chunk đổi | 16/20 | 131/180 | **20/20** | 166/180 |
| Jaccard với C0 (tv) | 0,80 | 0,83 | **0,60** | 0,60 |
| chunk thêm/câu (tv) | 2 | 1 | 4 | 3 |
| tổng chunk thêm | 34 (1,7/câu) | 239 (1,3/câu) | 94 (4,7/câu) | 694 (3,9/câu) |
| token thêm (tv) | +385 | +236 | +398 | +190 |
| hạng đồ thị của chunk thêm (tv) | 11 | 13 | 14 | 15 |
| điểm chunk thêm / điểm chunk số 1 (tv) | 0,17 | 0,12 | 0,14 | 0,12 |

Đọc:
- P-D05F thêm trung bình **4,7 chunk điểm thấp** (≈ 14% điểm của chunk số 1, hạng ~14) vào mỗi câu Null, so với 3,9 ở câu thường. Cơ cấu không khác nhiều giữa hai nhóm, nhưng Null chịu thay đổi ở **mọi** câu (20/20).
- Chunk thêm đều là chunk điểm thấp, ngắn: đúng loại "mảnh chat trông gần giống nhưng thiếu ngữ cảnh". Đây là cơ chế có thể làm Qwen bịa ở Null. **Đây là mô tả cơ chế, không phải bằng chứng về accuracy**; chỉ bước accuracy mới trả lời được.
- Với P-FF phần lớn tác động là cùng loại nhưng nhẹ hơn (1,7 chunk/câu Null).

## Giới hạn
n = 20, không nhãn, không kiểm định; chỉ cho biết *khối lượng* thay đổi, không cho biết thay đổi tốt hay xấu.
