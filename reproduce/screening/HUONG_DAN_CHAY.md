# Hướng dẫn chạy sàng lọc BM25 trên máy của bạn

Cho các thành viên nhóm. Quy trình và cổng quyết định nằm trong [ROADMAP.md](../../ROADMAP.md), mục sửa đổi đăng ký
trước cho BM25 (tầng A–D). Script ở đây chỉ chạy tầng A–C trên tập dev. Tầng D (435 câu ngoài dev) không có ở đây.

## Trạng thái (16/09/2026)

| Bước | Kết quả | Endpoint | Commit |
|---|---|---|---|
| Tầng A — B1 = RRF(Graph, Vector, BM25) | CONTINUE TO CANARY | hung-ai-labs (chỉ parser) | `739d024` |
| Tầng A — B2 = RRF(Vector, BM25) | CONTINUE TO CANARY | hung-ai-labs (chỉ parser) | `739d024` |
| Đông lạnh V3 canary | FROZEN — acc 62,00 | hung-ai-labs | `739d024` |
| Canary B1 | CONTINUE TO DEV200 — net +4, dưới 1σ = 4,50 | hung-ai-labs | `65280ae` |
| Canary B2 | gốc STOP (cổng thời gian +61,7 ms) → đo lại theo sửa đổi đăng ký: **PROMOTE, lệch đăng ký**; QA net +6 | hung-ai-labs | xem ROADMAP |
| Đo lại cổng thời gian (B1, B2) | cả hai đạt: T1 −15,1 / −7,7 ms, BM25 ~1 ms | CPU máy Hùng | xem ROADMAP |
| Dev 200 — mở rộng V3 | FROZEN (200/200) | hung-ai-labs | xem ROADMAP |
| Dev 200 — B1 | **FINALIST** — 30 lên / 10 xuống, net +20 (3,1σ) | hung-ai-labs | xem ROADMAP |
| Dev 200 — B2 | **FINALIST** (lệch đăng ký từ tầng B) — 49 lên / 18 xuống, net +31 (4,8σ) | hung-ai-labs | xem ROADMAP |
| Tầng D — 435 câu × 3 seed | **XONG 16/09**: H1 +6,51 và H3 +6,59 ROBUST POSITIVE, H2 BORDERLINE (trượt cổng Null). Nhóm **chốt B2**; báo cáo `logs/stage_d/stage_d_report.txt`. Không chạy lại | hung-ai-labs | xem ROADMAP |

## Quy tắc — đọc trước khi chạy

1. **Mỗi bước chỉ một người chạy.** Báo nhóm trước ("mình chạy canary B2"), chạy xong commit và push ngay. Hai người cùng
   chạy một biến thể sẽ ghi chồng lên `answers.jsonl` của nhau.
2. **Không chạy lại, không xoá** `logs/screening/frozen/`, `logs/screening/cache/kw_cache.jsonl`, các báo cáo
   `*_report.*` đã commit, và index `LiHua-World-qwen-modal/`. Bước nào đã có quyết định thì script tự dùng lại.
3. **Không chạy `--stage dev`**, hay bất kỳ lượt 435/637 câu nào, khi nhóm chưa duyệt.
4. **Không chạy hai tiến trình sinh cùng lúc trên một máy.** Script tự chờ nếu thấy `Step_1_QA.py` đang chạy.
5. **Thấy `ASSERT: ...` hoặc `thiếu đầu ra parser trong cache` thì dừng**, gửi log cho nhóm. Đừng tự đông lạnh lại V3 hay xoá
   cache: đó là dấu hiệu code hoặc index của bạn lệch với mốc đã commit.
6. **Khoá không bao giờ vào repo, chat hay log.** Mỗi người dùng Modal và khoá Gemini của riêng mình.

## 1. Cài đặt (một lần)

Cần macOS hoặc Linux (Windows thì dùng WSL), Python 3.13 (đã kiểm), git.

```bash
git clone https://github.com/hung-ai-labs/MiniRAG-HTTM.git
cd MiniRAG-HTTM
git checkout dev
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt openai sentence-transformers nano-vectordb json_repair modal
```

Model embedding `all-MiniLM-L6-v2` tự tải về ở lần chạy đầu (khoảng 90 MB).

## 2. Deploy SLM lên Modal của bạn (một lần)

Lệnh sau tạo khoá ngẫu nhiên ngay trên máy bạn và cất vào `~/.config/minirag/`, ngoài repo. Khoá không hiện lên màn hình.

