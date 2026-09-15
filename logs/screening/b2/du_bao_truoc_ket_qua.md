# Dự báo canary B2 — ghi TRƯỚC khi có kết quả

Ghi lúc 15/09/2026 13:26. Lúc ghi, canary đang dựng context; `logs/screening/b2/` chưa có câu trả lời hay phán quyết nào.
Đây là dự báo chủ quan để đối chiếu sau — **không phải cổng, không thay đổi quyết định**.

## Căn cứ

- Tầng A của B2: câu đủ đáp án 62,2 → 83,9% (+21,7 điểm); chunk đáp án giữ 66,2 → 86,0% (+19,8).
- Hiệu chuẩn từ B1: chunk giữ +8,7 điểm ở tầng A → +7,5 điểm trên canary → QA net +4 trên 97 câu đổi context
  (≈ 0,5 điểm acc cho mỗi điểm chunk giữ).
- 637 câu: V3 so với baseline, chunk giữ +19,4 điểm → acc +9,69 (≈ 0,5); vector thuần so với V3, +4,8 → +3,3 đến +4,5.
- Canary V3 đã giữ 72,9% chunk (cao hơn dev 180), nên B2 bị trần nhiều hơn tầng A.
- Nhiễu: σ(97) = √(0,209 · 97) ≈ 4,5 câu.

## Dự báo (khoảng tin cậy chủ quan ~80%)

| Mục | Dự báo | Khoảng |
|---|---|---|
| Câu đổi context m | ~97 | 95–100 |
| Chunk đáp án giữ (80 câu có evidence) | 72,9 → ~88% | 84–91% |
| Câu đủ đáp án | 66,2 → ~84% | 79–89% |
| acc thô (100 câu) | 62 → ~70; net ≈ +8 | net +3 đến +13 |
| Single (59) | net +7 | +3 đến +11 |
| Multi (21) | net 0 | −3 đến +3 |
| Null (20) | net −1 | −3 đến +1 |
| Δ số phiếu error | 0 | −3 đến +3 |
| Token context trung vị | −2% | trong ±5% |
| Truy hồi thêm (trung vị) | ~0 ms, nhiễu đo ±100 ms | tầng A: B1 +23, B2 −99; canary B1 +47 |
| B2 so với B1 (phụ) | net +3 | −2 đến +8 |
| B2 so với vector thuần, lượt chính thức (phụ) | net +3 | −3 đến +9 |

## Quyết định

- **CONTINUE TO DEV200: ~70%**, trong đó thăng hạng sớm ở lô 2 (net ≥ 2σ(80) = 8,2): ~30%.
- **STOP: ~30%.** Nguyên nhân khả dĩ nhất: cổng an toàn "truy hồi thêm ≤ 50 ms" trượt vì nhiễu đo thời gian (~15%);
  Null net < −3 hoặc phiếu error tăng > 3 (~10%); net QA < 1 (~5%).
- Nếu trượt chỉ vì cổng thời gian: vẫn ghi STOP theo luật đã đăng ký; mọi đề xuất sửa cổng chỉ áp cho biến thể sau.
