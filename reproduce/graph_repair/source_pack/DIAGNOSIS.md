# Người 2 — chẩn đoán L3/L2 (B1)

Viết 09/11/2026. Chỉ đọc log `logs/graph_repair/p_pack/c0_diag/diag.jsonl` (C0, 180 câu dev có Evidence, hồi quy 180/180) và
`logs/diag_path2chunk.jsonl` (nhãn đáp án — **chỉ để chẩn đoán/đánh giá, không vào cơ chế**). Tái tạo: 

```powershell
$env:TIKTOKEN_CACHE_DIR="$PWD\data-gym-cache"
.\.venv\Scripts\python.exe -X utf8 -I reproduce\graph_repair\source_pack\diagnose_pack.py
```

Đầu ra: `logs/graph_repair/p_pack/diagnosis.json` (+ `diagnosis_cases.json`). Script tái dựng A1 từ `graph_ids` rồi khẳng định
bằng `assert` rằng nó bằng đúng `chunk_ids` của log ở 180/180 câu, và tái hiện các số của giai đoạn 1: **75/180 câu đủ**,
chunk đáp án OK 96 / L3 33 (31 câu) / L2 6 / L1+L0 72.

## Kết luận một đoạn

Khoảng trống thật: nếu *biết* đáp án thì chỉ xếp lại 30 chunk đã có cũng cho **104/180 câu đủ** (hiện 75; 109 nếu dùng mọi
ứng viên). Nhưng **không tín hiệu thuần đồ thị nào tôi thử tách được đáp án khỏi nhiễu**: tốt nhất lên 6–8 câu, xuống 4–6 câu
(+2 câu ròng, không có ý nghĩa thống kê). Ngân sách bị lãng phí ít hơn tưởng (trung vị 456 token) và chunk đáp án bị mất
phần lớn là chunk **dài** — đúng loại mà mọi cách "tính theo token" phạt nặng. Hai hướng gợi ý của README: *phủ từ khoá* **không
được B1 ủng hộ**; *giá trị trên token* ủng hộ một phần, với rủi ro rõ.

## Q1 — Ngân sách bị lãng phí bao nhiêu?

| | Giá trị |
|---|---:|
| Token còn trống khi A1 dừng, 31 câu L3 (trung vị; min–max) | **456** (12–1.169) |
| Cùng chỉ số, 75 câu đủ đáp án / cả 180 câu | 302 / 308 |
| Chunk làm tràn (trung vị) | 1.037 token |
| Câu L3 mà chunk đáp án bị mất **vừa** phần trống | **8 / 31** |
| Chunk đáp án L3: trung vị token (p90) | 670 (1.200) — corpus: 274 |
| Sửa bước cắt thành first-fit (S1) | 75 → 77 câu đủ, **2 lên / 0 xuống**, chunk đáp án 96 → 99 |

Phần trống có thật nhưng chỉ cứu được 8/31 câu và thực tế first-fit chỉ cứu 2 (các chunk lấp thêm không phải đáp án). Đây là
**finding sửa baseline**, không phải đóng góp (CLAUDE.md §1b); sẽ đo riêng làm đối chứng.

## Q2 — Phía trên chunk đáp án (33 chunk L3)

| Chỉ số | Trung vị |
|---|---:|
| Hạng của chunk đáp án | 12 |
| Số chunk phía trên | 11 |
| **Token phía trên** | **6.038** (> 4.000: chunk đáp án không thể vào nếu giữ nguyên các chunk trên nó) |
| Chunk dài nhất phía trên | 1.200 |
| Số chunk ≥ 600 token phía trên | 5 — **32/33** ca có ít nhất một |
| Tỷ phần token do từ khoá chủ đạo của chunk đó | 0,59 (3 từ khoá/câu) |
| Tỷ phần token do thực thể hub (bậc ≥ 7, top-5% đồ thị) | 0,37 |
| Chunk phía trên có cùng từ khoá chủ đạo với chunk đáp án | 4 (30/33 ca có ≥ 1) |
| Bỏ riêng chunk dài nhất phía trên rồi cắt lại → chunk đáp án vào Sources | chỉ **8/33** |

Vì tổng phía trên (6.038) vượt ngân sách gần 1,5 lần, **không một thay đổi nhỏ nào** (bỏ 1 chunk, first-fit) đưa được chunk
đáp án vào: phải bỏ ~⅓ số token phía trên. Độ dài là yếu tố nổi bật (trung vị 5 chunk dài), tập trung theo từ khoá/hub cũng có
nhưng xem Q4: không khác nhóm đã đúng.

