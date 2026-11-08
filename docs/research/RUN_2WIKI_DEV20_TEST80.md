# Chạy 2Wiki: 20% phân tích lỗi, 80% đánh giá

Chuẩn bị ngày 30/10/2026 theo yêu cầu người dùng. Đây là hướng dẫn vận hành;
chưa phải kết quả benchmark, không thay xác minh deployment hay review khoa học.

**Bổ sung acceleration:** đã port truy hồi dùng chung C0/C1 và consumer chấm
gối từ nhánh đồng đội. Sau khi có index Modal, làm theo
[PORT_2WIKI_ACCELERATION.md](PORT_2WIKI_ACCELERATION.md) để kiểm tương đương
trên dev401 trước khi dùng pipeline mới. Các bước thiết lập/pilot/index dưới
đây vẫn áp dụng; chưa khẳng định mức tiết kiệm tiền khi chưa đo trên GPU thật.

## Đã chuẩn bị offline

- Giữ pool n2000_seed13 và corpus 11.657 đoạn hiện có.
- Khóa split mới: **401 internal_dev / 1.599 internal_test**, seed 13.
  Dùng thuật toán chia theo thành phần liên thông title gold đã có; không xé nhóm
  để ép đúng 400/1.600. Không có title gold chung giữa hai tập. Distractor có thể chung.
- Thư mục `dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/` chứa
  CSV, queries không có gold, gold/aliases riêng và manifest checksum. Không đưa lên Git.
- `smoke_dev20.csv` chỉ có 20 câu từ phần dev. Không mở internal_test để tinh chỉnh.
- Báo cáo công khai chỉ chứa counts/hash:
  `docs/research/env/2wiki_split_dev20_test80_seed13.json`.
- `judge_2wiki.py` nhận answers.jsonl theo ID, xét aliases, chấm ba lượt độc lập,
  không biến lỗi parse/API thành neither, lưu trace, hỗ trợ resume cùng identity.
  Rubric mới phải kiểm tay trên smoke trước benchmark; chưa xác minh Gemini model ID.

## 1. Hiểu thiết lập Modal

Modal chạy Qwen trên GPU cloud. Máy Windows chạy script điều phối, embedding và
truy hồi; endpoint là địa chỉ HTTP của máy chủ Qwen. Key của endpoint do bạn tạo,
khác token đăng nhập Modal và key Gemini. Không gửi các key vào chat/Git.

