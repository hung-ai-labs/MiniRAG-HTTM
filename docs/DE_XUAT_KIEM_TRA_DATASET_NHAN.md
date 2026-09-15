# Đề xuất kiểm tra dataset, nhãn và giám khảo

> Viết 15/09/2026, sau kiểm toán nhóm Null (commit `4688308`). Script: `reproduce/null_audit/`; kết quả: `logs/null_audit/`.
> Bối cảnh đầy đủ: [`ROADMAP.md`](../ROADMAP.md), Limitations của V3, mục 8. Kết quả hiện tại: [`KET_QUA_HIEN_TAI.md`](KET_QUA_HIEN_TAI.md).
>
> Đây là **đề xuất**. Việc nào muốn chạy phải được nhóm duyệt và **đăng ký trước giao thức** (mẫu ở mục 8) trước khi đọc dữ liệu.

## 1. Vì sao cần kiểm tra

- Mọi cải tiến truy hồi đưa thêm văn bản liên quan vào context đều làm **acc tổng tăng nhưng nhóm Null giảm**. Chiều giảm lặp lại ở
  mọi lượt, dù từng lượt chưa có ý nghĩa thống kê.
- Cần tách phần nào là **hành vi thật của model**, phần nào là **lỗi thước đo** (nhãn sai, giám khảo chấm lệch rubric).
- Tầng D đang chạy có cổng E4 về nhóm Null. Trước khi viết bài phải hiểu thước đo Null tin được tới đâu.

| Qwen2.5-3B, 637 câu | acc tổng | neither tổng | Null acc | Null err |
|---|---:|---:|---:|---:|
| Baseline | 51,02 | 21,31 | 70,26 | 17,44 |
| V3, trung bình 3 lượt sinh | 60,72 | 14,00 | 61,54 | 25,30 |
| Vector thuần | 65,20 | 9,76 | 62,56 | 30,77 |

Trên dev 200 (20 câu Null), Null của V3 đông lạnh là 65,0; B1 và B2 cùng là 55,0.

## 2. Kiểm toán ngày 15/09 đã tìm được gì

Chạy offline, không gọi API, không dùng dữ liệu tầng D.

| Phát hiện | Số liệu | Nguồn |
|---|---|---|
| Đáp án vàng của nhóm Null | cả 65 câu đều là **"Insufficient information"** | `dataset/LiHua-World/qa/query_set.csv` |
| Câu Null từng bị chấm `error` (baseline, V3 × 3, vector thuần; dev: V3, B1, B2) | **32/65**; 21 câu chỉ sai ở lượt cải tiến | `logs/null_audit/taxonomy.txt` |
| Kiểu lỗi chính | trả lời tự tin, **ghép tiền đề sai vào một sự kiện có thật gần đó** | như trên |
| Câu trả lời có rào đón vẫn bị chấm `error` | 5 câu; 13/100 lượt `error` | như trên |
| **Nhãn Null sai, đã đọc chunk gốc** | **3 câu** (bảng dưới) | `logs/null_audit/verify_labels.txt` |
| Tín hiệu "độ phủ tiền đề" (dev) | AUC 0,85 với context B2 — tín hiệu cũ tốt nhất 0,648 | `logs/null_audit/premise_signal_dev.txt` |
| Dùng tín hiệu đó để sửa (dev, cận trên lạc quan) | cổng từ chối: net = 0 · cắt context: −2 đến +1 câu / 200 | `logs/null_audit/cut_oracle_dev.txt` |

**Ba câu Null có đáp án trong corpus:**

| Câu hỏi (rút gọn) | Chunk | Trích |
|---|---|---|
| Kích thước cửa sổ trước khi lắp rèm | `20260928_10:00` | "The window is 150 cm wide and 120 cm high" |
| Vị bánh mới Li Hua thích ở sự kiện kỷ niệm của tiệm bánh | `20260418_15:00` | "I really enjoyed the new pastries, especially that raspberry tart" — câu hỏi nói "bread", corpus nói "pastries" |
| Phản hồi của Yuriko về demo website sáng thứ Năm | `20260312_16:00` | "I absolutely loved the demo website you showed me this morning" + ý tưởng mục community outreach |

