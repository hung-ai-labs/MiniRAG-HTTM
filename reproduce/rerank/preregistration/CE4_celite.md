# CE4 — Đăng ký trước: CE-lite, xếp lại có chọn lọc

> 21/09/2026 · Viết **sau** bước thăm dò độ phủ và **trước** khi đo bất kỳ chỉ số xác nhận nào
> (giữ bằng chứng, Single/Multi/Null, an toàn Null, độ trễ của luật đã chốt).
> Chỉ offline: không sinh, không chấm, không 637, không tầng D. B2 đông lạnh vẫn là bản dự phòng chính thức.

## Vì sao có giai đoạn này

Phase 1 (CE3) đã xong và **trượt**: ONNX Runtime CPU fp32 tái hiện CE1 **chính xác** (nhóm A — điểm chênh tối đa
1,597e−05, thứ tự trùng 200/200, `chunk_ids` trùng 200/200, chồng lấp top-10 = 1,0000) nhưng **chậm hơn 2,71×** ở p50
(4958 so với 1830 ms) và 3,82× ở max. Theo luật đã chốt trong CE3, bước tiếp theo là CE-lite, **không** thử INT8 hay
backend thứ hai.

## Tách bạch: phần THĂM DÒ đã làm

`logs/rerank/celite_coverage.txt` (script `celite_coverage.py`). Nó **chỉ** đo **độ phủ** (chunk đáp án của ca đó có nằm
trong tập con không) và **chi phí** (ứng viên/câu, cửa sổ MaxP/câu). Nó **không** đo giữ bằng chứng, Single, Multi hay
Null — đúng để việc chọn N không bị lái bởi chỉ số xác nhận.

Số liệu thăm dò chính:

| Luật | phủ 11 ca CE1 cứu | phủ 20 ca | cửa sổ/câu | % chi phí CE1 |
|---|---|---|---:|---:|
| top 10 RRF | 4/11 | 5/20 | 21,8 | 23% |
| top 15 RRF | 8/11 | 11/20 | 32,3 | 34% |
| top 20 RRF | 9/11 | 13/20 | 42,6 | 46% |
| **top 25 RRF** | **11/11** | **16/20** | **52,5** | **56%** |
| top 30 RRF | 11/11 | 16/20 | 62,5 | 67% |
| hợp top 10 BM25 & vector | 9/11 | 11/20 | 34,1 | 36% |
| hợp top 15 BM25 & vector | 11/11 | 16/20 | 50,3 | 54% |
| hợp top 20 BM25 & vector | 11/11 | 18/20 | 65,4 | 70% |
| tiền tố token 2,5× ngân sách | 8/11 | 13/20 | 41,6 | 44% |
| tiền tố token 3,0× ngân sách | 9/11 | 15/20 | 48,7 | 52% |

Hạng RRF của 11 ca CE1 cứu được: `[6, 9, 9, 10, 11, 14, 14, 15, 17, 22, 24]`, max **24**.

## Luật CE-lite đã CHỐT (một luật, không quét lại)

> **Xếp lại bằng cross-encoder CE1 chỉ 25 ứng viên đầu theo thứ tự RRF. Phần còn lại giữ nguyên thứ tự RRF và
> nằm sau tiền tố. Sau đó A1@4000 như cũ.**

- Model, revision, tokenizer, MaxP, lô 32, CPU float32: **giống hệt CE1**. Chỉ đổi **tập được chấm**.
- Hoà điểm trong tiền tố → giữ thứ tự RRF (tất định).
- Không nhãn vàng lúc chạy. Không thêm lời gọi LLM. Không đổi BM25 / vector / RRF / A1@4000 / parser / prompt / ngân sách.