Trong PowerShell tại gốc repo:

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py -m modal --version
& $py -m modal app list
```

Hai lệnh trên không gọi Qwen. Nếu chưa đăng nhập, dùng `& $py -m modal token new`
và hoàn thành đăng nhập trong trình duyệt. Kiểm Billing của đúng workspace để
biết credit/ngân sách. Chưa có phép đo đủ để báo chi phí toàn corpus.

Tại https://modal.com/secrets tạo **Custom Secret** tên `minirag-slm-key`, với
biến `MINIRAG_SLM_KEY` là một chuỗi ngẫu nhiên dài. Giữ bản sao trong `.env` local.
Không ghi đè Secret đang dùng bởi ứng dụng của người khác.
Tài liệu: https://modal.com/docs/guide/secrets.

Script có sẵn dùng App `minirag-slm`. Chỉ deploy nếu App này là của bạn và không
có thí nghiệm đang dùng; nếu dùng chung, cần tạo tên App/Secret riêng trước.

```powershell
& $py -m modal deploy reproduce/modal_slm.py
```

Deployment có thể build image/tạo tài nguyên. Ghi lại URL web server trả về;
không gọi endpoint cho tới khi sẵn sàng chạy GPU tính phí.
Tài liệu: https://modal.com/docs/guide/managing-deployments.

Tạo `.env` ở gốc repo, điền trực tiếp trong editor, không dán key vào lệnh/chat:

```dotenv
MINIRAG_SLM_URL=https://DIA_CHI_WEB_SERVER_CUA_BAN.modal.run/v1
MINIRAG_SLM_KEY=KEY_GIONG_TRONG_MODAL_SECRET
```

Đây là placeholder. Đừng commit `.env`; không đặt GEMINI_API_BASE toàn cục.

## 2. Xác minh deployment, chạy smoke trả phí nhỏ

Trước bước này, chọn mức tiền tối đa cho pilot và theo dõi Billing; runner chưa
có hard monetary cap. Không tự chạy toàn corpus chỉ vì smoke thành công.

Chuẩn bị `configs/research/2wiki/serving_modal.json` từ cấu hình deployment thực
tế, đủ các trường `model_revision, vllm_version, gpu, dtype, max_model_len, sampling`.
`reproduce/research/serving_qwen_modal.json` là **tham chiếu**, có provenance suy ra;
không sao chép rồi coi là revision đã được xác minh. Script server hiện chưa pin
model revision: cần pin/xác minh trọng số trước benchmark chính thức.

```powershell
& $py -X utf8 reproduce/research/slm_smoke.py --serving configs/research/2wiki/serving_modal.json --out runs/2wiki/modal/serving/smoke01.json
```

Lệnh này gọi GPU thật. Kiểm version/model/response; sau đó pilot index 20 đoạn:

```powershell
$pool = 'dataset/2WikiMultiHopQA/processed/pools/n2000_seed13'
$split = 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80'
$serving = 'configs/research/2wiki/serving_modal.json'
& $py -X utf8 reproduce/research/index_run.py --dataset-id 2wiki --docs "$pool/docs.jsonl" --subset pilot --pilot-size 20 --workingdir indexes/2wiki-modal-pilot20-dev20test80 --max-output-tokens 4096 --serving-config $serving --llm-max-async 4 --batch-docs 4
```

Pilot này chọn đoạn từ corpus, không phải QA 20 câu. Index nhỏ chưa đủ bằng chứng
để đánh giá accuracy trên tập câu hỏi. Kiểm finish_reason, output bị cắt, cấu trúc
graph, mọi verification và chi phí đo thực tế trước full index. Không dùng index
Ollama Q4 cũ để tiếp tục bằng Modal bf16.

## 3. Full index, sau khi pilot đạt và đã chốt chi phí

### Đợt đầu giới hạn 30 phút (người dùng chọn 30/10/2026)

Hai pilot20 đã đạt. Cấu hình ứng viên batch16/async8; xem
MODAL_PILOT20_REVIEW.md. Trước index mới, redeploy script đã pin revision/dtype:

```powershell
python -m modal deploy reproduce/modal_slm.py
```

Nếu endpoint trả về đổi thì cập nhật MINIRAG_SLM_URL trong .env bằng URL serve
(.modal.run/v1), không dùng link dashboard modal.com/apps. Sau deploy thành công:

```powershell
python reproduce/research/index_run.py --dataset-id 2wiki --docs dataset/2WikiMultiHopQA/processed/pools/n2000_seed13/docs.jsonl --subset full --workingdir indexes/2wiki-modal-n2000-s13-dev20test80 --max-output-tokens 4096 --serving-config configs/research/2wiki/serving_modal.json --llm-max-async 8 --batch-docs 16 --max-runtime-seconds 1800
```

Timer áp dụng mỗi lần gọi, từ lúc parse CLI; hết giờ hủy await của lô hiện tại,
không bắt đầu lô mới. Thao tác đồng bộ/cleanup có thể cần thêm thời gian; đây
không phải hard monetary cap hoặc lệnh dừng App trên Modal. GPU có thể còn tính
phí khi đang hoàn tất request hoặc giữ ấm (scaledown 300 giây).

Nếu hết giờ, exit code **3**, manifest `status=partial`, `stop_reason=time_limit`.
Đây là trạng thái dự kiến, không dùng index partial để QA/đánh giá. Lô dang dở
không được ghi progress; khi resume, reconcile sửa checkpoint phần chưa commit.
Lô đã hoàn tất được giữ nguyên. Sau khi review tiến độ/Billing, chạy tiếp đúng
lệnh trên với **--resume** để cấp thêm tối đa 1.800 giây cho lượt mới. Không tự
resume liên tục nếu chưa chốt ngân sách bổ sung, không xóa/đổi manifest.
Giữ nguyên source index_run/minirag/backend trong suốt các lượt resume.

Kiểm thử guard mới: 14 test index/time-limit đạt, dùng LLM/embedding giả,
không gọi cloud. Chưa chạy full index trả phí trong bước chuẩn bị giới hạn.

### Lệnh không giới hạn (chỉ tham khảo khi đã có ngân sách riêng)

```powershell
& $py -X utf8 reproduce/research/index_run.py --dataset-id 2wiki --docs "$pool/docs.jsonl" --subset full --workingdir indexes/2wiki-modal-n2000-s13-dev20test80 --max-output-tokens 4096 --serving-config $serving --llm-max-async 4 --batch-docs 4
```

Index mới, không ghi index LiHua/pilot local. Nếu gián đoạn, dùng lại đúng lệnh
với `--resume`. Đổi model/cap/serving/source không được lách manifest để resume.
Corpus nominal 23.322 call extract/glean trước retry/cache; không lấy giá đợt LiHua
để dự toán đợt này. Snapshot index và backup ngoài máy trước QA lớn.

## 4. Baseline QA, chỉ dev trước

Registration vận hành dùng tài liệu này và báo cáo split; chưa tuyên bố nhóm đã
review serving/rubric. C0 là baseline nhóm, C1 là B2; chưa chạy proposed ở bước này.

```powershell
& $py -X utf8 reproduce/research/run_phased_qa.py --dataset-id 2wiki --index indexes/2wiki-modal-n2000-s13-dev20test80 --questions "$split/smoke_dev20.csv" --registration docs/research/RUN_2WIKI_DEV20_TEST80.md --serving-config $serving --out runs/2wiki/modal/baseline-smoke-s101-c4 --seed 101 --configs C0 --workers 1 --llm-max-async 4
```

Mặc định chỉ in kế hoạch. Thêm `--execute` để thực sự gọi GPU. Sau smoke đạt,
dùng `internal_dev.csv` và một output directory mới để chạy 401 câu. Giữ cùng seed,
serving/concurrency khi so cấu hình. Không chạy internal_test trước khi đóng băng
phương pháp. Ba lượt chấm không thay thế ba lượt sinh của benchmark cuối.

## 5. Gemini chấm và phân tích lỗi

Trong shell mới, điền key Gemini free tier vào `.env` local (GEMINI_API_KEY hoặc
các key theo pool đã có). Chốt **exact Gemini model ID** trước chạy; không tự đổi
Flash thành Flash-Lite. Không tăng limiter hiện có. Xác minh quota/free tier của
project; không bật billing trả phí theo hướng dẫn này.

Ví dụ cho dev đầy đủ, sau khi đã sinh đủ 401 câu trong `baseline-dev-s101-c4`:

```powershell
$py = '.\.venv\Scripts\python.exe'
$split = 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80'
# Thay MODEL_ID_DA_XAC_MINH, không chạy nguyên placeholder.
& $py -X utf8 reproduce/research/judge_2wiki.py --questions "$split/internal_dev.csv" --gold "$split/internal_dev_gold.jsonl" --answers runs/2wiki/modal/baseline-dev-s101-c4/C0_s101/answers.jsonl --out runs/2wiki/judge/baseline-dev-s101 --model MODEL_ID_DA_XAC_MINH
```

Mặc định chỉ kiểm input và in số lượt. Thêm `--execute` để gọi Gemini; thêm
`--resume` nếu chạy tiếp cùng dữ liệu/model/rubric. Bộ chấm yêu cầu khớp chính xác
ID giữa questions/gold/answers; smoke20 phải dùng gold chỉ chứa đúng 20 ID đó.
Không dùng CSV của phased runner vì CSV này không giữ query_id; answers.jsonl có ID.

Kết quả: `judge.jsonl`, `requests.jsonl`, `per_question.csv`; chỉ xuất summary khi
mọi phán quyết hoàn tất. Đọc tay smoke để kiểm aliases/rubric trước lô lớn.
401 câu × 3 = 1.203 lượt chấm nominal. Không phân loại judge_failed/parse_failed
thành câu trả lời sai hoặc neither. Chỉ dùng 401 câu dev cho failure taxonomy.

## 6. Đánh giá cuối

Đóng băng phương pháp rồi mới chạy baseline/proposed trên 1.599 câu held-out.
Giữ cùng dữ liệu, model và ngân sách context, lặp lượt sinh, chấm mỗi lượt ba lần.
Báo đủ acc/err/neither, McNemar b/c/p, token và thời gian. Không coi bảng bài báo
là đối chứng trực tiếp và không tuyên bố hiệu quả khi chưa có số đo.

Để dừng deployment của chính bạn khi hết dùng:

```powershell
& $py -m modal app stop minirag-slm
```

Không dừng App nếu người khác đang chạy thí nghiệm. GPU hiện có scaledown 300 giây;
pha CPU không có nghĩa GPU đã dừng tính phí ngay.
