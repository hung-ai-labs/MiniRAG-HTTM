# CE2 — Đăng ký trước cho tầng canary của chế độ CE1

> 20/09/2026 · Viết **trước khi chạy canary**, sau khi kết quả offline CE1 đã chốt (`logs/rerank/CE1_KET_QUA.md`,
> commit `04cdae8`). Đây là tài liệu **tiến cứu**: nó **không** sửa lại đăng ký trước CE1 (`7fe9325`), chỉ nói rõ cách
> áp dụng cho các tầng sau.

## 1. Làm rõ tiến cứu về cổng Null mơ hồ

Đăng ký trước CE1 viết cổng 5 là *"không ca nào chunk gây nhầm lên hạng 1; không quá 1 ca nó tăng hạng"*. Câu này mơ hồ
với L052, vốn **đã** ở hạng 1 trong B2 và ở nguyên hạng 1 sau khi xếp lại. Sự mơ hồ được **ghi đúng như đã quan sát**
trong `CE1_KET_QUA.md` và **không** được giải nghĩa theo hướng có lợi.

**Luật tiến cứu, áp dụng từ canary trở đi (nhóm chốt 20/09/2026):**

> *Một chunk gây nhầm Null đã biết chỉ tính là **thoái lui an toàn** nếu reranker thí nghiệm **đẩy nó lên** so với B2
> đông lạnh. Chunk vốn đã ở hạng 1 trong B2 và vẫn ở hạng 1 thì là **không đổi** — không phải thoái lui mới, cũng không
> phải cải thiện.*

Hệ quả cho ba ca đã biết, theo số đo offline:

| | B2 → CE1 | phân loại theo luật trên |
|---|---|---|
| L002 (`20260112_10:00`) | 8 → 3 | **THOÁI LUI** (bị đẩy lên) |
| L052 (`20260214_16:00`, whey) | 1 → 1 | **TRUNG TÍNH** |
| L055 (`20261113_13:00`) | 4 → 16, rời Sources | **CẢI THIỆN** |

Cổng cho canary và mọi tầng sau: **≤ 1 ca THOÁI LUI trong 3 ca đã biết**. Hiện là 1 → đạt, nhưng **không còn dư địa**.

## 2. Cổng thời gian — tuyên bố lệch trước khi chạy

Bộ sàng lọc hiện có (`reproduce/screening/screen_variant.py`, `safety()`) đặt cổng canary **"truy hồi thêm ≤ 50 ms"**.
Cổng đó được hiệu chỉnh cho BM25 — một thao tác 1 ms. Một reranker học **cố ý** đánh đổi tính toán lấy chất lượng, nên
nó sẽ trượt cổng này theo thiết kế, không phải vì hỏng.

**Không vặn cổng cũ cho vừa.** Thay vào đó:
- cổng 50 ms vẫn chạy và **ghi TRƯỢT nguyên văn** trong báo cáo canary — không giấu;
- cổng thời gian thật của CE1 là **cổng 8 đã ghim trong đăng ký trước CE1** (viết trước mọi kết quả):
  **phần xếp lại ≤ 3000 ms mỗi câu trên CPU**. Đo được: p50 1601 ms, p95 2388 ms → đạt;
- thêm trần tổng, tuyên bố ở đây trước khi chạy: **tổng truy hồi p95 ≤ 2× p95 của B2 đông lạnh** (10024 → trần 20048 ms).

Thiết bị runtime cho canary: **CPU**, đúng như đã ghim. MPS nhanh gấp đôi và cho thứ hạng trùng khít, nhưng đổi thiết bị
để làm đẹp số đo là việc không được làm.

## 3. Cấu hình canary

| | |
|---|---|
| Bộ câu | `reproduce/screening/canary100.csv` — 100 câu cố định, đã đóng băng |
| Mốc so sánh | B2 đông lạnh, cùng bộ câu, cùng seed sinh 20260914 |
| Biến thể | `MINIRAG_CHUNK_FUSION=vector_bm25` **+** `MINIRAG_RERANK=ce1` — khác B2 **đúng một biến** |
| Không đổi | BM25, vector, RRF, A1@4000, parser, generator, prompt, ngân sách token, seed |
| Lượt | 1 lượt sinh, 3 lượt chấm (như mọi tầng canary trước) |
| Điều kiện tiên quyết | 9 selftest phải ĐẠT hết (`reproduce/rerank/run_selftest.sh`) |

## 4. Cổng quyết định canary — chốt trước khi chạy

Giữ nguyên bộ cổng an toàn sẵn có của tầng canary, cộng luật Null ở mục 1:

| # | Cổng | Nguồn |
|---|---|---|
| 1 | Null net ≥ −3 | `safety()` sẵn có |
| 2 | Multi net ≥ −3 | `safety()` sẵn có |
| 3 | số phiếu `error` tăng ≤ +3 | `safety()` sẵn có |
| 4 | token context trung vị ±5% | `safety()` sẵn có |
| 5 | ≤ 1 ca THOÁI LUI trong 3 chunk gây nhầm đã biết | mục 1 trên |
| 6 | phần xếp lại ≤ 3000 ms/câu trên CPU | cổng 8 của CE1 |
| 7 | tổng truy hồi p95 ≤ 2× B2 | mục 2 trên |
| 8 | cổng 50 ms cũ: **ghi nhận TRƯỢT**, không dùng để quyết | mục 2 trên |

**Null là ràng buộc an toàn, không phải mục tiêu.** Nếu tổng thể tốt lên mà **Null xấu đi rõ rệt** thì reranker
**trượt** — không có chuyện bù trừ.

Trượt bất kỳ cổng 1–7 → dừng, không chạy dev 200, tắt cờ, giữ B2, ghi kết quả phủ định.
Đạt hết → **dừng và xin duyệt**. Không tự chạy dev 200. Không chạm 637 hay tầng D.

## 5. Diễn giải

Không được viết bất cứ điều gì về "giải quyết ảo giác" hay "giải quyết Null". Canary 100 câu, một lượt sinh — theo
CLAUDE.md §3 nó là **cổng sàng lọc rẻ**, không phải bằng chứng. Sàn nhiễu sinh trên dev là 1,5 điểm; canary nhỏ hơn dev
nên nhiễu còn lớn hơn.
