# Người 2 — kết quả dev 180 (B4)

Chạy 09/11/2026 13:00–13:37, offline, một lượt mỗi lúc. Tạo bằng `compare_pack.py`; số liệu thô ở `logs/graph_repair/p_pack/dev_summary.json`.
Đăng ký đóng băng trước đó: `REGISTRATION.md`, sha256 `8baf2a7f59a585120c00f376ea78df3521f731b8f6faacc8df10fb927a2dd3ed` (12:47:51).

**Hồi quy với mọi công tắc tắt (`c0_reg`): 180/180 `chunk_ids` giống C0 đóng băng.**

| Nhánh | Câu đủ đáp án | Single | Multi | Micro recall | Lên / xuống vs C0 | McNemar p | Token Sources (tv) | Chunk/câu (tv) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 75/180 | 69 | 6 | 46,4 | — | — | 3.692 | 6,0 |
| P-FF *(đối chứng, sửa bước cắt)* | 77 | 71 | 6 | 47,8 | 2 / 0 | 0,50 | 3.944,5 | 7,5 |
| P-D1 | 76 | 68 | 8 | 48,3 | 7 / 6 | 1,00 | 3.731,5 | 10,0 |
| P-D05 | 77 | 69 | 8 | 48,8 | 6 / 4 | 0,754 | 3.685,5 | 9,0 |
| **P-D05F** | **78** | 70 | 8 | 49,8 | 7 / 4 | 0,549 | 3.922 | 9,5 |

So với P-FF (tách xếp lại khỏi lấp ngân sách): P-D1 5 lên / 6 xuống (p = 1); P-D05 4 / 4 (p = 1); **P-D05F 5 / 4 (p = 1)**.

Khớp mô phỏng B1: P-FF = S1, P-D1 = S4, P-D05 = S12 (đúng từng con số). P-D05F chưa mô phỏng; dự đoán 77 ± 1, thực tế 78.

## Áp luật chọn đã đăng ký (một lần)

1. Trong P-D1 / P-D05 / P-D05F, câu đủ cao nhất: **P-D05F (78)**.
2. (a) lên ≥ xuống so với C0: 7 ≥ 4 → **đạt**.
   (b) số câu đủ > P-FF: 78 > 77 → **đạt, chỉ hơn 1 câu**.

⇒ Theo luật, P-D05F được chuyển sang 435 câu ngoài dev. **Dự đoán chính của đăng ký (điều kiện b thất bại) đã sai**: nó đạt, nhưng với biên 1 câu.

## Giới hạn khi đọc (nói thẳng)

- Không phép so sánh nào có ý nghĩa thống kê: McNemar p từ 0,50 đến 1,00; P-D05F so P-FF là 5 lên / 4 xuống.
- Dev đã bị xem qua mô phỏng ở B1 (khai trong REGISTRATION), nên đây không phải bằng chứng độc lập; luật chọn chỉ dùng như cổng.
- Nhánh được chọn thay đổi tập Sources ở 166/180 câu (Jaccard thấp), chunk/câu 6 → 9,5: rủi ro với câu Null, chưa đo được ở đây.
- Mức tăng chunk đáp án giữ được (96 → 103/207 ở P-D05F; P-FF 99) và micro recall (+3,4 điểm) là truy hồi, chưa phải accuracy.
- Phép thử thật (435 câu × 3 lượt sinh) cần `phased_qa.py` và cache từ khoá ở máy chính; **chưa chạy**.