**Vì sao chọn tiền tố RRF, và vì sao N = 25:**
1. **Họ "tiền tố"** là họ duy nhất mà hai cách ghép ("tập con xếp lại lên trước, phần còn lại theo sau" và "hoán vị
   tập con trong đúng các vị trí nó đang chiếm") **trùng nhau**. Mọi họ khác buộc phải thêm một lựa chọn ghép tuỳ ý nữa.
2. **N = 25 là tiền tố NHỎ NHẤT mà độ phủ BÃO HOÀ** trong họ đã khảo sát: 25 và 30 cho cùng 11/11 và 16/20. Luật chọn
   phát biểu trước là *"lấy N nhỏ nhất nơi độ phủ bão hoà"*, không phải *"lấy N làm chỉ số cuối đẹp nhất"*.
3. Chi phí 56% cửa sổ. Ước tính tuyến tính: max 3429 × 0,56 ≈ **1920 ms**, dưới mốc 3000 ms với biên rộng.

**Cảnh báo phải ghi trước:** độ phủ là **điều kiện cần, không phải điều kiện đủ**. Chunk đáp án nằm trong tiền tố
không bảo đảm nó được đẩy đủ cao để vào A1, vì tiền tố 25 không cho phép một chunk hạng 40 nhảy lên đầu như CE1 làm được.
Nên **11/11 độ phủ có thể ra ít hơn 11 ca cứu thật**.

## Đây là BIẾN THỂ TRUY HỒI MỚI, không phải "tối ưu triển khai"

Theo luật 8 của nhóm: CE-lite đổi thứ hạng so với CE1 (chunk ngoài top-25 không còn được đẩy lên), nên nó **không**
được gọi là "vẫn là CE1". Nó cần phân tích an toàn offline riêng, và đó chính là nội dung dưới đây.

## Chỉ số xác nhận — đo MỘT LẦN cho luật trên

Phase 2A: ứng viên/câu · cửa sổ/câu · chi phí CPU **ước tính và đo thật** · bao nhiêu trong 11 ca CE1 cứu còn cứu được ·
giữ đủ bằng chứng trên dev · giữ→mất · mất→giữ · Single · Multi · token context · số chunk.
Bảng so sánh chính: **B2 vs CE1 đầy đủ vs CE-lite**.

Phase 2B (bắt buộc): sự kiện phân biệt trong Sources câu Null · chunk Null mới vào · chunk Null rời đi · ba chunk gây
nhầm **L002 / L052 / L055** · có chunk gây nhầm nào bị đẩy lên **so với B2 đông lạnh** không · CE-lite có làm **tăng**
bằng chứng gần giống so với **CE1 đầy đủ** không. **Không giả định "ít CE hơn thì an toàn hơn".**

## ⛔ Luật quyết định — chốt trước khi xem kết quả xác nhận

Ứng viên CE-lite đáng tin phải đạt **tất cả**:

| # | Điều kiện |
|---|---|
| 1 | giữ được phần lớn mức cải thiện truy hồi của CE1 |
| 2 | giữ được phần đáng kể trong 11 ca CE1 cứu được |
| 3 | Multi không tụt đáng kể ở mức offline |
| 4 | an toàn Null không xấu đi đáng kể — cụ thể: câu Null có chunk mới khớp đủ thực thể **≤ 7/20** (như cổng 4 của CE1), và **≤ 1** ca THOÁI LUI trong 3 chunk gây nhầm theo luật tiến cứu CE2 mục 1 |
| 5 | ngân sách context không đổi: cùng trần 4.000, token trung vị trong ±5% B2 |
| 6 | không thêm lời gọi LLM |
| 7 | độ trễ CPU đạt mốc vận hành **max ≤ 3000 ms/câu**, hoặc rõ ràng đủ gần để biện minh cho một thí nghiệm hệ thống có đăng ký riêng |

**Màn sàng độ phủ (hướng dẫn sàng lọc offline, KHÔNG phải ngưỡng ý nghĩa thống kê):**

| Số ca CE1 cứu còn giữ được | Kết luận |
|---|---|
| ≤ 5/11 | **DỪNG** |
| khoảng 9–11/11 kèm giảm độ trễ lớn | ứng viên mạnh |
| 6–8/11 | **không chắc** — báo cáo, không tự động đẩy tiếp |

Trượt → **DỪNG Phase 2**, không chạy QA, tắt chế độ thí nghiệm, giữ B2. Không quét lại N. Không sang Phase 3 khi chưa
được duyệt.

## Bất biến

Cờ tắt mặc định · đường đi B2 không đụng tới · reranker hỏng thì **ném lỗi**, không âm thầm trộn B2 với câu đã xếp lại
trong cùng một lượt đánh giá · không nhãn vàng lúc chạy.
