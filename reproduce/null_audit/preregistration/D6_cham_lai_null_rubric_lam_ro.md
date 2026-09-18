# Đăng ký trước — Đ6: chấm lại nhóm Null với rubric được làm rõ

**Việc:** Đ6 (xem [`docs/DE_XUAT_CAI_THIEN_NULL.md`](../../../docs/DE_XUAT_CAI_THIEN_NULL.md)).
**Ngày chốt:** 17/09/2026 — commit và push file này **trước** khi gửi bất kỳ lời gọi nào với rubric mới.
**Nhóm duyệt:** Hùng, 17/09/2026.

## Vì sao

Ba việc kiểm trước đã chỉ về cùng một hướng:

| Việc | Kết luận |
|---|---|
| Đ2 — chấm lại 3 lượt bằng rubric gốc | mức giảm Null của B2 **không** phải nhiễu giám khảo |
| Đ1 — người chấm 40 câu (Djicz) | 22/24 câu rubric gốc chấm `neither` thì người chấm **đúng**; chiếu ra, B2 từ thấp nhất thành cao nhất |
| Đ3 — rà 65 nhãn Null | nhãn **không** giải thích được khoảng cách Null của B2 |

Nhưng Đ1 là 40 câu của **một người**, và kết quả toàn bộ chỉ là **phép chiếu**. Đ6 đo trực tiếp: chấm lại toàn bộ câu Null của
mọi nhánh bằng một rubric nói rõ cách xử lý câu trả lời pha trộn, sau khi đã kiểm rubric đó với người.

## Rubric — khoá nguyên văn

Prompt = prompt gốc trong `reproduce/Step_2_evaluate.py` (biến `JUDGE_PROMPT`, không đổi chữ nào) **cộng đúng đoạn sau**:

```
When the gold answer is "Insufficient information": if the system answer clearly
states that the specific detail asked for is not available in the information it
has, reply "accurate", even if it also describes related events. Reply "error"
only if it presents the missing detail as a fact.
```

- **sha256 của toàn bộ prompt:** `78e5a15278535b893d6cec1dff38aa0e3901cbe425766145f35181432e94240b`.
  `rejudge_null_clarified.py` kiểm mã băm này mỗi lần chạy và **dừng** nếu prompt bị sửa.
- Giám khảo `gemini-flash-lite-latest` (free tier), dùng lại nguyên hàm `judge()` của `Step_2_evaluate.py` (thử lại 6 lần; lượt
  hỏng không được ghi).
- **3 lượt chấm**, mỗi lượt xáo thứ tự bằng `random.Random(13 + lượt)`. Phán quyết = đa số tuyệt đối; chia đều → `neither`
  (cùng luật với `analyze_stage_d.py`).
- Thay đổi kỹ thuật đi kèm: `Step_2_evaluate.py` thêm `if __name__ == "__main__"` để import được. Chạy như script thì hành vi
  không đổi; mọi script cũ đều gọi nó bằng dòng lệnh.

## Bước 2 — cổng kiểm trên 40 dòng Đ1

- **Đầu vào:** 40 câu trả lời trong `logs/null_audit/d1_judge_audit/sheet_A.csv`; nhãn người là cột `phan_quyet` (Djicz).
- So rubric mới (đa số 3 lượt) với `phan_quyet` của người.
- **QUA khi đạt đủ cả ba:**

| | Điều kiện | Ngưỡng |
|---|---|---|
| (a) | khớp với người trên 40 dòng | ≥ 32/40 |
| (b) | khớp trên 24 dòng rubric gốc chấm `neither` | ≥ 20/24 |
| (c) | trong các dòng người chấm `SAI`, rubric mới chấm `error` | ≥ 5/7 |

  Điều kiện (c) để chắc rubric mới không biến thành "cái gì cũng đúng".
- **Báo kèm để đối chiếu:** rubric gốc (lượt chấm chính thức) khớp với người 15/40.
- **KHÔNG QUA → báo là không qua và dừng.** Không sửa câu chữ rubric rồi thử lại trên 40 dòng này; nếu muốn thử rubric khác thì
  phải có đăng ký mới **và** một tập người chấm mới.
- **Giới hạn đã biết:**
  - nhãn người là của **một** người;
  - chỉ 24 dòng tranh chấp, nên cổng thô;
  - 40 câu này cũng nằm trong tập sẽ chấm ở bước 3, nên đây là **hiệu chuẩn**, không phải kiểm độc lập.

## Bước 3 — chấm toàn bộ (chỉ chạy khi cổng QUA)

- **Mẫu:** 45 câu Null ngoài dev × 4 nhánh × 3 lượt sinh = 540 câu trả lời.

| Nhánh | File câu trả lời |
|---|---|
| V3 | `logs/qwen637_v3.csv`, `logs/qwen637_v3_r2.csv`, `logs/qwen637_v3_r3.csv` |
| Vector thuần | `logs/qwen637_vec.csv`, `logs/stage_d/vec_s202.csv`, `logs/stage_d/vec_s303.csv` |
| B1 | `logs/stage_d/b1_s{101,202,303}.csv` |
| B2 | `logs/stage_d/b2_s{101,202,303}.csv` |

- **Khối lượng:** 3 lượt chấm = 1.620 lời gọi, free tier.
- **Báo:** Null acc / err / neither từng nhánh theo rubric làm rõ, **đặt cạnh** rubric gốc (lượt chấm chính thức); và Null net
  từng cặp lượt của H1, H2, H3 theo cả hai rubric.
- **Không báo** kiểm định ý nghĩa giữa các nhánh: 45 câu mỗi nhánh không đủ, giống tầng D. Chỉ báo thứ hạng và chiều.

## Sửa đăng ký, 18/09/2026 — thêm baseline vào bước 3

Chốt **trước** khi gửi lời gọi nào cho baseline. Lý do: bước 3 cho thấy theo rubric làm rõ bốn nhánh RRF hoà nhau, nhưng baseline
MiniRAG gốc (Null acc chính thức 73,3 trên 45 câu ngoài dev) chưa được chấm lại, nên chưa biết khoảng cách Null giữa B2 và baseline
là do rubric hay do hệ thống.

- **Thêm mẫu:** 45 câu trả lời Null ngoài dev của `logs/qwen637_fix.csv` (baseline chỉ có **một** lượt sinh) × 3 lượt chấm.
- **Rubric, giám khảo, seed, luật đa số:** giữ nguyên, prompt vẫn khoá đúng mã băm ở trên. Các phiếu đã chấm của bốn nhánh được dùng
  lại, không chấm lại.
- **Báo thêm:** Null acc / err / neither của baseline theo hai rubric; Null net của V3 và B2 so với baseline theo hai rubric.
- **Cách dùng:** giữ nguyên mục dưới — chỉ độ nhạy.

## Cách dùng kết quả

**ĐỘ NHẠY.**
- Không thay số chính thức của tầng D.
- **Không** xét lại cổng E4 hay phân loại H1–H3.
- Không dùng để chọn biến thể.
- Không phải cải tiến hệ thống: đổi cách **đo**, không đổi thứ được đo; mọi nhánh dùng cùng một rubric.
- Trong bài, luôn đặt số của hai rubric cạnh nhau.

## File kết quả

`logs/null_audit/d6_clarified/` — `gate_judged.csv`, `gate_ket_qua.txt`, `gate_status.txt`; nếu qua cổng thì thêm
`full_judged.csv`, `full_ket_qua.txt`.
