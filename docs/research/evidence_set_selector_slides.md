# Bộ chọn bằng chứng cho MiniRAG — ghi chú làm slide

Ba đóng góp trong Bảng 1 (thang cộng dồn): **+ bộ chấm F**, **+ tín hiệu ngữ nghĩa**, **+ chọn tập**.
Mỗi phần gồm: nằm ở đâu trong pipeline, vấn đề là gì, vì sao làm như vậy, bằng chứng đã có.

> **Trạng thái số liệu (11/11/2026).**
> - Số *offline*: đếm câu có **đủ bằng chứng** trong 4.000 token, 0 API.
>   - Dev200: 177 câu có nhãn Evidence. Điểm được cross-fit 5 fold theo hội thoại, β/τ chọn lồng trong fold.
>   - Non-dev: 385 câu có nhãn. Model học trên dev rồi đóng băng.
> - Số *QA*: Qwen2.5-3B, mới chạy trên dev200, **1 lượt sinh**, Gemini chấm **1 lượt**.
> - Bảng 1 chính thức đang chạy: 435 câu ngoài dev, 3 lượt sinh × 3 lượt chấm DeepSeek, Qwen và Phi.
>   Số chính thức thay các số QA dưới đây khi xong.

---

## 0. Pipeline và vị trí ba thành phần

```
Câu hỏi
  │
  ▼
[MiniRAG gốc] phân tích câu hỏi → seed entity → đồ thị → kwd2chunk         minirag/operate.py:1805
  │            (cộng điểm của mọi seed trỏ tới chunk)
  ▼
[+ source-time] đẩy chunk khớp mốc thời gian trong câu hỏi                  minirag/temporal.py:123
  │
  ▼
Danh sách chunk đã xếp hạng → lấy 45 chunk đầu (pool)
  │
  ├──► ① BỘ CHẤM F         18 đặc trưng đồ thị / thời gian / cấu trúc → p(chunk là bằng chứng)
  │
  ├──► ② TÍN HIỆU NGỮ NGHĨA  + logit cross-encoder(câu hỏi, chunk) vào cùng bộ chấm → p tốt hơn
  │
  ▼
Lấy chunk vào khối Sources, ngân sách 4.000 token
  │     gốc (A1): lấy theo thứ tự, gặp chunk đầu tiên tràn thì DỪNG               minirag/operate.py:1922
  ├──► ③ CHỌN TẬP           chọn tập chunk tối đa lợi ích / token trong 4.000 token
  ▼
Prompt rag_response (Entities + Sources) → SLM (Qwen2.5-3B / Phi-3.5-mini) → câu trả lời
```

Cả ba thành phần chỉ đổi **khối Sources**: chunk nào được đưa vào và theo thứ tự nào. Những thứ sau giữ nguyên:
- đồ thị, index, phần phân tích câu hỏi;
- bảng Entities, prompt;
- SLM, ngân sách 4.000 token.

Mã nguồn:
- Đặc trưng: [`reproduce/evidence_set/features.py`](../../reproduce/evidence_set/features.py)
- Bộ chấm: [`quick_scorer.py`](../../reproduce/evidence_set/quick_scorer.py)
- Chọn tập: [`select.py`](../../reproduce/evidence_set/select.py)
- Chạy A–Z: [`pipeline.py`](../../reproduce/evidence_set/pipeline.py), [`run_ladder.sh`](../../reproduce/evidence_set/run_ladder.sh)

---

## Vấn đề chung: bằng chứng có trong pool nhưng bị cắt mất

Đo trên dev200, 177 câu có nhãn, baseline = C0 + source-time + A1@4000:

| Đo | Số câu đủ bằng chứng | ACC (Qwen) |
|---|---:|---:|
| Baseline (Sources thực tế) | 88 / 177 | 55,4 |
| Bằng chứng **có trong 30 chunk đầu**, nếu đưa lên trước | 114 / 177 | 65,0 (24 lên / 7 xuống, p = 0,003) |
| Đưa đủ mọi bằng chứng | 177 / 177 | 83,6 |