Câu cửa sổ baseline không bị chấm sai, nhưng **mọi lượt cải tiến đều bị chấm sai**: truy hồi tốt hơn tìm ra đáp án thật và bị phạt.

**Độ nhạy của Null err** (phán quyết đa số 3 lượt chấm; chỉ để kiểm thước đo, **không thay số chính thức**):

| | Chính thức | Bỏ 3 câu nhãn sai | Bỏ 3 câu + tính câu rào đón là `neither` |
|---|---:|---:|---:|
| Baseline | 16,9 | 14,5 | 11,3 |
| V3, trung bình 3 lượt | 24,6 | 21,5 | 17,7 |
| Vector thuần | 29,2 | 25,8 | 25,8 |

**Kết luận:** nhãn và giám khảo chỉ giải thích khoảng 1 điểm của mức chênh; **phần lớn mức giảm Null là hành vi thật.**

## 3. Đề xuất kiểm tra dataset và nhãn

### K1 — Rà tay toàn bộ 65 câu Null · ưu tiên cao

**Vì sao.** Ba câu nhãn sai mới chỉ tìm được trong số câu *bị chấm sai*. Câu Null có đáp án mà model từ chối thì vẫn được chấm
`accurate`, tức cộng điểm oan cho cấu hình ít chịu trả lời, thường là baseline. Chưa rà thì chưa biết bộ Null thật sự có bao
nhiêu câu vô nghiệm.

**Cách làm.**
1. Chuẩn bị phiếu cho mỗi câu: 10 chunk khớp nhất theo BM25 trên câu hỏi, 10 chunk theo vector, và 2 câu khớp nhất trong mỗi chunk.
   Mở rộng từ `reproduce/null_audit/taxonomy.py`.
2. Hai người đọc **độc lập**, **không thấy câu trả lời hay phán quyết của cấu hình nào**. Mỗi câu gán một nhãn: `KHÔNG CÓ` /
   `CÓ ĐỦ` / `CÓ MỘT PHẦN hoặc MƠ HỒ`, kèm chunk id và trích dẫn.
3. Đối chiếu hai người, tính Cohen's κ; câu bất đồng do người thứ ba quyết.
4. Ghi `logs/null_audit/label_audit_null.csv`.

**Dùng kết quả thế nào.** Bảng độ nhạy "bỏ câu `CÓ ĐỦ`" cho **mọi cấu hình cùng lúc**, và đưa danh sách câu nhãn sai vào
Limitations như nhiễu của benchmark. Không đổi số chính thức.

**Công:** khoảng 3–4 giờ mỗi người.

### K2 — Rà mẫu đáp án vàng của câu có đáp án

**Vì sao.** Giám khảo so với đáp án vàng; đáp án vàng sai hoặc thiếu làm nhiễu acc của mọi cấu hình. Cột Evidence đã được dùng để
tự động tìm chunk vàng theo mốc thời gian, nên đọc chunk là kiểm được luôn.

**Cách làm.** Rút ngẫu nhiên có seed 60 câu (40 Single, 20 Multi) từ 570 câu có đáp án. Đọc chunk theo Evidence và gán đáp án vàng:
`ĐÚNG` / `SAI` / `THIẾU` / `MƠ HỒ`. Với câu Multi, ghi thêm: có thật cần từ 2 chunk trở lên không. Báo dev và ngoài dev riêng.

**Công:** khoảng 3 giờ.

### K3 — Kiểm nhãn loại câu (Single / Multi)

**Vì sao.** Mọi bảng đều tách theo loại câu. Câu Multi thực chất chỉ cần 1 chunk, hoặc câu Single cần 2 chunk, sẽ làm lệch kết luận
theo nhóm. Kết quả Multi của V3 đã không lặp lại được giữa các lượt.

**Cách làm.** Trên dev, dùng số chunk vàng trong `logs/diag_path2chunk.jsonl`: đếm câu Multi có đúng 1 chunk vàng và câu Single có
từ 2 chunk vàng trở lên, rồi đọc tay các trường hợp lệch.

