# Runner GPU dùng chung cho 2Wiki

Cập nhật 27/10/2026. Đọc cùng [bàn giao 2Wiki](HANDOFF_2WIKI_QWEN.md).
Đây là hướng dẫn hạ tầng; protocol và split của 2Wiki vẫn do người phụ trách chốt.

## Nhận code và giữ điều kiện thí nghiệm

PR nhắm vào `dev`, lấy runner dùng chung từ MultiHop-RAG, không đưa corpus, index hoặc kết quả MultiHop vào nhánh bạn.
Sau khi PR merge, cập nhật `origin/dev` vào nhánh `research/2wiki-qwen` theo quy trình Git của nhóm.
Các file `prepare_2wiki.py`, `materialize_2wiki_pool.py`, `local_qwen.py`, `local_index_pilot.py`, `metrics.py`,
config và artifact local của bạn không bị thay thế.

Đã kiểm nhánh 2Wiki tại `0d7a18c`: pool 2.000 câu đã materialize, split 80/20 còn là ứng viên;
pilot Ollama Qwen2.5-3B **Q4_K_M** mới chạy 10/200 tài liệu. Những dữ liệu này không đồng nghĩa đã có index Modal.

- Giữ pilot local để làm bằng chứng. Nếu tiếp tục local, dùng adapter/runner local của nhánh bạn.
- Nếu chọn đường Modal/bf16, tạo **index mới bằng chính Qwen trên Modal**. Không resume index Q4 vào runner Modal.
- Không cần dựng lại một index Modal đã hoàn tất và được xác minh chỉ vì đổi runner QA.
- Khai báo model revision, vLLM, dtype, GPU, context và sampling thực tế. File
  `reproduce/research/serving_qwen_modal.json` chỉ là tham chiếu MHR; provenance trong đó có phần suy ra.
  Sao chép vào file riêng của 2Wiki sau khi kiểm deployment, không coi khai báo là xác minh từ xa.
- Không dùng toàn bộ pool làm smoke nếu split/internal-test chưa được chốt. Chuẩn bị CSV nhỏ từ phần dev được phép xem.

## Bộ code nhận được

| File | Việc |
|---|---|
| `qa_run.py` | QA song song có giới hạn, snapshot index, manifest, checkpoint, resume |
| `phased_qa.py` | A từ khóa trên GPU → B context trên CPU → C trả lời trên GPU |
| `run_phased_qa.py` | Điều phối đa cấu hình trên Windows/Linux; mặc định chỉ in lệnh |
| `index_run.py` | Index theo lô, sửa checkpoint của lô bị ngắt, kiểm doc/chunk/vector/graph |
| `llm_trace.py` | Ghi token, model, finish reason, lỗi và latency; không ghi token truy cập/URL |
| `slm_smoke.py` | Kiểm deployment Modal bằng ba request; bước này có dùng GPU thật |
| `benchmark_qa.py` | Chuẩn bị phép đo throughput của runner QA; chỉ thực thi khi thêm `--execute` |

Nhánh `dev` đã có `modal_slm.py` và `slm_env.sh`. Sửa limiter trong PR bảo đảm lời gọi lỗi/hủy vẫn trả lại slot.
`build_rag()` mặc định vẫn là 8; runner mới truyền mức song song riêng.

## Kiểm offline trước