Từ bảng này rút ra ba điều:
- **26 câu** có đủ bằng chứng trong 30 chunk đầu nhưng mất ở bước cắt 4.000 token. Lỗi nằm ở **thứ tự**, không ở việc tìm kiếm.
- Có đủ bằng chứng thì Qwen đúng khoảng 83%, nên SLM không phải nút thắt.
- Vị trí bằng chứng trong prompt gần như không ảnh hưởng (83,0 → 84,1). Cái quyết định là bằng chứng **có lọt vào** Sources hay không.

Slide nói một câu: *"MiniRAG tìm thấy bằng chứng nhưng xếp nó xuống dưới, rồi cắt mất."*

---

## ① + Bộ chấm F (đặc trưng đồ thị / thời gian / cấu trúc)

**Nằm ở đâu.**
- Sau kwd2chunk và source-time, trước bước cắt 4.000 token.
- Thay *thứ tự* của 45 chunk đầu: chấm p cho từng chunk, sắp theo p, rồi vẫn cắt bằng A1 như gốc.

**Vấn đề.**
- Điểm gốc của kwd2chunk là **tổng điểm của mọi seed** trỏ tới chunk. Mỗi câu hỏi có trung vị khoảng 105 seed, phần lớn chỉ giống câu hỏi khoảng 0,3. Vì vậy xếp hạng gần như bằng **số seed trỏ tới**, tức chunk "hub" nhắc nhiều entity sẽ lên đầu.
- Kiểm toán 09/11: chunk bằng chứng bị cắt có độ khớp *cao hơn* (0,40 so với 0,30) nhưng *ít seed trỏ tới hơn* (3 so với 5) các chunk xếp trên nó.

**Vì sao học, không chỉnh tay.**
- Đã thử 9 tín hiệu xếp hạng lại tất định và đều thất bại; hướng này đã đóng ngày 20/09 (ROADMAP). Tín hiệu tốt nhất chỉ cứu được 9/20 ca, đồng thời đẩy bằng chứng "gần giống" lên đầu ở 15–16/20 câu Null.
- Bỏ seed điểm thấp còn **làm hại** (11 lên / 24 xuống, p = 0,041), vì chính các seed đó mang bằng chứng vào pool.
- Kết luận: tín hiệu đồ thị có giá trị nhưng **không có công thức tay nào cân đúng được**. Vì vậy ta học trọng số từ nhãn Evidence trên dev.

**Cơ chế.**
- Hồi quy logistic, C = 1, không dò tham số, trên 18 đặc trưng chỉ lấy từ pipeline gốc:

  | Nhóm | Đặc trưng |
  |---|---|
  | đồ thị (10) | hạng gốc, điểm đồ thị, điểm tương đối, số seed path, số nhóm từ khoá, có phải đầu path |
  | thời gian (2) | khớp ngày, được source-time đẩy |
  | dense (2) | có trong top-30 vector, hạng vector |
  | cấu trúc hội thoại (4) | là phần nối tiếp, vị trí trong hội thoại, số chunk của hội thoại, độ dài |

- Nhãn: chunk chứa mốc `Time:` của Evidence. Nhãn chỉ dùng khi học, lúc chạy thì không đọc nhãn.
- Chạy: 0 API, khoảng 1,5 phút trên Mac.

**Bằng chứng (offline, dev, cross-fit).**

| | Đủ bằng chứng /177 | so với baseline |
|---|---:|---|
| Baseline | 88 | — |
| + F (sắp theo p → A1) | **103** | **19 lên / 4 xuống, p = 0,0026** |

- AUC trung bình các fold: 0,934.
- Bỏ từng nhóm khỏi phương pháp đầy đủ (109):

  | Bỏ nhóm | Còn |
  |---|---:|
  | cấu trúc hội thoại | 100 (−9) |
  | dense | 106 (−3) |
  | đồ thị | 107 (−2) |
  | thời gian | 109 (0) |

