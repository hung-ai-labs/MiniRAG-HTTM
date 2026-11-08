# C0–C1 trên dev401, seed101 — 01/11/2026

Đăng ký trước: DEV401-QA-C1-001 và DEV401-CTX-C1-001 trong
[EXPERIMENT_HISTORY.md](EXPERIMENT_HISTORY.md). C0=GROUP_BASE, C1=B2_FULL
theo [HANDOFF §1.5](HANDOFF_2WIKI_QWEN.md). C1 là cấu hình dự án có sẵn,
không phải phương pháp mới được chứng minh trong đợt này.

**Kết luận:** chưa có bằng chứng C1 cải thiện accuracy ở lượt sinh seed101 này.
Không kết luận hai cấu hình tương đương chỉ vì p lớn.

## Kết quả judge

Cả hai cấu hình đều có401 đáp án và đủ1.203 phiếu hợp lệ (401×3), không incomplete,
no_majority hoặc phiếu lỗi còn tồn tại. Cùng câu hỏi/gold/aliases, cùng judge
`gemini-3.5-flash-lite`, source và rubric `2wiki-upstream-aliases-v2` cùng hash.
Qwen/index/embedding/seed và điều kiện QA khớp; không dùng test1599.

| Mean ± SD giữa ba lượt judge, % | C0 | C1 |
|---|---:|---:|
| accurate | 35,33 ± 0,29 | 36,66 ± 0,00 |
| error | 25,02 ± 0,29 | 25,27 ± 0,38 |
| neither | 39,65 ± 0,00 | 38,07 ± 0,38 |

Chênh accuracy trung bình judge là+1,33 điểm phần trăm. SD0 ở cột accurate C1
chỉ cho biết ba lượt có cùng tổng số câu accurate; không chứng minh từng câu
được chấm giống nhau, judge đúng, hoặc nhiễu sinh bằng0.

## So sánh ghép cặp theo majority từng câu

| Majority, số câu | C0 | C1 |
|---|---:|---:|
| accurate | 142 | 147 |
| error | 99 | 101 |
| neither | 160 | 153 |

- Accurate-vs-không-accurate: **51 lên /46 xuống, net+5**, trên401 cặp đầy đủ;
  delta+1,247 điểm phần trăm, McNemar exact hai phía **p=0,684859**.
- Query bootstrap10.000 mẫu, seed13: CI95 delta majority **[−3,49;+5,99]** điểm
  phần trăm, lấy mẫu theo query, không coi1.203 verdict là1.203 câu độc lập.
- Error-vs-không-error: 57 câu chuyển sang error /55 câu rời error, net+2;
  McNemar p=0,924775. Từ “lên” ở biến error nghĩa là thêm lỗi, không phải tốt hơn.
- Delta majority khác delta mean judge vì hai phép tổng hợp khác nhau; không
  ghép+1,33 với b/c51/46 như thể cùng một thống kê.

| Loại câu | n | C0 majority đúng | C1 majority đúng |
|---|---:|---:|---:|
| bridge_comparison | 97 | 46 | 46 |
| comparison | 96 | 66 | 64 |
| compositional | 159 | 20 | 22 |
| inference | 49 | 10 | 15 |

Các nhóm chỉ mô tả lượt này, chưa có xác nhận nhiều lượt và không dùng để chọn
một tập con báo kết quả dương. Ví dụ bridge_comparison có neither21→11 nhưng
error30→40, accurate vẫn46: trả lời nhiều hơn không đồng nghĩa đúng nhiều hơn.

## Đối chiếu với retrieval và giới hạn

Supporting-title recall proxy tăng60,34%→67,47%, đủ tài liệu137→154
([báo cáo context](C1_DEV401_CONTEXT_REVIEW.md)); mức tăng proxy chưa chuyển
thành cải thiện accuracy đáng tin trong lượt này. Không quy toàn bộ lỗi cho
retrieval: đã thấy lỗi sử dụng bằng chứng và annotation trong dev.