Chạy từ gốc repo trong PowerShell; thay đường dẫn Python nếu môi trường của bạn khác:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -X utf8 -m unittest discover -s tests/research -p "test_qa_parallel.py" -v
& $py -X utf8 -m unittest discover -s tests/research -p "test_phased_qa.py" -v
& $py -X utf8 -m unittest discover -s tests/research -p "test_index_run.py" -v
```

Các test tạo index giả tạm thời, dùng LLM/embedding giả, không gọi Modal/Gemini.
Chúng kiểm nội dung request tương đương với MiniRAG, pha CPU cấm gọi LLM, resume và bảo vệ index nguồn.
Vẫn cần smoke thật trên dữ liệu 2Wiki trước benchmark; test giả không chứng minh các đầu ra lấy mẫu sẽ giống nhau.

## Chọn cấu hình và chuẩn bị endpoint

Trong shell chạy Modal, dùng `.env` bị ignore với `MINIRAG_SLM_URL` và `MINIRAG_SLM_KEY` của deployment riêng.
Hai biến này khác key Gemini của judge. Không đưa key vào tài liệu, commit hoặc artifact.

Chỉ khi đã chọn và triển khai Modal, kiểm endpoint bằng:

```powershell
& $py -X utf8 reproduce/research/slm_smoke.py --serving <SERVING_2WIKI.json> --out runs/2wiki/serving/smoke.json
```

Lệnh trên khởi động GPU nếu đang tắt và có chi phí. Không được thực thi trong bước test offline.
Mỗi đợt giữ cùng deployment và cùng mức song song giữa các cấu hình.

## Index nếu chưa có index Modal

`docs.jsonl` từ `materialize_2wiki_pool.py` đã có `doc_id`, `minirag_doc_id`, `text`, đúng schema runner.
Trước hết thử một nhóm tài liệu nhỏ; chọn đường dẫn mới để giữ pilot local và mọi index đã có.

```powershell
& $py -X utf8 reproduce/research/index_run.py --dataset-id 2wiki --docs <DOCS_2WIKI.jsonl> --subset pilot --pilot-size 20 --workingdir indexes/2wiki-modal-smoke20 --max-output-tokens 4096 --serving-config <SERVING_2WIKI.json> --llm-max-async 4 --batch-docs 4
```

Đây là lời gọi GPU thật. `4096` là trần index của phương án MHR và pilot local hiện có; người phụ trách 2Wiki phải ghi
nó vào protocol đã review. Kiểm `finish_reason`, node/cạnh và `verification` trước khi chạy corpus đầy đủ.
QA dùng trần riêng `1024`. Chạy lại đúng lệnh với `--resume` nếu ngắt; thay input/cap/serving sẽ bị từ chối.
`--verify` chỉ đọc index và không cần endpoint hoặc `--max-output-tokens`/`--serving-config`:

```powershell
& $py -X utf8 reproduce/research/index_run.py --dataset-id 2wiki --docs <DOCS_2WIKI.jsonl> --subset pilot --pilot-size 20 --workingdir indexes/2wiki-modal-smoke20 --verify
```

## QA: in kế hoạch trước, thực thi sau

CSV đầu vào cần `query_id,Question,Gold Answer` (có thể thêm `Type`), ID duy nhất. Các cột từ pipeline 2Wiki hiện tại đã khớp.
`--registration` phải trỏ tới protocol **của 2Wiki** đã review; runner lưu hash file, không tự coi nó đã được nhóm duyệt.
`--index` phải là index Modal của đúng corpus. Các dấu `<...>` dưới đây là placeholder, cần thay trên máy bạn.

```powershell
& $py -X utf8 reproduce/research/run_phased_qa.py --dataset-id 2wiki --index <INDEX_MODAL_2WIKI> --questions <SMOKE_DEV_2WIKI.csv> --registration <PROTOCOL_2WIKI.md> --serving-config <SERVING_2WIKI.json> --out runs/2wiki/modal/smoke-s101-c4 --seed 101 --configs C0 C1 --workers 1 --llm-max-async 4
```

Mặc định lệnh chỉ in JSON các bước A/B/C, không đọc key, tải model hay gọi API. Kiểm mọi `--index` trong kế hoạch đều là
index 2Wiki. Thêm `--execute` vào cùng lệnh để chạy GPU thật sau khi sẵn sàng; không tự động chạy judge.
Sau smoke, có thể chọn concurrency lớn hơn (tối đa 32) và số CPU worker theo RAM, nhưng dùng output directory mới và cùng
mức đó cho mọi cấu hình đối chứng. Pha B không gọi LLM; container Modal đang ấm vẫn có thể tính phí tới khi tự tắt
theo `scaledown_window=300`, nên không hiểu “CPU-only” là tắt GPU tức thì.

| ID runner | Ý nghĩa cho 2Wiki |
|---|---|
| C0 | GROUP_BASE (vá answer-type, Sources 4.000) |
| C1 | B2_FULL: C0 + RRF vector/BM25 |
| C2 | B2_NO_BM25: vector thuần |
| C3 | Naive RAG, chỉ mô tả; không cần pha từ khóa |
| C_orig | Gốc ở bước QA trên index đã vá; không tự coi là MR_FULL của bài báo |

Các ablation B2_NO_VECTOR, B2_NO_ENT, HYBRID_NO_GRAPH, MR_MINUS_* trong handoff chưa được runner này triển khai.
Đừng gán lại ID C0/C1… sang các phương pháp đó.

Mọi pha phải dùng cùng bộ đường dẫn, seed và concurrency. `run_manifest.json` lưu hash input/index/protocol/serving,
endpoint và source code; chạy tiếp khi đổi điều kiện bị từ chối. Cache từ khóa chỉ chia sẻ giữa các cấu hình trong cùng
run và seed. Index nguồn chỉ được đọc, các thao tác RAG ghi vào bản sao tạm.

Kết quả mỗi cấu hình ở `<out>/<config>_s<seed>/answers.csv`, kèm `answers.jsonl`, `contexts.jsonl`, `context.jsonl`,
`requests.jsonl` và `run_note.json`. Log request ghi riêng token và latency; không cộng thời gian các request song song
để suy ra số giờ GPU tính tiền. Pipeline ba pha đo throughput; latency người dùng phải đo riêng từng câu.

Judge và metrics dùng protocol 2Wiki đã chốt. Nhánh hiện tại yêu cầu Gemini Flash, exact ID còn chờ xác minh;
launcher này không tự thay bằng Flash Lite của MHR và không gọi judge. Các schema alias/rubric/log còn chờ review
trong `PROTOCOL_2WIKI_REVIEW.md` vẫn phải được xử lý trước khi công bố benchmark.