- **Lưu ý khi trình bày:**
  - Nhóm thời gian không thêm gì, vì source-time đã dùng thông tin này ở bước trước.
  - QA của dòng này đang chạy (dòng 3 của Bảng 1). Chưa có số ACC.

---

## ② + Tín hiệu ngữ nghĩa (cross-encoder zero-shot)

**Nằm ở đâu.**
- Cùng chỗ với ①. Đây là **đặc trưng thứ 19** của cùng bộ chấm: một logit cross-encoder.
- Nó không thay thế đồ thị và không là bước riêng.

**Vấn đề.**
- 18 đặc trưng của F **không đọc nội dung chunk**. Chúng biết chunk được đồ thị trỏ tới nhiều hay ít, gần ngày hay không, nhưng không biết chunk có *trả lời* câu hỏi không.
- Hai chunk cùng nhắc một entity thì F không phân biệt được.

**Vì sao chọn cách này.**
- Cross-encoder `ms-marco-MiniLM-L6-v2`: 22 triệu tham số, chạy cục bộ, **không fine-tune**, 0 API. Người dùng yêu cầu *nhanh mà ACC vẫn tăng*; nếu cross-encoder không đủ thì mới lên model to hơn.
- Ghép vào **cùng** hồi quy logistic thay vì dùng CE một mình. Lý do: hai nguồn tín hiệu bổ sung cho nhau. Đồ thị biết *chunk nào liên quan tới entity của câu hỏi*; CE biết *chunk nào nói đúng điều được hỏi*.

**Bằng chứng (offline, dev, cross-fit).**

| | Đủ bằng chứng /177 | so với baseline | AUC |
|---|---:|---|---:|
| CE một mình | 103 | 25 lên / **10 xuống**, p = 0,017 | 0,942 |
| F một mình | 103 | 19 lên / 4 xuống, p = 0,0026 | 0,934 |
| **CE + F** (sắp theo p → A1) | **110** | **25 lên / 3 xuống, p = 2,7·10⁻⁵** | **0,961** |
| Trần (bằng chứng trong pool 45) | 117 | — | — |

- Hai tín hiệu bù nhau:
  - CE một mình cứu nhiều câu nhưng cũng làm mất 10 câu.
  - Ghép với F thì chỉ còn mất 3 câu.
  - Ghép lại đạt 110/117, tức thu hồi 22/29 phần chênh giữa baseline và trần.
- Bỏ từng cái khỏi phương pháp đầy đủ (109):
  - bỏ CE còn 98;
  - bỏ 18 đặc trưng còn 102.

  **Cả hai đều cần.** Dòng "bỏ đặc trưng" là bằng chứng phương pháp *không chỉ là cross-encoder kiểu RECOMP*.
- Non-dev, offline, model đóng băng: baseline 196 → **238** / 385.
- QA dev200 (1 lượt): ACC 57,5 → 63,5 (31 lên / 19 xuống, **p = 0,12, chưa có ý nghĩa**). ERR 26,0 → 28,5, **tăng nhẹ**.
  - Cách hiểu: sắp xếp tốt hơn giúp Qwen trả lời nhiều hơn (neither 16,5 → 8,0), nhưng không phải câu nào cũng đúng.
  - Đây là lý do cần thành phần ③.

---

## ③ + Chọn tập theo ngân sách (phương pháp đầy đủ)

**Nằm ở đâu.**
- Thay bước cắt A1@4000 trong khối Sources.
- Dùng **đúng điểm p** của ②. Điểm không đổi, chỉ đổi *cách lấy chunk*.

**Vấn đề: A1 lấy theo thứ tự và dừng ở chunk đầu tiên tràn ngân sách.**

Kích thước chunk rất lệch:

| Chỉ số | Số token |
|---|---:|
| trung vị | 274 |
| 10% nhỏ nhất | ≤ 127 |
| 10% lớn nhất | ≥ 1.200 |

Có 82/514 chunk dài khoảng 1.200 token. Một chunk dài nằm ở vị trí 6 là đủ chặn mọi chunk ngắn phía sau.

