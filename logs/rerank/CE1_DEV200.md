# CE1 — kết quả tầng dev 200, mốc so sánh B2 đông lạnh → **STOP**

> 21/09/2026 · Cổng tầng dev chốt trong [`CE2_canary.md`](../../reproduce/rerank/preregistration/CE2_canary.md) mục 2 và 6,
> commit `9f2e760` **trước** khi chạy. Báo cáo máy sinh: `logs/screening/ce1/dev_report.txt`.

**Quyết định của bộ sàng lọc: `STOP`.** Theo luật đã chốt: tắt chế độ thí nghiệm, **giữ B2 làm hệ thống chính thức**,
ghi lại như kết quả phủ định. Không chạm 637, không chạm tầng D. Cờ vẫn tắt mặc định — code runtime giữ lại để tái lập,
không bật.

## Vì sao STOP

Mọi cổng **chất lượng** đều đạt. Cổng **chi phí do chính tôi đăng ký trước** thì trượt.

| Cổng | Kết quả | |
|---|---|---|
| Null net ≥ −3 | net 0 | ĐẠT |
| Multi net ≥ −3 | net −2 | ĐẠT |
| số phiếu error tăng ≤ +4 | −3 | ĐẠT |
| token context trung vị ±5% | 3877 → 3858 (−0,5%) | ĐẠT |
| Single net ≥ 0 | +9 | ĐẠT |
| net ≥ 1σ(m) | net +7, σ(m) = 6,40 | ĐẠT |
| *(ghi nhận, không quyết)* truy hồi thêm ≤ 50 ms | +1946 ms trung vị | TRƯỢT |
| **phần xếp lại ≤ 3000 ms/câu (cổng 8 của CE1)** | **max 3429 ms — 5/200 câu vượt** | **TRƯỢT** |
| **tổng truy hồi p95 ≤ 2× mốc** | lượt sàng lọc báo trượt | **TRƯỢT** (xem cảnh báo dưới) |

**Cổng 8 là lý do vững.** Đăng ký trước CE1 viết *"phần xếp lại ≤ 3000 ms **mỗi câu** trên CPU"*, cài đúng nghĩa đen là
`max`. Trên dev 200: p50 **1830 ms**, p95 **2731 ms**, **max 3429 ms**, **5/200 câu vượt 3000 ms** (3051 · 3112 · 3136 ·
3414 · 3429). Canary 100 câu không có câu nào vượt — ngưỡng chỉ lộ ra khi tập lớn hơn. Đây là thất bại thật, tái lập được,
không phải nhiễu đồng hồ.

**⚠ Cổng p95 thì tôi KHÔNG tái lập được, và phải nói rõ.** Lượt sàng lọc báo trượt, nhưng dựng lại context cùng bộ câu
offline cho: B2 p95 **9742 ms**, CE1 p95 **11909 ms**, trần 2× = 19485 → **đạt**. Hai lần đo tường trên cùng máy đang
chạy nhiều thứ khác cho kết quả khác nhau, và lượt sàng lọc **không lưu lại phân vị nó đã nhìn thấy**, nên không dựng
lại được. Tôi **không** dùng số offline để lật quyết định đã ghi — nhưng cũng **không** tính cổng này là lý do thứ hai
để dừng. Lý do dừng là cổng 8.
*Đã sửa công cụ:* `safety()` nay ghi `retrieval_p95_var/base`, `rerank_p50/p95/max` vào báo cáo để lần sau kiểm toán được.
Đây là **đo đạc**, không đổi cổng nào.

## Kết quả QA (200 câu, 1 lượt sinh seed 20260914 × 1 lượt chấm)

| | mốc B2 | CE1 | |
|---|---:|---:|---|
| acc | 74,50 | **78,00** | Δ +3,50 |
| err | 22,00 | 20,50 | −3 phiếu |
| neither | 3,50 | 1,50 | |

**Ghép cặp so với B2: 22 lên / 15 xuống, net +7, McNemar p = 0,324.** σ(m) = 6,40 với m = 196 câu đổi context.

| Nhóm | n | acc mốc → CE1 | lên / xuống |
|---|---:|---|---|
| Single | 159 | 79,2 → **84,9** | 19 / 10 |
| Multi | 21 | 57,1 → 47,6 | 2 / 4 |
| Null | 20 | 55,0 → 55,0 | 1 / 1 |

### ⚠ dev 200 KHÔNG kiểm lại Multi và Null

`canary100` là **tập con** của `dev200`, và phần Multi/Null **trùng khít**:

| | canary | dev | câu mới ở dev |
|---|---:|---:|---:|
| Single | 59 | 159 | **100** |
| Multi | 21 | 21 | **0** |
| Null | 20 | 20 | **0** |

