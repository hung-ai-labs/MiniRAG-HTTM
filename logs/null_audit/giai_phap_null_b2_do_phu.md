# Kiểm độ phủ — đề xuất "xếp hạng bằng chứng theo điều kiện sự kiện"

> 19/09/2026 · Đề xuất: [`docs/GIAI_PHAP_NULL_B2_18_09_2026.md`](../../docs/GIAI_PHAP_NULL_B2_18_09_2026.md), mục 6.
> **Chỉ dùng dev** (theo đúng mục 6 của đề xuất). Không gọi API, không chạy QA.
> Người đọc: Claude, theo quy tắc phạm vi hẹp của mục 3. Đây là **cổng khả thi** để quyết định có viết code hay không — không phải
> nhãn người để đưa vào bài.

## Dữ liệu

- Câu trả lời và context của B2 trên dev: `logs/screening/b2/answers.jsonl` (một lượt sinh, một lượt chấm, rubric gốc).
- 20 câu Null dev: B2 đúng 11, **sai 9**. Kiểm cả 9 câu sai, đọc toàn bộ chunk B2 đưa vào Sources.
- Nhãn Đ3 (Tài, một người rà) chỉ dùng để đối chiếu, module không được đọc.

## Luật áp dụng (mục 3 của đề xuất)

- Điều kiện chỉ lấy khi nêu nguyên văn: tên người, ngày tuyệt đối, mẫu trạng thái rõ. Ngày tương đối, "last", "Thursday" → chưa xác định.
- Không dùng trường `Time:` để kết luận xung đột ngày. Thiếu thông tin **không** phải mâu thuẫn.
- Kích hoạt chỉ khi có **ít nhất một chunk khớp và một chunk không khớp rõ**; câu nhiều sự kiện → giữ B2.

## Kết quả từng câu

| Câu | Nhãn Đ3 | Điều kiện nêu rõ | Chunk khớp | Chunk không khớp rõ | Kích hoạt |
|---|---|---|---|---|---|
| L002 · thiết bị Wolfgang dùng ở gym | CO_MOT_PHAN | người | có thể (Wolfgang + gym, nhưng là *dự định* "maybe hit the treadmill") | không | **không** |
| L055 · món Thane thích khi chơi game | KHONG_CO | người | **không có** — chunk có Thane chỉ nói game | có (chat đồ ăn nhanh của Li Hua và Wolfgang, không có Thane) | **không** — thiếu chunk khớp |
| L036 · loài hoa mới theo phản hồi của Li Hua | CO_MOT_PHAN | người, dịp "progress reports" | Li Hua gợi ý luống hoa (trạng thái *gợi ý*) | không — "progress report" cần suy luận ngữ nghĩa | **không** |
| L052 · protein sau buổi tập 19/09/2026 | KHONG_CO | **ngày tuyệt đối**, người | chunk 20260919 (nhắc bổ sung protein, không nói loại) | chunk 20260214 (khuyên whey) chỉ lệch ngày qua `Time:` → bị cấm dùng | **không** |
| L048 · mục tiêu tập luyện cho marathon | CO_MOT_PHAN | người | không rõ | không | **không** |
| L054 · số đo cửa sổ | CO_DU | người | có — đúng câu có đáp án | không | **không** |
| L029 · phản hồi cho Chae + vai trò Wolfgang | CO_DU | hai sự kiện | — | — | **không** — ngoài phạm vi (nhiều sự kiện) |
| L023 · góp ý của Yuriko tại Central Perk sáng thứ Năm | CO_MOT_PHAN | người, địa điểm; "Thursday morning" tương đối | chỉ tin nhắn *hẹn* | không — tin 12/03 "loved the demo… this morning" khớp với thứ Năm | **không** |
| L006 · gợi ý của Li Hua về lịch thi công "last meeting" | CO_MOT_PHAN | người; "last" tương đối | không | không | **không** |

## Kết luận

**Kích hoạt 0/9.** Theo đúng điều kiện dừng của đề xuất (mục 6: "context cuối gần như không đổi → dừng trước QA lớn"), nên dừng.

Ba lý do, mỗi lý do đủ để chặn:

1. **Câu Null thật không có chunk khớp.** Chỉ 2/9 câu là Null thật theo Đ3 (L055, L052). L055 đúng là loại lỗi đề xuất nhắm tới
   — gán chuyện đồ ăn nhanh của Wolfgang cho Thane — và có chunk *không khớp rõ* theo người, nhưng không có chunk *khớp*, nên luật
   kích hoạt không bao giờ chạy.
2. **Ngay cả trường hợp tốt nhất, context không đổi.** L052 là câu duy nhất có ngày tuyệt đối. Nếu nới luật cho dùng `Time:`, module
   sẽ đảo chunk 20260919 lên trước chunk 20260214 — nhưng B2 đưa 11 chunk vào Sources và **cả hai đều nằm trong ngân sách**. Nội
   dung context giữ nguyên, chỉ đổi thứ tự. (Câu trả lời của B2 ở câu này vốn đã nói "no particular type is mentioned" — loại câu pha
   trộn mà rubric Đ6 chấm `accurate`.)
3. **7/9 lỗi nằm ở câu corpus có đáp án đầy đủ hoặc một phần** (CO_DU 2, CO_MOT_PHAN 5). Ở đó nếu module kích hoạt, nó sẽ đẩy chunk
   *khớp* — chính là chunk chứa câu trả lời — lên trước, khiến B2 trả lời tự tin hơn và err so với đáp án vàng "Insufficient
   information" tăng.

**Phạm vi thật của module nằm ở câu có đáp án:** dev có 23/178 câu Single/Multi nêu ngày tuyệt đối, so với 3/20 câu Null. Nếu làm tiếp,
đây là một cơ chế xếp hạng cho câu có đáp án — phải đánh giá như vậy, không phải như giải pháp Null.

## Giới hạn

- Một người đọc (Claude), dev 20 Null, một lượt sinh, nhãn Đ3 của một người (L023, L054 thuộc 4 dòng nhiễm).
- Chỉ kiểm 9 câu B2 trả lời sai; 11 câu đúng không kiểm vì mục tiêu là đo khả năng sửa lỗi.
- Không đọc câu ngoài dev để viết luật.