```bash
.venv/bin/modal token new
mkdir -p ~/.config/minirag && chmod 700 ~/.config/minirag
openssl rand -hex 24 > ~/.config/minirag/slm_key && chmod 600 ~/.config/minirag/slm_key
.venv/bin/modal secret create minirag-slm-key MINIRAG_SLM_KEY="$(cat ~/.config/minirag/slm_key)"
.venv/bin/modal deploy reproduce/modal_slm.py
```

`modal deploy` in ra URL dạng `https://<workspace>--minirag-slm-serve.modal.run`. Ghi URL đó vào file:

```bash
echo "https://<workspace>--minirag-slm-serve.modal.run" > ~/.config/minirag/slm_url
```

Kiểm endpoint. Lần đầu mất 2–5 phút để GPU khởi động và tải model; thấy chữ `minirag-slm` trong kết quả là được:

```bash
curl -s -m 600 -H "Authorization: Bearer $(cat ~/.config/minirag/slm_key)" "$(cat ~/.config/minirag/slm_url)/v1/models"
```

Deploy dùng image ghim `vllm==0.11.0` và cùng model `Qwen/Qwen2.5-3B-Instruct`, nên kết quả so được với lượt chạy trên
Modal khác. GPU tự nhả sau 5 phút không có yêu cầu, lúc rảnh không tốn tiền.

## 3. Khoá Gemini cho giám khảo (một lần)

```bash
cp .env.example .env
```

Mở `.env` bằng trình soạn thảo, điền `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, … (free tier). Càng nhiều khoá chấm càng nhanh.
`.env` đã bị gitignore, không bao giờ commit.

## 4. Chạy canary B2

> ⚠️ **Canary B2 đã chạy xong ngày 15/09 (gốc STOP; sau đo lại thời gian: PROMOTE — lệch đăng ký). Không chạy lại lệnh dưới.** Chạy lại sẽ dựng lại context, đo lại thời gian
> và ghi đè báo cáo đã commit; script nay từ chối nếu bước đó đã có quyết định. Phần này giữ làm mẫu cho biến thể sau.

```bash
git pull
reproduce/screening/run_screen.sh --variant b2 --stage canary
```

Script làm theo thứ tự:
1. Dựng lại context V3 cho 100 câu canary chỉ từ cache, kiểm khớp hash đông lạnh (khoảng 9 phút CPU).
2. Dựng context B2 cho 100 câu (khoảng 9 phút).
3. Sinh câu trả lời cho các câu đổi context trên Modal, theo ba lô 40 / 40 / 20.
4. Chấm một lượt bằng Gemini, áp cổng tuần tự sau mỗi lô và in quyết định.

Tổng khoảng 40 phút; GPU chỉ chạy vài phút. Kết quả nằm ở `logs/screening/b2/canary_report.txt`, dòng `Decision:` là
`CONTINUE TO DEV200`, `STOP` hoặc `INVALID`. Báo cáo ghi endpoint và tên git của người chạy.

Máy tắt hoặc mạng rớt giữa chừng thì chạy lại đúng lệnh cũ: câu đã sinh hoặc đã chấm được dùng lại.

## 5. Commit kết quả

```bash
git add logs/screening/b2
git commit -m "B2 canary: <quyết định> (<lên> lên / <xuống> xuống)"
git push origin dev
```

Rồi dán nội dung `canary_report.txt` vào nhóm. Nếu `git status` báo `LiHua-World-qwen-modal/` thay đổi thì đừng commit
phần đó (index không được đổi), báo nhóm.

## Lỗi thường gặp

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Thiếu endpoint hoặc khoá SLM` | Chưa có `~/.config/minirag/slm_url` hoặc `slm_key` | Làm lại bước 2 |
| `401` / `Unauthorized` lúc sinh | Khoá trong file khác khoá trong Modal secret | `modal secret create --force minirag-slm-key MINIRAG_SLM_KEY="$(cat ~/.config/minirag/slm_key)"`, rồi `modal deploy` lại |
| `No Gemini API key found` | Chưa có `.env` | Làm bước 3 |
| `thiếu đầu ra parser trong cache` | Cache hoặc code không khớp commit | `git pull`; `git status` phải sạch ở `logs/screening/`; vẫn lỗi thì báo nhóm |
| `ASSERT: context V3 dựng lại lệch hash` | Index hoặc code khác mốc | Không chạy tiếp, gửi log cho nhóm |
| Đứng lâu ở lô đầu | GPU đang khởi động | Chờ 2–5 phút |
| `đang có Step_1_QA chạy — chờ 60 s` | Máy đang chạy một lượt QA khác | Chờ nó xong |

Log đầy đủ của mỗi lần chạy nằm ở `logs/screening/screen.log` (không commit).
