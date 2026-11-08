# Tích hợp acceleration vào 2Wiki — 30/10/2026

Theo yêu cầu người dùng, đã chuyển có chọn lọc cơ chế từ nhánh
`origin/codex/mhr-phase3-acceleration`, head `ae52921`; commit `e62e7ed` là mốc
đóng gói được đồng đội gửi trong ảnh. Không merge toàn bộ lịch sử/corpus/kết quả
MultiHop-RAG vào nhánh hiện tại. Vì vậy Git ancestry của nhánh upstream vẫn là
chưa merge; code cần cho 2Wiki đã được port và điều chỉnh tại workspace này.

## Phần nhận và điều chỉnh

| Thành phần | Nguồn / thay đổi |
|---|---|
| `two_wiki_acceleration/shared_context.py` | Port adapter AST, paired_query và CPU worker từ upstream; giữ nguyên thuật toán truy hồi. Thêm source/runtime identity và bắt buộc Hugging Face offline. |
| `two_wiki_acceleration/common.py` | Port hash/runtime/helpers; đổi output sang 2Wiki và dùng OS lock đã có để chống hai writer cùng lúc. |
| `two_wiki_acceleration/validate.py` | Port chạy worker/đối chiếu; dùng đúng dev401, index/keyword/reference truyền rõ, CPU worker có thể chọn. |
| `two_wiki_acceleration/pipeline.py` | Điều phối riêng 2Wiki: keyword GPU → paired contexts CPU → answer GPU, theo seed; có giới hạn thời gian các pha GPU. |
| `two_wiki_acceleration/judge_worker.py` | Một consumer Gemini sống qua các seed; chấm C0 rồi C1 cùng seed khi producer chuẩn bị seed tiếp. Dùng aliases/rubric của `judge_2wiki.py`, không áp model judge MHR. |

Mỗi query/seed tính phần đồ thị chung một lần, sao chép trạng thái trước khi tạo
Sources riêng cho C0/C1. Keyword parser vẫn thực thi cho từng cấu hình nhưng chỉ
đọc cache, không gọi LLM ở pha CPU. Không giữ cache truy hồi qua query/seed khác.
Các cờ path pruning/reranking bên ngoài phạm vi được từ chối để tránh chia sẻ sai.

## Cổng kiểm tra trước chạy thật

Đã có kiểm thử fixture với LLM/embedding giả: context, thứ tự Sources/Entities,
prompt, log canonical (chỉ bỏ trường thời gian), early exit, checkpoint, đổi seed,
thứ tự chấm, aliases, resume và chế độ plan không mở nhãn test.
Kiểm tra sau tích hợp: **103 test trong tests/research đạt** trên Python 3.13.5
với Hugging Face/Transformers offline (23,10 giây). Entry point mặc định đã chạy
thành công ở chế độ plan, không gọi API/GPU. Chưa có phép đo live trên 2Wiki.

Đây chưa phải kiểm chứng trên corpus 2Wiki thật. Muốn thực thi pipeline tối ưu,
phải có **index Modal hoàn tất**, keyword cache và reference C0/C1 trên toàn dev401.
Validator phải đối chiếu **802 context** không sai khác, không gọi LLM. Smoke nhỏ
không mở khóa pipeline; đổi source/runtime/index/keyword/reference làm mất hiệu
lực validation. Test nội bộ còn cần `--method-frozen` sau khi chốt phương pháp.

## 1. Xem kế hoạch ngay, không dùng GPU/API

Tại gốc repo:

```powershell
python -m reproduce.research.two_wiki_acceleration.pipeline
```

Mặc định: dev401, C0/C1, seed 101/202/303, một CPU worker, GPU concurrency 4,
chưa bật judge. Lệnh chỉ đọc metadata split và in plan. Không đọc `.env`, không
đọc câu hỏi/nhãn test, không tạo endpoint, không tải model.

## 2. Chuẩn bị reference context bằng runner cũ

Sau khi xong thiết lập Modal, pilot và full index trong RUN_2WIKI_DEV20_TEST80.md:

```powershell
$idx = 'indexes/2wiki-modal-n2000-s13-dev20test80'
$dev = 'dataset/2WikiMultiHopQA/processed/splits/n2000_s13_dev20_test80/internal_dev.csv'
$serving = 'configs/research/2wiki/serving_modal.json'
$protocol = 'docs/research/RUN_2WIKI_DEV20_TEST80.md'
$ref = 'runs/2wiki/acceleration/reference-dev401-s101'
```

Bước keyword dưới đây gọi GPU thật. Hai bước contexts chỉ dùng CPU và embedding
local, yêu cầu keyword cache hoàn chỉnh; giữ cùng một worker để đối chiếu.

