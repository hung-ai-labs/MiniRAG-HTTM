# Báo cáo đêm 25→26/10/2026 — MultiHop-RAG: pilot và index đầy đủ bằng Qwen2.5-3B

Nhánh `research/mhr-qwen`. Kế hoạch: [`MULTIHOP_RAG_ROADMAP.md`](MULTIHOP_RAG_ROADMAP.md) (số liệu chi tiết ở mục Phase 1).

## Tóm tắt

- **Index đầy đủ 609 bài đã xong và đạt mọi kiểm toàn vẹn** (M1.2): 1.656 chunk, 18.561 node, 14.849 cạnh, 3.312 lời gọi —
  **100% do `Qwen/Qwen2.5-3B-Instruct` trả lời**, không lời gọi nào đi qua Gemini. 162 phút, một lần chạy, không cần resume.
- **Đã sửa một vấn đề lớn về chất lượng đồ thị trước khi index**: ở trần 1024 token, 56% lời gọi trích xuất bị cắt và mất
  phần relationship → 60% node không có cạnh. Nâng trần lên 4096 **chỉ cho index** (QA giữ 1024 như bản đăng ký) — bạn đã duyệt.
- **Ánh xạ evidence → chunk xong** (M1.3): 6.084/6.084 fact nằm trọn trong chunk của index.
- **Chi phí GPU ≈ 3,5–4 USD** cho cả đêm (ước tính, xem mục Chi phí).
- **Dừng trước QA/chấm (M1.4)** — bước tiếp theo cần bạn duyệt.

## Đã làm, theo thứ tự

| Giờ (UTC) | Việc | Kết quả |
|---|---|---|
| 18:06 | Kiểm endpoint (`slm_smoke.py`) | vLLM 0.11.0, phục vụ đúng Qwen2.5-3B, khởi động lạnh 53 s — 3/3 kiểm đạt |
| 18:22–18:33 | Pilot 30 bài, trần 1024 | Dừng 1 lần vì lỗi in Unicode của Windows → chạy lại bằng `PYTHONUTF8=1 --resume`, đạt 6/6 kiểm. **Phát hiện 56% đầu ra bị cắt** |
| 18:43–18:57 | Pilot 30 bài, trần 4096 | Bị cắt còn 2%, cạnh gấp đôi (308 → 607), node cô lập 60% → 33% |
| 18:57 | Sửa lỗi gắn `chunk_id` trong log, ghi roadmap, commit `d90d892` | 8/8 test |
| 18:59–21:41 | **Index đầy đủ 609 bài** (trần 4096, song song 32) | `completed`, 6/6 kiểm đạt |
| song song | Ánh xạ evidence → chunk | 6.084/6.084 fact, 0 chunk thiếu |
| 21:44 | Khoá file index chỉ đọc; chép manifest (sha256 từng file) vào repo | — |

## Kết quả index đầy đủ

| Mục | Giá trị |
|---|---|
| Tài liệu / chunk | 609 / 1.656 (khớp dự kiến) |
| Node / cạnh | 18.561 / 14.849 — node cô lập 35% |
| Lời gọi | 3.312 thành công + 1 lỗi kết nối lúc khởi động lạnh (tự thử lại) |
| Chạm trần 4096 | 9,8% đầu ra; **gần một nửa (149/324) là vòng lặp** model tự lặp lại danh sách; ~5% đầu ra là danh sách dài thật bị cắt (vẫn giữ trung vị 30 bản ghi) |
| Bản ghi trùng | 15,7% — nằm gần hết trong các vòng lặp; đầu ra tự dừng chỉ trùng 4,3% |
| Chunk không sinh entity | 5 (3 chunk đuôi rất ngắn, 2 chunk thường) |

Vòng lặp không tạo node trùng (entity gộp theo tên, mô tả trùng bị loại) nhưng **cộng dồn trọng số một số cạnh** — đã ghi vào
Limitations. Nâng trần thêm chỉ tốn GPU cho vòng lặp, nên giữ 4096.