Đây chỉ **một lượt sinh** mỗi cấu hình. Ba lượt judge không thay thế ba lượt
sinh. Trường `generation_sd_delta_pp.sd=0` do metrics.py trả cho một repeat
không được diễn giải thành đo được SD sinh0; độ biến thiên giữa lượt sinh
**chưa được ước lượng**. Provenance verified trong metrics chỉ nói adapter
identity/index/split/judge/rubric khớp, không chứng nhận mọi cổng handoff đã xong.

Chưa hoàn thành pilot C1 riêng50–100 câu trước toàn dev; đây là lệch trình tự
đã ghi nhận. Chưa đủ ablation B2_NO_BM25/NO_VECTOR/NO_ENT/HYBRID_NO_GRAPH,
chưa xác nhận seed202/303 hoặc kiểm chéo độc lập của người khác. Không coi
C0 là tái hiện chính xác MR_FULL của bài báo. Không dùng kết quả này để mở test.

## Artifact và bước tiếp theo

### Chẩn đoán offline97 câu đổi accurate-vs-không-accurate

Đã ghép tự động toàn bộ51 câu lên và46 câu xuống với thay đổi supporting titles
trong context; đây là liên hệ mô tả, chưa phải rà thủ công/nhãn nhân quả97 câu.

| Thay đổi số supporting document tìm được | 51 câu lên | 46 câu xuống |
|---|---:|---:|
| Nhiều hơn | 18 | 6 |
| Bằng nhau | 30 | 34 |
| Ít hơn | 3 | 6 |

Tập supporting titles giữ nguyên ở29/51 câu lên và33/46 câu xuống (62/97 câu).
Không quy các ca này hoàn toàn cho nhiễu sinh: thứ tự Sources và distractors vẫn
khác giữa C0/C1. Tuy vậy, số tài liệu gold đơn thuần không giải thích được mọi
đổi kết quả. Không dùng phép đếm này để tuyên bố BM25 có ích hoặc có hại.

Ví dụ đã đối chiếu đầy đủ hai đoạn hỗ trợ: `03fbfaa80bb011ebab90acde48001122`,
hỏi ông nội Sharaf al-Dawla. Cả hai Sources cùng chứa Sharaf là con 'Adud,
và 'Adud là con Rukn al-Dawla. C0 trả đúng Rukn, C1 nói không xác định được.
Đây là một ca không sử dụng bằng chứng sẵn có; không phải mất supporting doc.
Không sửa judge hoặc prompt để cứu riêng ví dụ này.

File số đếm: `runs/2wiki/analysis/c0-c1-dev-s101-fl35-v2/flip_diagnostics.json`;
đáp án/context tham chiếu trong paired_answers và hai run QA nêu dưới.

- QA C1: `runs/2wiki/analysis/c1-context-dev401-s101/C1_s101/`.
- Judge C1: `runs/2wiki/judge/c1-dev-s101-fl35-v2/`.
- Metrics đã tính bằng `reproduce/research/metrics.py` có sẵn:
  `runs/2wiki/analysis/c0-c1-dev-s101-fl35-v2/{C0_metrics,C1_metrics,comparison.json}`.
- Hai adapter manifest lưu hash cấu hình/index/split và nguồn QA/judge;
  `paired_answers.jsonl` lưu401 cặp đáp án, nhãn và gained/lost supporting titles.
- QA C1 đã kết thúc exit0 sau641,02 giây; snapshot Billing tháng11 sau QA
  metered0,28000084 USD/billed0, tổng hai tháng đã đối soát khoảng18,65 USD.
  Snapshot không bảo đảm không có bill trễ hoặc workload khác.

Bước offline tiếp theo: rà51 câu lên và46 câu xuống để xác định việc thay
Sources, lỗi sinh và judge/annotation ảnh hưởng ra sao. Sau đó theo P4 của
handoff, ablation đầu tiên là B2_NO_BM25 (C2 vector thuần) để tách vai trò BM25,
giữ cùng mẫu/điều kiện và đối chiếu B2_FULL. Mỗi lượt GPU cần đăng ký/đối soát
ngân sách trước; không chạy lại hay tinh chỉnh top-k/prompt chỉ vì điểm tăng ít.
Chỉ mở test1599 sau khi phương pháp và protocol đã đóng băng.
