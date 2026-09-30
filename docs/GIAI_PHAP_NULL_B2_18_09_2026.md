# Giải pháp Null cho B2 không fine-tune: xếp hạng bằng chứng theo điều kiện sự kiện

> Cập nhật 18/09/2026 theo ràng buộc của nhóm: **không fine-tune**.
> Bản này thay thế đề xuất LoRA trước đó. Đây là giả thuyết cần kiểm tra, chưa có kết quả hiệu quả.
> Cơ sở: [báo cáo nhóm 18/09](BAO_CAO_NHOM_18_09_2026.md), Đ6 và các phép thử A3, V5a–V5e.
> Chỉ đề xuất thiết kế; chưa sửa runtime, chạy QA/API, đổi index hoặc thay số chính thức và cổng E4.

## 1. Quyết định đề xuất

**Giữ Qwen2.5-3B và B2 = RRF(vector, BM25), bổ sung một bước xếp hạng bằng chứng theo điều kiện sự kiện trước khi cắt Sources A1@4000.**

B2 tìm tốt những đoạn liên quan chủ đề nhưng có thể đưa vào context sự kiện gần giống mà không trả lời được câu hỏi.
Bước mới chỉ thay thứ tự khi xác định được bằng chứng thuộc sự kiện phù hợp hoặc có điều kiện rõ ràng không khớp.
Trường hợp mơ hồ giữ hành vi B2. Không thêm verifier sau sinh, không dùng ngưỡng cosine để ép từ chối.

**Chưa thể khẳng định khả năng thành công cao.** Xếp hạng lại không tự làm Qwen biết từ chối; nếu đoạn gây nhầm vẫn nằm trong
4.000 token hoặc không nhận diện được điều kiện sai, Null có thể không cải thiện. Phép kiểm offline phải xác định độ phủ trước.

## 2. Vấn đề cần giải quyết

- Theo rubric làm rõ Đ6: Null err baseline 13,3%, B2 25,9%; Null acc tương ứng 86,7% và 74,1%.
  Baseline mới một lượt sinh, B2 ba lượt; độ lớn chênh lệch còn giới hạn này.
- B2 đạt acc tổng 73,95%, err 19,54% trên tầng D theo rubric gốc. Không ghép Null của Đ6 vào số tổng chính thức.
- Lỗi cần nhắm đến: đúng chủ đề nhưng sai người, thời điểm, dịp, hoặc biến lời khuyên/ý định thành hành động đã xảy ra.
- P1/P2 đổi duyệt đường đi; E1 gộp thực thể. Chúng không trực tiếp xử lý quan hệ giữa điều kiện câu hỏi và bằng chứng trong Sources.

Ví dụ minh hoạ độc lập: hỏi “Mai đã mua trà gì ngày 12/05?”. Đoạn Mai mua ô long ngày 03/04 liên quan về chủ đề,
nhưng không chứng minh loại trà đã mua ngày 12/05. Đoạn nói Mai cân nhắc mua trà cũng không chứng minh việc mua đã xảy ra.
**Hai đoạn này không chứng minh câu hỏi không có đáp án; chúng chỉ không đủ để làm bằng chứng cho hành động được hỏi.**

## 3. Cơ chế và phạm vi phiên bản đầu

### 3.1 Lấy điều kiện nêu rõ trong câu hỏi

Biểu diễn ứng viên:

`người — hành động — đối tượng — thời gian/sự kiện — trạng thái hành động`

Chỉ lấy điều kiện có trong câu hỏi, kèm vị trí văn bản gốc. Không tự bổ sung ngày, người, hoặc quan hệ suy đoán.
Phiên bản đầu dùng quy tắc tất định có phạm vi hẹp: tên xuất hiện nguyên văn, ngày rõ ràng, mẫu diễn đạt rõ về trạng thái.
Đại từ chưa giải được, ngày tương đối chưa có mốc, alias mơ hồ và sự kiện cần suy luận nhiều bước → đánh dấu chưa xác định.

Trạng thái hành động là hạng mục khó: “recommended”, “planned”, “bought”, “used” chỉ là dấu hiệu ứng viên.
Không gán cả chunk là “lời khuyên” vì nó chứa từ “recommend”; câu sau có thể xác nhận đã thực hiện.
Nếu cần LLM/NLI để quyết định hầu hết trường hợp thì phiên bản này chưa khả thi; không lặng lẽ biến nó thành verifier cũ.

### 3.2 Gắn bằng chứng với sự kiện trong chunk

Đọc câu chứa hành động cùng ngữ cảnh người nói và lượt hội thoại liên quan; giữ đoạn trích và chunk id để kiểm toán.
Một bản ghi tối thiểu gồm:

- Điều kiện trong câu hỏi và vị trí ký tự.
- Đoạn văn trong chunk cho phép xác định điều kiện của sự kiện.
- Người nói, người thực hiện hành động nếu xác định được, thời gian sự kiện nếu có.
- Trạng thái so khớp, mã quy tắc và lý do chưa xác định.

**Ngày tin nhắn không nhất thiết là ngày sự kiện.** Tin nhắn tháng 10 có thể thuật lại việc tháng 9.
Không dùng trường `Time:` để tự động kết luận xung đột ngày. Tương tự, người nói không nhất thiết là người thực hiện hành động.

### 3.3 Chia ba nhóm, không coi thiếu thông tin là mâu thuẫn

| Nhóm | Định nghĩa | Xử lý |
|---|---|---|
| Khớp điều kiện | Có đoạn trích gắn hành động được hỏi với các điều kiện đã phân tích, không có điều kiện chưa giải quyết trong phạm vi áp dụng | Ưu tiên |
| Chưa xác định | Thiếu thông tin, cần nối nhiều chunk, hoặc quy tắc không đủ tin cậy | Giữ thứ tự tương đối B2 |
| Không khớp rõ | Đoạn liên quan mô tả sự kiện khác theo điều kiện xác định được và không chứa bằng chứng phù hợp khác | Hạ thứ tự |

“Khớp điều kiện” **không phải** kết luận rằng chunk có đáp án đầy đủ. “Không khớp rõ” cũng **không phải** nhãn Null của câu hỏi.
Lời khuyên và hành động có thể cùng xuất hiện; một chunk có nhiều sự kiện phải được kiểm toàn đoạn.
Không hạ cả chunk nếu chỉ một sự kiện không khớp nhưng phần khác còn có thể cung cấp đáp án hoặc mắt xích Multi.

### 3.4 Xếp hạng bảo thủ

Giữ danh sách ứng viên và điểm RRF B2. Đề xuất quy tắc đầu tiên để kiểm offline:

1. Nếu câu hỏi nằm ngoài phạm vi phân tích, cần ghép nhiều sự kiện, hoặc không có chunk khớp điều kiện đáng tin cậy:
   trả lại danh sách B2 nguyên vẹn.
2. Chỉ kích hoạt khi có ít nhất một chunk khớp và một chunk không khớp rõ.
3. Trong các vị trí vốn thuộc hai nhóm xác định được, đưa nhóm khớp lên trước nhóm không khớp; giữ thứ tự B2 trong mỗi nhóm.
   Giữ nguyên vị trí của nhóm chưa xác định để hạn chế xáo trộn bằng chứng gián tiếp.
4. Áp dụng cùng A1@4000 sau khi xếp lại. Không giảm ngân sách, không bỏ cố định một số chunk, không chèn câu trả lời từ chối.

```text
candidates = B2_candidates(question)
labels = classify_with_explicit_rules(question, candidates)
if outside_supported_scope(labels) or not (has_match(labels) and has_mismatch(labels)):
    ordered = candidates
else:
    ordered = stable_reorder_known_slots(candidates, labels)
context = A1_4000(ordered)
answer = unchanged_Qwen(question, context)
```

**Đánh đổi có chủ ý:** cơ chế này ưu tiên bảo vệ câu có đáp án, nên có thể bỏ qua phần lớn Null.
Nếu mọi chunk chỉ gần giống hoặc chưa xác định, nó không can thiệp. Không được báo rằng phương án giải được mọi câu thiếu bằng chứng.
Nếu độ phủ thực tế quá thấp thì dừng, không nới sang “không thấy điều kiện nên chắc là sai”.

## 4. Những gì giữ nguyên và điểm tích hợp

Giữ model/trọng số, embedding, index, parser hiện tại, BM25, RRF k=60, top-k, A1@4000, bảng Entities,
prompt sinh, temperature và max output token. Bước phân tích điều kiện là module mới tất định, không thay parser LLM chung.

Vị trí dự kiến: trong `minirag/operate.py`, sau khi lấy nội dung ứng viên của nhánh `vector_bm25`, trước
`truncate_list_by_token_size` cho Sources. Việc thiết kế chi tiết sẽ kiểm lại code tại thời điểm triển khai.
Không index lại và không ghi vào index hiện có; log dẫn chứng/điều kiện để ở thư mục thí nghiệm riêng.

Giữ nguyên văn, người nói và ranh giới hội thoại. Không dùng LLM tóm tắt hay nén context trong cùng phép thử.
Module tắt phải cho context giống hệt B2. Module bật nhưng không kích hoạt cũng phải cho context giống hệt B2.
Log danh sách trước/sau, đoạn trích, mã quy tắc, chunk bị đẩy khỏi ngân sách và hash context.