**Công:** khoảng 1 giờ.

### K4 — Ghi nhận các vấn đề dữ liệu đã biết

- 637 dòng nhưng chỉ 635 câu phân biệt (2 cặp trùng văn bản, 1 cặp nằm ngoài dev); đã xử lý bằng trọng số 1/2 theo luật mẫu số.
- Mọi câu Null dùng chung một đáp án vàng, nên giám khảo phải tự suy "từ chối = đúng" (xem G1).
- Câu hỏi dùng từ lệch corpus ("bread" so với "pastries") — xếp vào nhãn `MƠ HỒ` ở K1.

## 4. Đề xuất kiểm tra giám khảo

### G1 — Độ khớp giữa giám khảo và người trên câu Null · ưu tiên cao

**Vì sao.** Rubric có ba nhãn: `accurate` = truyền đạt đáp án vàng, `error` = khẳng định trái đáp án vàng **mà không thừa nhận
không chắc**, `neither` = nói không biết hoặc từ chối. Với câu Null, "không có thông tin" vừa là đáp án vàng vừa là "nói không biết",
nên cùng một kiểu câu có lúc được chấm `accurate`, có lúc `neither`. Thêm vào đó, 5 câu có rào đón vẫn bị chấm `error`.

**Cách làm.** Rút 80 câu trả lời cho câu Null, phân tầng theo có / không rào đón × cấu hình (baseline, V3, vector thuần, B2). Người
chấm theo đúng rubric, **mù cấu hình và mù phán quyết Gemini**. Lập bảng nhầm lẫn người × Gemini và tính κ. Nên làm sau K1 để
dùng nhãn đã rà.

**Công:** khoảng 2 giờ.

### G2 — Giám khảo dễ dãi với chi tiết sai

**Vì sao.** Trong pilot V5e, 13/40 câu được chấm `accurate` vẫn chứa ngày, thứ tự hoặc người nói mâu thuẫn với Sources. Mẫu pilot
có chọn lọc, nên chưa phải ước lượng cho toàn bộ.

**Cách làm.** Rút ngẫu nhiên 60 câu `accurate` của V3 và B2 trên dev. Người đối chiếu từng chi tiết với chunk vàng, ước lượng tỉ lệ
"đúng đáp án nhưng sai chi tiết" kèm khoảng tin cậy.

**Công:** khoảng 3 giờ.

### G3 — Giám khảo thứ hai · cần duyệt chi phí

**Vì sao.** Bài báo chấm bằng GPT-4o, nhóm chấm bằng Gemini Flash-Lite; khác giám khảo là một nguồn lệch khi so với bài báo.

**Cách làm.** Chấm lại một mẫu cố định (ví dụ 200 câu × 3 cấu hình) bằng một model khác, chỉ báo độ khớp giữa hai giám khảo, không
thay số chính thức. **Có gọi API trả phí, nên phải hỏi nhóm trước** ([`CLAUDE.md`](../CLAUDE.md) §1).

## 5. Các hướng sửa Null đã đánh giá

| Hướng | Kết quả | Trạng thái |
|---|---|---|
| Cổng từ chối theo độ tương đồng truy hồi (A3) | AUC ≤ 0,648; mọi ngưỡng đều làm giảm acc | ⛔ đóng |
| Kiểm dấu vết câu trả lời, quan hệ đồ thị, đặc trưng MiniLM (V5a–V5c) | AUC khoảng 0,5; kiểm quan hệ chặn nhầm ≥ 63% câu đúng | ⛔ đóng |
| NLI nhỏ HHEM (V5d) | chặn nhầm 47,6% câu đúng | ⛔ đóng |
| Qwen tự kiểm chứng sau khi sinh (V5e) | chặn nhầm 92,5% câu đúng; AUC 0,448 | ⛔ đóng |
| **Cổng từ chối theo độ phủ tiền đề** (mới, 15/09) | AUC 0,85, nhưng net oracle = 0 ở mọi ngưỡng | ⛔ không làm |
| **Cắt context khi độ phủ tiền đề thấp** (mới, 15/09) | net lạc quan −2 đến +1 câu trên dev 200 (B2) | ⛔ không làm |
| Sửa prompt kiểu "hãy nói không biết" | cải tiến giả bị cấm ([`CLAUDE.md`](../CLAUDE.md) §1b) | ⛔ không làm |
| Fine-tune generator để biết từ chối | chưa duyệt; rủi ro rò nhãn từ bộ đánh giá | ⏸ chưa làm |
| Biểu diễn cấp sự kiện (ai, khi nào, trong cuộc trò chuyện nào) để kiểm tiền đề | cần đổi cách index; đồ thị hiện tại vô hướng, không có loại quan hệ (V5b) | 🔭 chỉ ghi Future work |