Nên con số Multi (2/4) và Null (1/1) ở đây **chính là số của canary**, cùng câu, cùng câu trả lời, cùng phán quyết —
**không phải lần lặp độc lập**. Thông tin thật sự mới của tầng dev là **100 câu Single**, và ở đó net là 19 lên / 10 xuống.
Ai đọc bảng này mà tưởng Multi/Null đã được kiểm hai lần là hiểu sai.

**Hệ quả:** nhận định "Multi tụt do thứ tự trình bày" từ canary **vẫn chưa được kiểm lại lần nào**. Muốn kiểm phải có
câu Multi ngoài dev — tức tầng D hoặc bộ 637, vốn chưa được duyệt.

## Truy hồi

| | mốc B2 | CE1 |
|---|---:|---:|
| chunk đáp án giữ được | 86,0% | **90,8%** |
| câu đủ bằng chứng (180 câu có evidence) | 83,9% | **90,0%** |
| token context trung vị | 3877 | 3858 (−0,5%) |
| truy hồi trung vị | 5828 ms | 7773 ms (+33%) |
| phần xếp lại | — | p50 1830 · p95 2731 · max 3429 ms |
| context đổi | — | 196/200 câu |

Phần truy hồi làm đúng việc nó hứa: giữ bằng chứng tăng từ 83,9% lên 90,0% câu, đúng hướng và đúng độ lớn mà kiểm toán
offline dự báo (offline đo 83,9% → 90,0% trên cùng tập — **trùng khít**).

## Null — ràng buộc an toàn

acc **11/20 → 11/20** · err **9 → 8** · neither **0 → 1**. Chuyển dịch: `error→accurate` 1, `accurate→error` 1,
`error→neither` 1, còn lại giữ nguyên. Sự kiện phân biệt trong Sources trung vị **10,5 → 7,5**.

Ba chunk gây nhầm (luật tiến cứu CE2 mục 1): L002 8→3 **thoái lui** · L052 1→1 **trung tính** · L055 4→16 và rời Sources
**cải thiện**. **1/3, cổng ≤ 1 → đạt.**

Null **không xấu đi**. Nhưng vì đây là cùng 20 câu của canary, nó cũng **không phải bằng chứng mới**.

## Đọc kết quả này cho đúng

net +7 với **p = 0,324** trên một lượt sinh **không** phải bằng chứng cải thiện accuracy. Theo CLAUDE.md §3, một lượt
sinh đơn lẻ mà net dưới ~18 câu thì chưa kết luận được; sàn nhiễu giữa các lượt sinh trên dev là **1,5 điểm**, còn
Δacc ở đây là 3,50 điểm trên một lượt.

**Được viết:**
> *"Xếp lại bằng cross-encoder cải thiện rõ khâu giữ bằng chứng (câu đủ bằng chứng 83,9% → 90,0% trên dev 200) và không
> làm Null xấu đi, nhưng trượt cổng chi phí đã đăng ký trước (5/200 câu vượt 3000 ms trên CPU), nên hướng này dừng ở
> tầng dev. Mức tăng accuracy quan sát được (+3,50, p = 0,324, một lượt sinh) chưa vượt sàn nhiễu."*

**Không được viết:** "cross-encoder cải thiện accuracy", "đã giải quyết Null", "đã cải thiện Multi-hop", hay bất cứ câu
nào coi Multi/Null ở tầng dev là lần kiểm thứ hai.

## Điều KHÔNG được làm tiếp (theo luật đã chốt)

- Không nới cổng 8 cho vừa kết quả.
- Không đổi thiết bị sang MPS để qua cổng. MPS nhanh gấp đôi và cho thứ hạng trùng khít, nhưng thiết bị đã được **ghim là
  CPU trước khi có kết quả**; đổi thiết bị bây giờ là chọn cấu hình theo kết quả. Nếu nhóm muốn đo lại trên MPS thì đó là
  **thí nghiệm mới, đăng ký trước mới**, và là quyết định của nhóm chứ không phải của tôi.
- Không thử reranker thứ hai.
- Không fine-tune.
- Không chạy 637 hay tầng D.

## Chi phí đã dùng

Tầng canary + dev cộng dồn: **196 lời sinh** trên Modal, **196 lời gọi giám khảo** (ít hơn 69,2% / 89,7% so với 637 × 3).

## Giới hạn

- Một lượt sinh, một lượt chấm ở cả hai tầng.
- Multi (n=21) và Null (n=20) chỉ được đo **một lần**, dùng chung giữa canary và dev.
- Nhãn "chunk gây nhầm" do một người đọc xác định, chưa ai rà lại.
- Cổng thời gian đo bằng đồng hồ tường trên máy cá nhân đang chạy nhiều tiến trình; cổng p95 không tái lập được (đã sửa
  công cụ để lần sau lưu phân vị).
- Chỉ một model, một revision, một chính sách cắt, một thiết bị.