Độ trễ phân tích quy tắc phải đo; không mặc định rằng thêm bước này miễn phí. Số lượt gọi LLM lúc suy luận không tăng.

## 5. Khác các hướng đã đóng

| Hướng | Tín hiệu quyết định |
|---|---|
| A3 / độ phủ tiền đề | Độ tương đồng hoặc mức trùng từ để dự đoán khả năng trả lời |
| V5d/V5e | Model đánh giá hỗ trợ/không hỗ trợ cho câu trả lời sau sinh |
| Đề xuất này | Điều kiện sự kiện có dẫn chứng cụ thể trong câu hỏi và đoạn gốc, dùng để xếp thứ tự trước sinh |

Không mở lại cổng từ chối hoặc confidence threshold. Nếu một quy tắc phải nhờ Qwen đoán “đoạn này có trả lời được không”,
đó là thay đổi bản chất thiết kế và cần đánh giá lại dưới các kết quả phủ định cũ.

Đây là thay đổi cơ chế chọn bằng chứng, không phải chỉnh top-k hay thêm lời nhắc prompt.
Tuy vậy, chưa có hiệu quả và chưa khảo sát đầy đủ tính mới; không tự nhận là đóng góp khoa học đã xác lập.

## 6. Kiểm tính khả thi offline trước khi chạy QA

Chỉ thiết kế quy tắc trên dev. Không đọc thêm lỗi ngoài dev để viết luật riêng cho từng câu.
Đánh giá toàn bộ dev 200 gồm câu đúng và sai, không chỉ những câu Null có ví dụ đẹp.
Nhãn Type, Evidence và phán quyết chỉ dùng để đánh giá; module runtime không được đọc chúng.

### Cần đo

1. **Độ phủ:** bao nhiêu câu phân tích được, bao nhiêu kích hoạt, bao nhiêu đổi context sau A1.
2. **Độ đúng của quy tắc:** người rà xem điều kiện và đoạn trích; đếm gán nhầm khớp/không khớp, đặc biệt lỗi ngày và chủ thể.
3. **Null:** trong lỗi B2 đã quan sát trên dev, bao nhiêu trường hợp giảm được đoạn có thể gây nhầm trong context cuối.
   Đoạn gây nhầm vẫn ở Sources thì không được tính là đã loại bỏ nguyên nhân.
4. **Single/Multi:** chunk gold và toàn bộ chuỗi bằng chứng còn sống sau A1; báo cả câu giữ được và câu mất đi.
5. **Bảo toàn:** câu không kích hoạt có hash context giống B2; kiểm không rơi mất văn bản, đảo nhầm người nói hay dùng nhãn gold.
6. **Efficiency:** latency p50/p95 và token context, trên cùng máy với cách đo xen kẽ.

Đề xuất cổng an toàn cho bản đầu: không chấp nhận mất thêm bộ bằng chứng đầy đủ nào của 180 câu dev có evidence;
đồng thời phải có thay đổi context phù hợp ở ít nhất một lỗi Null được người rà xác nhận. Đây chỉ là cổng đi tiếp tối thiểu,
không chứng minh hiệu quả hoặc mức tăng 5 điểm. Nếu tác động chỉ một ca, phải ghi độ phủ quá thấp để kết luận rộng.

Nếu không nhận diện được lỗi đáng kể, hạ nhầm bằng chứng, hoặc context cuối gần như không đổi: dừng trước QA lớn.
Không dùng “net oracle” offline như số câu chắc chắn sẽ được cứu: Qwen có thể tiếp tục suy đoán dù đã hạ đoạn gây nhầm.

## 7. Pilot và cổng chất lượng

Khi offline qua cổng, khoá module, phạm vi áp dụng, phiên bản dữ liệu và giao thức trước khi chạy.
So B2 với B2 + module trên dev 200, ít nhất ba lượt sinh ghép seed nếu dùng kết quả để quyết định tiến lên đánh giá cuối.
Đối chứng phải cùng endpoint/model revision và tham số sinh; không chỉ so một lượt mới với con số tổng cũ.

Các biên sau là **đề xuất mới cần chốt trước pilot**, không phải cổng E4 cũ hay kết quả dự báo:

| Chỉ số so với B2 | Mục tiêu / giới hạn |
|---|---|
| Null acc theo rubric Đ6 đã khoá | Mục tiêu tăng ít nhất 5 điểm % |
| Null err theo rubric Đ6 | Giảm; không chỉ đổi hình thức rào đón |
| Acc của câu có đáp án | Giảm không quá 1 điểm % |
| Acc tổng theo rubric gốc | Giảm không quá 1 điểm % |
| Err tổng theo rubric gốc | Tăng không quá 0,5 điểm % |
| Multi | Báo riêng; giảm quá 2 điểm % là tín hiệu dừng/điều tra |