| | Token bỏ trống (trung vị) | Số chunk | Số hội thoại |
|---|---:|---:|---:|
| Baseline (A1) | 311 | 6 | 6 |
| CE + F sắp theo p (A1) | 400 | 6 | 6 |
| **CE + F + chọn tập** | **46** | **11** | **10,5** |

Ngoài ra, nhiều chunk liền nhau của **cùng một hội thoại** thường lặp nội dung và chiếm ngân sách.

**Vì sao làm như vậy.**
- Đây là bài toán *chọn tập có ngân sách* (knapsack / maximum coverage), không phải bài toán sắp xếp.
- Thuật toán tham lam theo **lợi ích biên trên mỗi token** trên một hàm submodular cho đảm bảo xấp xỉ chuẩn.
- Hàm này không cần nhãn lúc chạy, và mọi khía cạnh đều lấy từ pipeline gốc.

**Cơ chế.**
```
F(S) = Σ_hội thoại d [1 − Π_{c∈S, doc(c)=d} (1 − p_c)]          lợi ích giảm dần trong cùng hội thoại
     + β Σ_khía cạnh f  w_f [1 − Π_{c∈S hỗ trợ f} (1 − p_c)]     phủ từ khoá / mốc ngày của câu hỏi
```
- Mỗi bước thêm chunk có (F(S ∪ c) − F(S)) / token(c) lớn nhất.
- Chunk **không vừa thì bỏ qua và xét tiếp**, khác A1 vốn dừng hẳn.
- β = 2, τ = 0, chọn lồng trong fold trên dev rồi đóng băng cho non-dev.

**Bằng chứng.**
- Offline: số câu đủ bằng chứng **không đổi** (110 → 109). Chọn tập không thêm chunk bằng chứng *chính*. Nó lấp ngân sách bằng chunk bổ trợ (6 → 11 chunk) và trải ra nhiều hội thoại hơn.
- Non-dev offline: 238 → **241** / 385.
- **QA dev200 (1 lượt sinh, Gemini 1 lượt):**

  | | ACC | ERR | Neither |
  |---|---:|---:|---:|
  | Baseline | 57,5 | 26,0 | 16,5 |
  | + CE + F, sắp theo p | 63,5 | 28,5 | 8,0 |
  | **+ chọn tập (đầy đủ)** | **66,0** | **24,5** | 9,5 |

  - So với baseline: ACC 35 lên / 18 xuống, **p = 0,027**. Đây là kết quả QA *duy nhất* có ý nghĩa đến giờ.
  - Theo loại câu:

    | Loại | ACC baseline → đầy đủ | McNemar |
    |---|---|---|
    | Single | 59,1 → 68,6 | 28 lên / 13 xuống, p = 0,028 |
    | Multi | 33,3 → 57,1 | 6 / 1, n = 21, chưa đủ |
    | Null | 70 → 55 | 1 / 4, n = 20 |

  - So với sắp theo p (đóng góp riêng của chọn tập):
    - ACC 18 lên / 13 xuống, p = 0,47.
    - ERR: sửa 21 lỗi, gây 13 lỗi mới, p = 0,23. Chiều đúng nhưng **chưa có ý nghĩa**.
- Thành phần phủ khía cạnh (β) chỉ thêm +2 câu offline (107 → 109). Nên trình bày như một phần nhỏ, không phải điểm chính.

**Lưu ý khi trình bày.**
- Bằng chứng QA hiện có mới là 1 lượt sinh trên dev, tập đã bị xem nhiều lần. CLAUDE.md quy định phải lặp lượt.
- Null giảm 70 → 55 (n = 20), cần theo dõi ở Bảng 1.
- Chỉ được viết "chọn tập cải thiện ACC" khi Bảng 1 (435 câu, 3 lượt sinh) xác nhận.

---

## Khác RECOMP ở đâu (slide "không phải sao chép")