**Vì sao chưa có cách nào khả thi.** Câu Null có độ phủ tiền đề thấp thì model đã tự từ chối đúng. Câu Null model trả lời sai lại có
tiền đề **gần đúng gần như trọn vẹn**: đúng người, đúng loại sự kiện, chỉ sai một chi tiết như ngày, dịp, hay người nói. Mọi tín
hiệu đo độ khớp hay độ phủ đều thấy những câu này giống câu có đáp án. Muốn bắt chúng phải kiểm được *sự kiện cụ thể* mà câu hỏi
nhắc tới có tồn tại không, và biểu diễn hiện tại không làm được việc đó.

## 6. Nguyên tắc khi chạy các kiểm tra

- **Đăng ký trước giao thức** (mẫu, seed, định nghĩa nhãn, cách tính, cách dùng kết quả) rồi mới đọc dữ liệu.
- **Người gán nhãn mù cấu hình và mù phán quyết** của giám khảo.
- Kết quả **chỉ dùng cho phân tích độ nhạy và Limitations**, áp cùng lúc cho mọi cấu hình. Không đổi số chính thức, không chỉnh
  cổng, không dùng để chọn biến thể.
- **Không đụng dữ liệu tầng D** cho tới khi phân tích tầng D chạy xong.
- Kiểm nhãn được làm trên cả 637 câu; nhưng **thiết kế cơ chế chỉ dùng dev**, không dùng 435 câu ngoài dev.

## 7. Thứ tự đề xuất

| # | Việc | Công | Gọi API trả phí | Phụ thuộc |
|---|---|---|---|---|
| 1 | **K1** — rà tay 65 câu Null | 6–8 giờ người (2 người) | không | — |
| 2 | **G1** — khớp giám khảo–người trên câu Null | 2 giờ | không | nên sau K1 |
| 3 | **K3** — nhãn loại câu (dev) | 1 giờ | không | — |
| 4 | **K2** — mẫu 60 đáp án vàng | 3 giờ | không | — |
| 5 | **G2** — chi tiết sai trong câu được chấm đúng | 3 giờ | không | — |
| 6 | **G3** — giám khảo thứ hai | tuỳ cỡ mẫu | **có** | cần nhóm duyệt |

Nếu chỉ có thời gian cho hai việc: **K1 rồi G1**. Hai việc này quyết định con số Null trong bài có tin được hay không.

**Cách viết vào bài (dự thảo):** *"Các cải tiến truy hồi tăng accuracy tổng nhưng làm nhóm Null giảm theo cùng một chiều ở mọi lượt
(chưa có ý nghĩa thống kê ở từng lượt). Kiểm toán cho thấy 3/65 câu Null thực ra có đáp án trong corpus và một số câu trả lời có
rào đón bị chấm sai, nhưng hai nguồn này chỉ giải thích khoảng 1 điểm; phần còn lại là mô hình 3B trả lời tự tin khi context chứa sự
kiện gần giống tiền đề của câu hỏi."*

## 8. Mẫu đăng ký trước giao thức

```
Việc: K1 / K2 / K3 / G1 / G2 / G3
Ngày chốt:
Mẫu (danh sách câu, hoặc cách rút + seed):
Người gán nhãn (≥ 2) và cách làm mù:
Nhãn và định nghĩa từng nhãn:
Cách tính (κ, tỉ lệ, khoảng tin cậy):
Cách dùng kết quả (chỉ độ nhạy / Limitations — không đổi số chính thức):
File kết quả:
```