Luôn báo acc/err/neither, đúng→sai hoặc từ chối, sai→đúng và tỷ lệ từ chối nhầm ở câu có đủ bằng chứng.
Dev chỉ có 20 Null nên đây là sàng lọc. Không được coi thay đổi một câu là bằng chứng chắc chắn đạt mục tiêu.

Với tỷ lệ 45 Null / 435 câu, tăng Null 10 điểm nhưng làm 390 câu có đáp án giảm 1 điểm thì acc tổng theo cùng rubric chỉ tăng:

`(45/435) × 10 − (390/435) × 1 ≈ 0,14 điểm %`.

Đó là lý do phải bảo vệ câu có đáp án ngay từ thiết kế. Không trộn chỉ số hai rubric để tính mức tăng chính thức.

## 8. Đánh giá cuối, ablation và cách kết luận

435 câu tầng D đã được phân tích nhiều lần. Với cơ chế thiết kế sau các phân tích đó, dùng chúng làm bộ hồi quy lịch sử,
không gọi là test hoàn toàn chưa xem. Muốn tuyên bố tổng quát hoá, cần bộ câu hỏi/hội thoại mới được khoá độc lập,
gồm cả câu có đáp án và Null gần giống, không chỉ thêm seed trên 45 câu cũ.

Đối chứng/ablation cần có:

- B2 gốc.
- Chỉ điều kiện thời gian xác định được.
- Cơ chế đầy đủ trong phạm vi đã khoá; nếu có xử lý người/trạng thái thì tách tác dụng từng thành phần.
- Kiểm trên các cặp minh hoạ mới: chỉ đổi người, ngày hoặc “dự định” thành “đã thực hiện”; ca diễn đạt gián tiếp đúng phải được giữ.

Không chạy nhiều nhánh rồi chỉ báo nhánh thắng. Chốt so sánh chính trước, khai báo số phép thử và các lần sửa luật.
Dùng McNemar từng cặp lượt và khoảng tin cậy ghép cặp theo câu/họ sự kiện, không coi các seed cùng câu là mẫu độc lập.
“Không có ý nghĩa thống kê” không chứng minh tương đương: muốn nói giữ điểm trong biên, CI phải nằm trong biên bảo vệ thích hợp.
Cỡ mẫu cần tính từ pilot; CI quá rộng thì kết luận chưa đủ bằng chứng.

Rubric gốc giữ số lịch sử, Đ6 làm chỉ số Null bổ sung/mục tiêu mới đã đăng ký. Không sửa H2 BORDERLINE, không xét lại E4.
Các ca chuyển nhãn cần người rà mù cấu hình; ưu tiên hai người độc lập.

## 9. Rủi ro và điều kiện dừng

- **Độ phủ thấp:** nhiều câu Null không có ngày/người mâu thuẫn rõ, chỉ thiếu một quan hệ; quy tắc không giải được.
- **Không có tác dụng trên generation:** chunk sai vẫn còn trong ngân sách hoặc Qwen tự suy diễn từ đoạn khác.
- **Nhận diện sai sự kiện:** ngày tin nhắn, lời thuật lại, chủ thể và trạng thái hành động bị hiểu sai.
- **Hại Multi:** đoạn không trực tiếp khớp có thể là mắt xích bắt buộc. Gặp ca chưa giải được phải giữ B2.
- **Overfit luật:** một tập regex được viết theo 20 Null dev có thể chỉ ghi nhớ benchmark. Cần log phạm vi và kiểm mới độc lập.

Không có tín hiệu offline hoặc pilot trượt cổng → giữ B2 và ghi kết quả phủ định.
Không tự động nối thêm bộ từ chối, giảm token hay sửa prompt để cứu biến thể.

## 10. Kết luận

**Trong điều kiện không fine-tune, ưu tiên kiểm offline bước xếp hạng bằng chứng theo điều kiện sự kiện, chỉ can thiệp hẹp khi
có dẫn chứng rõ và giữ B2 cho trường hợp mơ hồ.** Đây là cách thử nhắm trực tiếp hơn vào context gần giống và hạn chế nguy cơ
mất accuracy, nhưng độ phủ và hiệu quả Null đều chưa được chứng minh.

Việc tiếp theo là kiểm tính khả thi trên dev và chốt giao thức nếu có tín hiệu, chưa phải chạy benchmark lớn hoặc bật mặc định.