| | RECOMP (extractive) | Phương pháp này |
|---|---|---|
| Đơn vị | câu | **nguyên chunk hội thoại** (giữ mốc `Time:` và ngữ cảnh người nói) |
| Tín hiệu học | likelihood của LM | **nhãn Evidence** + **đặc trưng đồ thị / thời gian / cấu trúc hội thoại** |
| Bộ chấm | encoder fine-tune | cross-encoder **zero-shot** + hồi quy logistic, không fine-tune |
| Cách lấy | top-k câu | **chọn tập theo ngân sách token**, lợi ích giảm dần theo hội thoại, phủ khía cạnh |
| Bằng chứng tách bạch | — | bỏ 18 đặc trưng đồ thị: 109 → 102; bỏ CE: 109 → 98 |

---

## Bảng 1 (đang chạy) và Bảng 2 (đề xuất)

**Bảng 1, cộng dồn:** 435 câu ngoài dev, 3 lượt sinh × 3 lượt chấm DeepSeek, Qwen2.5-3B và Phi-3.5-mini. Mỗi SLM dùng index do chính nó dựng.

| # | Cấu hình | Đóng góp riêng đo bằng |
|---|---|---|
| 1 | C0 (MiniRAG gốc) | — |
| 2 | C0 + source-time *(baseline)* | dòng 2 so với dòng 1 |
| 3 | … + bộ chấm F | dòng 3 so với dòng 2 |
| 4 | … + tín hiệu ngữ nghĩa | dòng 4 so với dòng 3 |
| 5 | … + chọn tập *(đầy đủ)* | dòng 5 so với dòng 4 |

Mỗi ô báo ACC / ERR / Neither ± độ lệch giữa các lượt sinh, kèm McNemar (b lên / c xuống, p) cho từng lượt. Một thành phần chỉ được gọi là đóng góp khi cùng chiều qua cả 3 lượt.

**Bảng 2, bỏ từng cái khỏi phương pháp đầy đủ** (đề xuất). Bảng này xử lý nhược điểm "thứ tự cộng ảnh hưởng kết quả" của Bảng 1.

| Cấu hình | Offline đã có |
|---|---:|
| Đầy đủ | 109 |
| − tín hiệu ngữ nghĩa | 98 |
| − 18 đặc trưng đồ thị / thời gian / cấu trúc | 102 |
| − chọn tập (= dòng 4) | 110 |

---

## Gợi ý thứ tự slide

1. **Vấn đề:** MiniRAG tìm thấy bằng chứng nhưng cắt mất. Có đủ bằng chứng thì Qwen đúng 83,6%, baseline chỉ 55,4%.
2. **Pipeline:** sơ đồ mục 0, ba ô màu ①②③.
3. **① Bộ chấm F:** điểm gốc = đếm seed (hub); chỉnh tay đều thất bại; học từ nhãn: 88 → 103.
4. **② Tín hiệu ngữ nghĩa:** F không đọc nội dung; ghép CE: 103 → 110; bỏ cái nào cũng tụt.
5. **③ Chọn tập:** A1 dừng ở chunk tràn; ngân sách bỏ trống 311 → 46 token, 6 → 11 chunk; ACC 57,5 → 66,0 (p = 0,027).
6. **Khác RECOMP.**
7. **Bảng 1 + Bảng 2** (điền số chính thức khi xong).
8. **Giới hạn:** Null; số dev mới 1 lượt; Multi n nhỏ.

## Nguồn số liệu

| Nội dung | File |
|---|---|
| Offline dev | `review/evidence_set_20261111/offline_eval_dev200.json` |
| Bỏ từng nhóm | `review/evidence_set_20261111/offline_eval_dev200_ablation.json` |
| AUC | `review/evidence_set_20261111/scores/quick_scorer_report.json` |
| QA dev200 | `review/evidence_set_20261111/qa_dev200/results.json` |
| Non-dev offline | `review/evidence_set_20261111/qa_nondev435/build.json` |
| Trần pool / oracle | `review/oracle_headroom_20261111/` |
| Bảng 1 khi xong | `review/evidence_set_20261111/qa_nondev435/ladder/REPORT.md` (Qwen), `review/evidence_set_20261111/phi/qa_nondev435/ladder/REPORT.md` (Phi) |