```powershell
python reproduce/research/phased_qa.py keywords --dataset-id 2wiki --index $idx --questions $dev --registration $protocol --serving-config $serving --out $ref --seed 101 --llm-max-async 4
python reproduce/research/phased_qa.py contexts --config C0 --dataset-id 2wiki --index $idx --questions $dev --registration $protocol --serving-config $serving --out $ref --seed 101 --llm-max-async 4 --workers 1
python reproduce/research/phased_qa.py contexts --config C1 --dataset-id 2wiki --index $idx --questions $dev --registration $protocol --serving-config $serving --out $ref --seed 101 --llm-max-async 4 --workers 1
```

Không cần sinh answer để tạo reference context. Dùng thư mục mới để giữ các lượt
baseline đã có. C0 và C1 ở đây là hai cấu hình retrieval đã định nghĩa trong repo,
không coi việc đổi runner là Proposed Method khoa học mới.

## 3. Kiểm tương đương trên 2Wiki thật — CPU, không gọi LLM

```powershell
python -m reproduce.research.two_wiki_acceleration.validate --index $idx --keywords "$ref/kw_s101.jsonl" --reference $ref --workers 1
```

Mặc định báo cáo ở `runs/2wiki/acceleration/DEV_CONTEXT_VALIDATION.json`.
Thêm `--limit 20 --out runs/2wiki/acceleration/validation-smoke20 --status runs/2wiki/acceleration/VALIDATION_SMOKE20.json`
để thử nhỏ; report này không đủ mở khóa thực thi chính thức.
Embedding model phải có trong cache, workers không tự tải từ Hugging Face.

## 4. Chạy QA và chấm gối sau khi đã chọn ngân sách/model judge

Chạy plan trước với model ID Gemini đã được xác minh cho project free tier của
bạn. Tham số dưới đây là placeholder, không tự chọn Flash-Lite thay Flash:

```powershell
python -m reproduce.research.two_wiki_acceleration.pipeline --judge-model MODEL_ID_DA_XAC_MINH
```

Để chạy thật, bổ sung `--execute --gpu-stage-budget-seconds SO_GIAY_DA_CHON`.
SO_GIAY_DA_CHON là tổng thời gian wall của các pha keyword/answer trong đợt, bao
gồm các lần thất bại. Đây là guard thời gian local, **không phải hard cap tiền
Modal**. GPU ấm còn có thể tính phí trong pha CPU và sau khi client dừng; không
tự dừng App vì có thể đang được người khác sử dụng. Theo dõi Billing thực tế.

Consumer giữ cùng key pool Gemini qua các seed; không tăng RPM/TPM. Không có
`--judge-model` thì chỉ chạy QA. Mỗi lần consumer chấm đủ ba lượt cho C0 rồi C1
của seed hiện tại; chỉ bắt đầu sau marker READY của cả cặp. Không đọc answer dở
để chấm. Nếu chấm còn lỗi parse/API, pipeline báo lỗi thay vì coi là hoàn tất.
Chạy lại đúng lệnh để resume; identity đổi bị từ chối. Stage GPU bị mất end marker
phải đối soát trước khi resume, không tự xóa budget để chạy lại.

Khi phương pháp đã chốt và đủ validation, chạy test bằng `--partition test
--method-frozen --out runs/2wiki/acceleration/test` cùng các tham số còn lại.
Các file dev/test đúng split401/1599; không lấy số 400/2156 của MHR.

## Đầu ra và giới hạn

- `<out>/qa/s101/kw_s101.jsonl`: keyword cache; C0/C1 dùng chung trong seed.
- `<out>/qa/s101/C0_s101/` và `C1_s101/`: context, answer, trace tương thích runner cũ.
- `<out>/judge/C0_s101/` và `C1_s101/`: ba lượt chấm và summary theo ID/aliases.
- `STATUS.json`, `JUDGE_STATUS.json`, `RUN_MANIFEST.json`, `GPU_BUDGET.json`:
  tiến độ, identity và ngân sách thời gian. Không ghi key hoặc URL endpoint thô.
- Adapter/runner chỉ ghi snapshot, không sửa index nguồn hoặc index LiHua.

Chưa chạy Modal/Gemini hoặc đo chi phí 2Wiki trong đợt tích hợp này. Không áp
tỷ số thời gian MHR sang 2Wiki. Thời gian truy hồi dùng chung phải báo riêng;
không lấy suffix C1 đã tái dùng làm latency truy hồi độc lập. Chồng lấp chấm với
QA giúp giảm thời gian toàn đợt nhưng không tự làm giảm số token/lượt chấm.
Metrics vẫn dùng `reproduce/research/metrics.py`; không kéo báo cáo khoa học MHR
sang 2Wiki. Cần đo chất lượng rubric trên smoke và chốt serving/model trước khi
coi đây là benchmark hoàn chỉnh.