## Q3 — Từ khoá

39 ca (33 L3 + 6 L2). Chunk đáp án luôn có từ khoá góp (0 ca không có). Trung vị từ khoá của nó đã có **3** chunk trong Sources;
**14/39** ca có từ khoá đã có ≥ 5 chunk. Chỉ **5/39** ca có từ khoá của chunk đáp án **không có chunk nào** trong Sources.
Từ khoá không có chunk nào trong Sources: 10/109 (9,2%) ở câu L3/L2 so với 15/202 (7,4%) ở 75 câu đủ đáp án; câu có ≥ 1
từ khoá "đói": 8/37 (21,6%) so với 14/75 (18,7%). → **Sự đói từ khoá không phân biệt câu mất đáp án với câu giữ được.**

## Q4 — So với 75 câu đã đủ đáp án (trung vị)

| | đủ (75) | L3 ∪ L2 (37) | còn lại (68) |
|---|---:|---:|---:|
| số chunk vào Sources | 7 | **5** | 6,5 |
| token chunk trung vị trong top-30 | 510,5 | **599,5** | 471,5 |
| token còn trống | 302 | 434 | 288,5 |
| tỷ phần token của từ khoá chủ đạo | 0,67 | 0,65 | 0,71 |
| từ khoá chủ đạo khác nhau trong Sources | 2 | 2 | 2 |
| số thực thể xuất phát | 131 | **164** | 150,5 |

Điểm khác nhau rõ duy nhất: câu mất đáp án có **chunk dài hơn** (599 so với 510) nên chỉ vừa 5 chunk thay vì 7, và nhiều
thực thể xuất phát hơn. **Độ tập trung vào một từ khoá không khác.** Thêm: Spearman(token, điểm) trong top-30 = **−0,18**
(chunk dài *không* được điểm cao hơn) → giả thuyết "điểm bị thổi phồng theo độ dài" bị bác. Chunk đáp án đã giữ được có
trung vị 311 token, chunk đáp án bị mất 670 — sự khác biệt này mới là xung đột cốt lõi.

## Mô phỏng offline — MỌI cách đã thử (180 câu dev, không chạy pipeline)

Mô phỏng chính xác đến từng chunk vì tái hiện C0 180/180. "Lên/xuống" = số **câu** đổi trạng thái đủ-đáp-án so với C0.

| # | Cách xếp | Câu đủ | Chunk đáp án | Lên / xuống | Token Sources (tv) | Jaccard với C0 (tv) |
|---|---|---:|---:|---:|---:|---:|
| S0 | C0 | 75 | 96/207 | — | 3.692 | 1,00 |
| S1 | first-fit *(sửa bước cắt)* | 77 | 99 | 2 / 0 | 3.944 | 0,83 |
| S2 | phủ từ khoá (chunk hạng cao nhất mỗi từ khoá lên đầu), cắt tiền tố | 75 | 96 | 3 / 3 | 3.656 | 1,00 |
| S3 | S2 + first-fit | 76 | 98 | 4 / 3 | 3.944 | 0,82 |
| S4 | điểm/token, cắt tiền tố | 76 | 100 | 7 / 6 | 3.732 | 0,50 |
| S5 | điểm/token + first-fit | 76 | 100 | 7 / 6 | 3.908 | 0,46 |
| S6 | phủ từ khoá chọn chunk mật độ cao nhất + còn lại theo mật độ | 77 | 101 | 8 / 6 | 3.735 | 0,50 |
| S7 | S6 + first-fit | 77 | 101 | 8 / 6 | 3.907 | 0,45 |
| S8 | phủ từ khoá trên **mọi** ứng viên (bỏ trần 30) | 75 | 96 | 3 / 3 | 3.658 | 1,00 |
| S9 | điểm chunk = Σ từ khoá của max thực thể (không cộng nhiều thực thể cùng từ khoá) | 75 | 96 | 5 / 5 | 3.712 | 0,75 |
| S10 | S9 rồi xếp theo mật độ | 73 | 97 | 8 / 10 | 3.733 | 0,45 |
| S11 | xếp theo số từ khoá cùng trỏ tới chunk | **48** | 60 | 5 / 32 | 3.580 | 0,39 |
| S12 | điểm/√token | 77 | 101 | **6 / 4** | 3.686 | 0,67 |
| S13 | xen kẽ theo thực thể xuất phát chủ đạo | 63 | 83 | 2 / 14 | 3.615 | 0,57 |
| S14 | xen kẽ theo từ khoá chủ đạo | 63 | 80 | 3 / 15 | 3.622 | 0,60 |

