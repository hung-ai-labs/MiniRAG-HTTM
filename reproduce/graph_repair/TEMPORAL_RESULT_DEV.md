# V_t (node thời gian) — kết quả truy hồi trên dev 180 (runtime thật)

Chạy 09/11/2026 23:58 → 10/11/2026 02:54 bằng `run_temporal.sh`, theo [TEMPORAL_REGISTRATION.md](TEMPORAL_REGISTRATION.md)
(khoá sha256 trước khi chạy). Log: `logs/graph_repair/temporal/run_temporal.console.txt`. Nguồn gốc ý tưởng: thống kê
truy hồi trên 435 câu ngoài dev (đã công bố trong bản đăng ký); dev là tập sàng lọc.

Hồi quy: tắt công tắc, C0 khớp bản đóng băng **180/180**. Câu không có biểu thức thời gian: context **giống từng byte
154/154** ở mọi nhánh.

Biến: số câu giữ đủ mọi chunk đáp án (180 câu có Evidence), McNemar chính xác hai phía.

| Nền | Phép so | Trước → sau | lên / xuống | p |
|---|---|---:|---:|---:|
| **C0** | **Full vs −V_t (C0 gốc)** | **75 → 91** | **16 / 0** | **3,1·10⁻⁵** |
| C0 | Full vs −tương tác thời gian–thực thể (h = 1) | 86 → 91 | 5 / 0 | 0,063 |
| C0 | Full vs −mở rộng ứng viên | 78 → 91 | 13 / 0 | 2,4·10⁻⁴ |
| C-paper | Full vs −V_t (C-paper gốc) | 55 → 59 | 4 / 0 | 0,125 |
| C-paper | Full vs −tương tác | 59 → 59 | 0 / 0 | 1 |
| C-paper | Full vs −mở rộng ứng viên | 55 → 59 | 4 / 0 | 0,125 |

Runtime C0 khớp đúng mô phỏng log (`sim/temporal_sim.py`: 75 → 91, 16/0, h = 1 → 86).

## Đọc

- Trên C0, V_t tăng mạnh và sạch: 16 câu lên, không câu nào xuống, không đổi câu không có thời gian.
- Phần lớn lợi ích nằm ở **mở rộng ứng viên** (đưa chunk của ngày được hỏi vào tập ứng viên): bỏ nó còn 78.
  Phần **tương tác thời gian–thực thể** chỉ thêm 5 câu, p = 0,063 — chưa được viết "đồ thị vượt tra theo ngày".
- Trên C-paper lợi ích nhỏ (+4, p = 0,125): Step 2 + trần 5 chunk và Step 1 giới hạn những gì V_t đưa vào được.
- Đây là truy hồi trên dev, không phải accuracy. Bước tiếp theo theo bản đăng ký: sinh câu trả lời (≥ 3 lượt sinh ×
  3 lượt chấm) trên Qwen và Phi, báo acc và err với b/c/p.
