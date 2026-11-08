# B2_NO_BM25 (C2) so B2_FULL (C1) — dev401 seed101

Đăng ký trước: DEV401-CTX-C2-001 và DEV401-QA-C2-001 trong EXPERIMENT_HISTORY.md.
Đối chứng đúng theo HANDOFF §2W-10 là **C1/B2_FULL**, không phải C0.

## Hoàn tất và điều kiện

- C2 có401 đáp án hợp lệ, trace401 Qwen/stop/seed101, không request lỗi/length.
- Judge C2 sau resume đủ1.203 phiếu ok. Bảy judge_failed và một parse_failed
  ban đầu đã được thử lại; không sửa parser/rubric hay biến lỗi thành neither.
- C1/C2 cùng401 query_id/gold/aliases, index/embedding, seed101, serving và QA1024,
  prompt, Sources4000. Manifest/cache khớp; Entities và graph/vector candidate
  lists khớp401/401. C1=RRF(vector,BM25); C2=vector thuần, bỏ thành phần BM25.
- Cùng judge gemini-3.5-flash-lite, rubric2wiki-upstream-aliases-v2/source hash.
  Đã kiểm input/context/answer hashes trước dùng metrics.py. Không mở test1599.

## Kết quả

| Mean ± SD giữa ba lượt judge, % | C1/B2_FULL | C2/B2_NO_BM25 |
|---|---:|---:|
| accurate | 36,66 ± 0,00 | 36,66 ± 0,25 |
| error | 25,27 ± 0,38 | 29,18 ± 0,25 |
| neither | 38,07 ± 0,38 | 34,16 ± 0,00 |

| Majority, số câu | C1 | C2 |
|---|---:|---:|
| accurate | 147 | 146 |
| error | 101 | 118 |
| neither | 153 | 137 |

- Accurate-vs-không-accurate theo majority: **47 lên /48 xuống, net−1 câu**;
  delta−0,249 điểm phần trăm; exact McNemar hai phía **p=1,000**.
- Query bootstrap10.000 mẫu seed13: CI95 delta majority **[−4,99;+4,24]** điểm.
- Error-vs-không-error:69 chuyển sang error /52 rời error, net+17 lỗi;
  delta+4,239 điểm; McNemar **p=0,145487**, chưa xác nhận tăng lỗi đáng tin.
- Mean judge accuracy bằng nhau không có nghĩa cùng câu đúng hoặc hai phương
  pháp tương đương. Có95 câu đổi accurate-vs-không-accurate giữa hai cấu hình.

| Loại câu | n | C1 majority đúng | C2 majority đúng |
|---|---:|---:|---:|
| bridge_comparison | 97 | 46 | 45 |
| comparison | 96 | 64 | 65 |
| compositional | 159 | 22 | 27 |
| inference | 49 | 15 | 9 |

Chỉ mô tả từng nhóm của seed101, không chọn một nhóm tăng để kết luận đóng góp.

## Diễn giải và giới hạn

Trong lượt này, bỏ BM25 không tạo chênh accuracy đáng tin so B2_FULL; quan sát
ít neither nhưng nhiều error hơn. **Chưa chứng minh BM25 cải thiện accuracy hoặc
giảm error, cũng chưa chứng minh bỏ BM25 không ảnh hưởng.** Không chỉnh weight,
top-k/prompt để cố tạo kết quả dương.

Supporting-title proxy C1=672/996 (67,47%), C2=628/996 (63,05%); đủ document154→130,
2 thiếu→đủ/26 đủ→thiếu khi C1→C2. Document presence chưa đảm bảo bằng chứng đủ.
Số liệu này cho thấy coverage và QA accuracy không nhất thiết cùng thay đổi.

Một lượt sinh mỗi cấu hình, ba lượt judge. SD giữa lượt sinh chưa được ước lượng;
trường sd0 trong metrics khi chỉ có một repeat không phải nhiễu sinh0. Các vấn
đề annotation/alias đã ghi ở báo cáo dev được giữ nguyên, không loại sau nhìn điểm.
Đây không phải tái hiện chính xác MR_FULL hoặc kết luận benchmark cuối.

## Artifact và bước tiếp

- C2 QA: runs/2wiki/modal/c2-dev-s101-c4/C2_s101.
- C2 judge: runs/2wiki/judge/c2-dev-s101-fl35-v2.
- Metrics bằng script có sẵn: runs/2wiki/analysis/c1-c2-dev-s101-fl35-v2/
  gồm C1_metrics, C2_metrics, hai adapter manifest và comparison.json.
- Manifest adapter kiểm index/split/config/judge/rubric/input hashes; verified
  ở metrics không chứng nhận mọi cổng protocol của handoff đã hoàn tất.

Theo thứ tự HANDOFF §2W-10, ablation tiếp là **B2_NO_VECTOR (BM25 thuần)**,
so với C1/B2_FULL. Handoff đánh dấu cấu hình này cần triển khai; không dùng nhầm
C3 (naive) hoặc tự truyền fusion không được hỗ trợ rồi gọi đó là BM25 thuần.
Phải hiện thực/kiểm đúng một thành phần và đăng ký trước khi chạy, đối soát budget
trước GPU. Sau các ablation mới lựa chọn lượt sinh lặp202/303 theo kế hoạch.
Giữ test1599 đóng cho đến khi phương pháp và protocol đã chốt.