## Vấn đề phát hiện và đã xử lý

1. **Trần token 1024 làm đồ thị thưa giả tạo.** Định dạng trích xuất liệt kê entity trước relationship, nên khi bị cắt thì mất
   relationship (28/47 đầu ra gleaning bị cắt không còn relationship nào). Đúng cảnh báo trong CLAUDE.md §1: đồ thị thưa do
   trần hạ tầng, không phải do SLM yếu. → Trần 4096 cho index. **Khác LiHua** (index Qwen của LiHua dùng 1024) — so sánh cấu
   trúc đồ thị giữa hai dataset phải ghi rõ.
2. **Lỗi in Unicode trên Windows** làm tiến trình dừng khi stdout ghi ra file. → Mọi lệnh chạy dùng `PYTHONUTF8=1` (đã ghi
   trong roadmap). Không phải sửa code.
3. **Lỗi resume của MiniRAG** (phát hiện hôm qua bằng test): lần dừng ở pilot 1024 là lần kiểm thật đầu tiên — `index_run.py`
   dọn 8 bài của lô dở và index cuối cùng đạt đủ kiểm. Index Qwen của **LiHua** vẫn mang lỗi này ở 1 bài (`doc-62f43652…`,
   không có chunk nào) — chưa sửa, chờ nhóm quyết.
4. **Log gắn sai `chunk_id`** khi chunk đuôi nằm trong vùng chồng lấn của chunk trước → chọn chunk dài nhất (chỉ ảnh hưởng log).

## Chi phí

Modal tính tiền theo thời gian container GPU chạy, kể cả 5 phút chờ trước khi tự tắt.

| Phiên GPU | Thời gian |
|---|---:|
| Kiểm endpoint | ≈ 6 phút |
| Pilot 1024 | ≈ 16 phút |
| Pilot 4096 + index đầy đủ (container chạy liền) | ≈ 184 phút |
| **Tổng** | **≈ 3,4 giờ A10G** |

Ước tính ≈ 3,5–4 USD theo giá A10G khoảng 1,1 USD/giờ — **số chính xác xem trên dashboard Modal → Usage**. Song song 32
thay vì 8 đã giảm thời gian index từ ước tính 5–6 giờ xuống 2,7 giờ mà không đổi nội dung yêu cầu.

## Cần bạn quyết / làm

1. **Duyệt M1.4 — smoke 20 câu dev × C0, C1** (tốn GPU vài phút + vài trăm lời gọi Gemini free tier), rồi M1.5 baseline C0
   trên dev 400. Đây là lượt sinh thật đầu tiên — mọi thứ đã được đăng ký trước ở commit `7013291`.
2. **Backup index** (`indexes/multihop_rag-qwen-full609`, 160 MB): chưa có nơi lưu chung. Index này tốn ≈ 3 USD và 2,7 giờ để
   dựng lại, và dựng lại sẽ ra đồ thị khác — nên nén và chép lên nơi lưu của nhóm. Checksum từng file nằm trong
   [`artifacts/multihop_rag-qwen-full609.index_manifest.json`](artifacts/multihop_rag-qwen-full609.index_manifest.json).
3. **Index LiHua-Qwen thiếu chunk của 1 bài**: có ghi vào Limitations của LiHua không, có index lại bài đó không.
4. Pilot index (`indexes/multihop_rag-qwen-pilot30`, `…-cap4096`) chỉ để kiểm kỹ thuật; giữ lại làm bằng chứng cho quyết
   định trần 4096. Không xoá khi chưa hỏi.

## Lệnh tái lập

```sh
PYTHONUTF8=1 MINIRAG_MAX_TOKENS=4096 python reproduce/research/index_run.py --subset full \
    --workingdir indexes/multihop_rag-qwen-full609 --llm-max-async 32 --batch-docs 32
python reproduce/research/index_run.py --subset full --workingdir indexes/multihop_rag-qwen-full609 --verify
python reproduce/research/map_mhr_evidence.py --index indexes/multihop_rag-qwen-full609
```