Đọc:
- **Đa dạng hoá (S11, S13, S14) làm hại mạnh** (−12 đến −27 câu): thứ tự điểm của C0 phần lớn là đúng; chunk top thật sự cần ở trên.
- **Phủ từ khoá (S2/S3/S8) hoà** (3 lên / 3 xuống): đúng như Q3 dự báo.
- **Mật độ (S4/S5) và mật độ một phần (S12)** là hướng duy nhất có tín hiệu dương nhỏ: +1 đến +2 câu ròng, chunk đáp án +4 đến +5. McNemar
  chính xác cho 6 / 4 là p = 0,75; cho 8 / 6 là p = 0,79. **Không phải bằng chứng.**
- S6/S7 chỉ hơn S4/S12 nhờ kết hợp phủ từ khoá + mật độ, nhưng phủ từ khoá một mình hoà → không có cơ sở tách.
- **Lưu ý trung thực:** vì đã xem số dev ở bước này, dev không còn là phép thử độc lập cho các cách trên. Lượt chạy pipeline thật sẽ
  tái hiện đúng các số mô phỏng (tất định). Kết luận chỉ rút ra được trên 435 câu ngoài dev.

## Rủi ro đặc biệt — câu Null

Evidence Recall không đo được 45 câu Null. Mọi cách trên đổi tập Sources (Jaccard 0,45–0,83); mật độ ưu tiên chunk **ngắn**,
mà chunk ngắn thường là mảnh chat đơn lẻ trông "liên quan" nhưng thiếu ngữ cảnh → có thể làm Qwen bịa ở câu Null. V3 (RRF) đã đi
ngược ở Null (CLAUDE.md); phải ghi sẵn và chỉ kết luận bằng accuracy 435 câu, có tách nhóm Null.

## Đề xuất tối đa 2 hướng cho B2

**Hướng A — giá trị trên token, cụ thể điểm/token^α (ứng viên chính).**
- *Vấn đề (số B1):* 32/33 ca L3 có chunk ≥ 600 token nằm phía trên; 6.038 token phía trên so với ngân sách 4.000; câu mất đáp án có chunk dài hơn (599 so với 510) nên chỉ vừa 5 chunk thay vì 7.
- *Giả thuyết:* Sources đang trả công theo điểm mà không tính chi phí ngân sách; một chunk dài chiếm ngân sách của nhiều chunk, nên xếp theo điểm trên chi phí giữ được nhiều bằng chứng độc lập hơn trong 4.000 token.
- *Cơ chế:* xếp lại 30 chunk theo `điểm / token^α` trước A1. α **chốt trước, không dò**: α = 1 (mật độ thuần) và α = 0,5 (nửa chi phí); hai điểm này là hai đầu mút đã nằm trong B1 (S4, S12).
- *Rủi ro:* chunk đáp án bị mất dài hơn (670 so với 311) nên mật độ thuần cũng phạt đáp án; câu Null; hiệu ứng mất khi `top_k` nhỏ.

**Hướng B — chỉ như đối chứng/ablation, không phải đóng góp:** first-fit (S1) = sửa baseline. Cần để tách hiệu ứng "lấp ngân sách" khỏi hiệu ứng "xếp lại".

**Không đề xuất:** phủ từ khoá (B1 không ủng hộ: Q3, S2/S3/S8), đa dạng theo thực thể/từ khoá (S11/S13/S14 làm hại), cộng tín hiệu hub (cả Q2 lẫn phase 1 đều chỉ mô tả, chưa nhân quả).

## Kỳ vọng thực tế (nói thẳng)

Trần oracle +29 câu, nhưng tín hiệu thuần đồ thị dùng được chỉ cho +1…+2 câu ròng trên dev, nằm trong sai số. Khả năng cao
kết quả cuối là **âm tính hoặc không phân biệt được** trên 435 câu. Báo như một kết quả phủ định có kiểm soát vẫn có giá trị
(giải thích vì sao khoảng trống 29 câu không thu hẹp được bằng xếp lại thuần đồ thị).
