# B2_NO_VECTOR (C4) so B2_FULL (C1) — dev401 seed101

Đăng ký trước DEV401-CTX-C4-001 và DEV401-QA-C4-001; đối chứng theo
HANDOFF_2WIKI_QWEN.md §2W-10 là C1/B2_FULL. C4 chọn Sources bằng BM25 top30,
giữ bảng Entities và đường xử lý đồ thị; đây không phải HYBRID_NO_GRAPH.

## Hoàn tất và kiểm soát

- Đủ401 đáp án C4 hợp lệ, trace401 Qwen/stop/seed101 không lỗi/length.
- Sau resume, đủ1.203 phiếu judge ok, không incomplete/no_majority. Không thay
  model/rubric/limiter để giải quyết RateLimitError, không coi lỗi là neither.
- Cùng dev401, gold/aliases, judge gemini-3.5-flash-lite, rubric v2/source hash,
  index/embedding/seed101/QA1024/concurrency4, prompt và Sources4000.
- Đã kiểm401 Entities, graph/vector/BM25 candidate lists giống C1; ranked C4 đúng
  BM25 list. Source extension thêm nhánh bm25/C4 được ghi source_amendment.json;
  manifest ngoài source khớp C1. Không sửa metadata hoặc kết quả cũ.
- Metrics.py kiểm hash inputs/context/answers trước tính ghép cặp. Verified
  identity không đồng nghĩa chứng nhận mọi cổng protocol đã hoàn tất.

## Kết quả

| Mean ± SD giữa ba lượt judge, % | C1/B2_FULL | C4/B2_NO_VECTOR |
|---|---:|---:|
| accurate | 36,66 ± 0,00 | 32,25 ± 0,14 |
| error | 25,27 ± 0,38 | 25,94 ± 0,25 |
| neither | 38,07 ± 0,38 | 41,81 ± 0,29 |

| Majority, số câu | C1 | C4 |
|---|---:|---:|
| accurate | 147 | 130 |
| error | 101 | 104 |
| neither | 153 | 167 |

- C4 so C1: **29 sai→đúng /46 đúng→sai, net−17 câu**, trên401 cặp hoàn chỉnh.
  Delta majority−4,239 điểm phần trăm; exact McNemar hai phía **p=0,063950**.
- Query bootstrap10.000 mẫu, seed13: CI95 delta majority **[−8,48;0,00]** điểm.
  Không dùng biên CI rời rạc/đã làm tròn để đổi kết luận của phép kiểm McNemar
  đã đăng ký; không chọn phép kiểm sau nhìn kết quả.
- Error:50 chuyển sang error/47 rời error, net+3; p=0,839214.
- Mean judge accuracy giảm4,41 điểm; khác delta majority vì cách tổng hợp khác.

| Loại câu | n | C1 majority đúng | C4 majority đúng |
|---|---:|---:|---:|
| bridge_comparison | 97 | 46 | 41 |
| comparison | 96 | 64 | 64 |
| compositional | 159 | 22 | 16 |
| inference | 49 | 15 | 9 |

Đây là mô tả của một seed; không chọn nhóm hoặc gộp các verdict làm mẫu độc lập.

## Diễn giải

Lượt này có xu hướng giảm accuracy khi bỏ vector, đồng thời nhiều neither hơn.
**Chưa xác nhận tác dụng vector bằng McNemar ở mức0,05; không kết luận tương
đương hoặc vector vô ích vì p lớn hơn0,05.** Cần thí nghiệm đầy đủ/lượt sinh lặp
trước kết luận khoa học. Ba lần judge không thay thế ba lượt sinh.

Coverage supporting-title proxy C1=672/996 (67,47%), C4=655/996 (65,76%);
số câu đủ supporting document154→143, 2 thiếu→đủ/13 đủ→thiếu. Đây không phải
semantic sufficiency hoặc accuracy. Những hạn chế annotation/alias trên dev giữ
nguyên; không loại câu hoặc sửa rubric sau nhìn điểm.

Chỉ seed101, chưa ước lượng SD giữa lượt sinh; sd0 do metrics trả cho một repeat
không được diễn giải là đo được nhiễu sinh0. Không dùng số bài báo như đối chứng
trực tiếp và không gọi C0 là MR_FULL đã tái hiện chính xác.

## Artifact và bước tiếp theo

- QA: runs/2wiki/modal/c4-dev-s101-c4/C4_s101.
- Judge: runs/2wiki/judge/c4-dev-s101-fl35-v2.
- Metrics: runs/2wiki/analysis/c1-c4-dev-s101-fl35-v2/, gồm hai metrics bundle,
  adapter manifest và comparison.json; không gọi API trong bước tổng hợp.
- Kết quả âm/chưa chắc chắn được ghi trong EXPERIMENT_HISTORY và PROJECT_STATE.

Theo HANDOFF §2W-10, ablation tiếp là **B2_NO_ENT**: bỏ bảng Entities khỏi prompt,
giữ Sources nguyên từng byte của B2_FULL/C1, lưu hash Sources để kiểm chứng;
đối chứng vẫn là C1, không phải C4. Cấu hình cần triển khai/kiểm thử trước khi
chạy, không đồng nhất với HYBRID_NO_GRAPH hay −Redge. Đối soát ngân sách trước
GPU; chưa mở test1599 hoặc chạy thêm lượt sinh trong bước tổng hợp này.
