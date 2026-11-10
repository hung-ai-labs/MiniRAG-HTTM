# C0 so với C0+V_t — LiHua 435, Qwen và Phi

Ngày 10/11/2026. Chạy từ Git Bash tại `E:/Project/MiniRAG/.worktrees/temporal`. **Từng lệnh tuần tự; một job offline mỗi lúc.** Không index lại, không sửa `.env`, không dùng index Gemini. Dừng nếu cổng báo lỗi; mỗi model sinh sau khi cả ba seed của chính model đó qua cổng. Bản đăng ký: `../TEMPORAL_REGISTRATION.md`, Sửa đổi 1–3. 435 câu Single 347 / Multi 43 / Null 45.

## 0. Kiểm tra CPU, nguồn đóng băng

```bash
cd /e/Project/MiniRAG/.worktrees/temporal
PY=/e/Project/MiniRAG/.venv/Scripts/python.exe
MODAL=/e/Project/MiniRAG/.venv/Scripts/modal.exe
$PY -m unittest tests.test_temporal_acc -v
$PY reproduce/graph_repair/acc/run.py prepare --model qwen
$PY reproduce/graph_repair/acc/run.py prepare --model phi
```

`prepare` chỉ sao chép ba keyword cache mỗi model vào `runs/lihua_world/temporal_acc/{qwen,phi}/`; không ghi index. Nó kiểm 435 câu, hash CSV, hash keyword, fingerprint index và baseline contexts. Nguồn Qwen: `E:/Project/MiniRAG/runs/lihua_world/flow_v1/L-C0R_s*`, index `E:/Project/MiniRAG/LiHua-World-qwen-modal`. Nguồn Phi: `E:/Project/MiniRAG/.worktrees/lihua-phi-rope/runs/lihua_world/phi_rope/L-C0_s*`, index `.../lihua-phi-rope/indexes/lihua_world-phi-rope-modal`. Mỗi seed có cache `kw_s{seed}.jsonl` riêng. Tuyệt đối không chạy pha `keywords`.

## 1. Context trên CPU và hồi quy — chưa triển khai GPU

```bash
for model in qwen phi; do
  for seed in 101 202 303; do
    $PY reproduce/graph_repair/acc/run.py contexts --model "$model" --seed "$seed" --arm L-C0
    $PY reproduce/graph_repair/acc/run.py contexts --model "$model" --seed "$seed" --arm L-T
  done
  $PY reproduce/graph_repair/acc/run.py gate --model "$model"
done
```

`L-C0` đặt `MINIRAG_TEMPORAL=0`, `L-T` đặt `=1`; `PYTHONHASHSEED=13`, `EXPAND=1`, `H=0`. Chạy lại cùng lệnh để resume. Cổng đòi **435/435** context string/status C0 bằng baseline từng byte mỗi seed và mọi context L-T thay đổi phải nằm trong tập parser fires. `gate_s*.json` lưu danh sách parser fires và context changed. Parser hiện nhận **44/435** câu trên corpus 2026, hơi cao hơn dự kiến ≈35: kiểm danh sách trước GPU. File JSONL có `retrieval_s` biến thiên; so từng byte của **context**, không so timestamp/latency của record.

Danh sách 44 ID từ parser offline (Qwen/Phi đều có corpus year 2026): `lh-0024, lh-0031, lh-0047, lh-0090, lh-0092, lh-0100, lh-0102, lh-0113, lh-0116, lh-0129, lh-0130, lh-0131, lh-0132, lh-0134, lh-0135, lh-0136, lh-0139, lh-0140, lh-0148, lh-0149, lh-0151, lh-0153, lh-0160, lh-0175, lh-0178, lh-0179, lh-0181, lh-0182, lh-0190, lh-0211, lh-0212, lh-0221, lh-0223, lh-0254, lh-0265, lh-0354, lh-0355, lh-0393, lh-0402, lh-0412, lh-0416, lh-0418, lh-0427, lh-0429`. Đây là *parser fires*, không phải danh sách context thực sự đổi; cổng sẽ ghi danh sách thứ hai sau khi chạy CPU.

Thời gian tham chiếu: log Phi `g4a_g5.log` 07/11 ghi L-C0 s101 20 phút lúc tải lạnh, s202 7 phút, s303 7 phút với 6 workers. Ước 6 arm Phi 45–90 phút, 6 arm Qwen 60–120 phút với 3 workers, tổng CPU khoảng 2–4 giờ tùy RAM/cache. Chạy tuần tự để không tranh tài nguyên với phiên khác.

## 2. Qwen — Modal A10G, G1 và sinh

Trước **mỗi bước GPU**, chạy guard trong nền: `MODAL_PROFILE=nguyenhuuanhtai426 sh reproduce/modal_budget_guard.sh 30 1.0 300`. Guard dùng profile này và dừng app khi chạm hạn mức. Không chạy đồng thời job GPU khác. Phi và Qwen chạy thành **hai session riêng**, nhưng hai arm của cùng SLM cùng deployment/URL trong một session. Bản Qwen dùng `serving_qwen_modal.json` gốc; ước G1 khởi động 3–6 phút, ~$0,05–0,15; 6×435 câu sinh khoảng 35–60 phút, ~$0,8–1,5 (A10G, ước theo các đợt Qwen và log Phi; kiểm billing thực tế).

```bash
MODAL_PROFILE=nguyenhuuanhtai426 sh reproduce/modal_budget_guard.sh 30 1.0 300 > runs/lihua_world/temporal_acc/qwen/guard.log 2>&1 & QGUARD=$!
MODAL_PROFILE=nguyenhuuanhtai426 SLM_SERVING=reproduce/research/serving_qwen_modal.json "$MODAL" deploy reproduce/modal_slm.py
read -r -p 'Dán URL HTTPS của app Qwen vừa deploy: ' QWEN_URL
MINIRAG_SLM_URL="$QWEN_URL" $PY reproduce/graph_repair/acc/run.py smoke --model qwen
for seed in 101 202 303; do
  for arm in L-C0 L-T; do
    MINIRAG_SLM_URL="$QWEN_URL" $PY reproduce/graph_repair/acc/run.py answers --model qwen --seed "$seed" --arm "$arm"
  done
done
MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" app stop -y minirag-slm
kill "$QGUARD"
MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" billing report --for today
```

Nếu bất kỳ bước nào lỗi: **dừng app ngay** bằng `MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" app stop -y minirag-slm`, xem log rồi chạy lại lệnh bị lỗi. G1 `slm_smoke.py` phải đạt 3 check; lúc cold start có thể thấy HTTP 303/500/408, thử lại tối đa 3 lần và lưu từng kết quả riêng trước khi ghi đè `g1_smoke.json`. `run.py` từ chối generation nếu thiếu G1/cổng context, sai URL trong cùng session, thiếu khóa, hoặc sai model trên endpoint. Khóa SLM lấy từ biến môi trường hoặc đọc `E:/Project/MiniRAG/.env` (chỉ đọc); nếu secret tài khoản mới khác, đặt `MINIRAG_SLM_KEY` trong môi trường shell. URL **luôn truyền bằng `MINIRAG_SLM_URL` từng lệnh**, không sửa `.env`.

## 3. Phi — Modal A100-80GB, RoPE tĩnh, G1 và sinh

File `serving_phi_rope_modal.json` chứa revision, alias `phi35-static-longrope`, override RoPE và sampling cũ. G1 3–6 phút; 6×435 câu sinh khoảng 45–65 phút. Log Phi 07/11: 9 arm trả lời từ 17:02 đến ~18:08, chi phí smoke + QA 3,90 USD; suy ra lần này khoảng **2,6–3,4 USD** gồm G1. Không gọi kết quả là Phi gốc vì RoPE tĩnh là can thiệp đã đăng ký.

```bash
MODAL_PROFILE=nguyenhuuanhtai426 sh reproduce/modal_budget_guard.sh 30 1.0 300 > runs/lihua_world/temporal_acc/phi/guard.log 2>&1 & PGUARD=$!
MODAL_PROFILE=nguyenhuuanhtai426 SLM_SERVING=reproduce/research/serving_phi_rope_modal.json "$MODAL" deploy reproduce/modal_slm.py
read -r -p 'Dán URL HTTPS của app Phi vừa deploy: ' PHI_URL
MINIRAG_SLM_URL="$PHI_URL" $PY reproduce/graph_repair/acc/run.py smoke --model phi
for seed in 101 202 303; do
  for arm in L-C0 L-T; do
    MINIRAG_SLM_URL="$PHI_URL" $PY reproduce/graph_repair/acc/run.py answers --model phi --seed "$seed" --arm "$arm"
  done
done
MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" app stop -y minirag-slm-phi-rope
kill "$PGUARD"
MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" billing report --for today
```

Khi lỗi, stop: `MODAL_PROFILE=nguyenhuuanhtai426 "$MODAL" app stop -y minirag-slm-phi-rope`. Tổng GPU hai SLM ước **~1,5–2,2 giờ và 3,5–5,1 USD** gồm smoke, chưa tính biến động cold start, scale-down và billing lag. Hai deployment dùng cùng profile và secret có sẵn; volumes `create_if_missing`.

## 4. CRN và chấm có chia sẻ verdict — theo từng model

Sau khi đủ 6 file answers.csv/answers.jsonl của **Qwen** (hoặc Phi), dựng L-TC cho ba seed. Mỗi câu trong `context_changed` lấy answer L-T; các câu khác lấy nguyên dòng L-C0. Cổng yêu cầu baseline 435/435, đủ 435 ID và CSV khớp JSONL. `crn_manifest.json` ghi số câu lấy từ từng arm và SHA256 đầu vào. Lệnh không sửa L-C0/L-T.

```bash
for seed in 101 202 303; do
  $PY reproduce/graph_repair/acc/run.py crn --model qwen --seed "$seed"
done
$PY reproduce/graph_repair/acc/share_judge.py prepare --model qwen
$PY reproduce/graph_repair/acc/share_judge.py run --model qwen
```

`prepare` cũng tự dựng/kiểm L-TC. Đầu vào chính đóng băng tại `judge_shared/qwen/{questions.csv,answers.csv,mapping.json}`; thay `qwen` bằng `phi` để chấm Phi ngay khi Phi xong. `--model all` xử lý cả hai khi đều đủ. `run` gọi **đúng `judge_run.py` gốc**: `gemini-3.5-flash-lite`, prompt V1 từ `Step_2_evaluate.py`, 3 pass, seed 13, strict labels, `--invalid-tries 3 --abstain-after 3`. Lệnh có thể trả incomplete do `parse_failed`/quota; chạy lại **cùng lệnh** để resume, không xóa journal. Kiểm `judge_shared/qwen/judge/summary.json` có `status=completed`.

Qwen chính: 435 C0 × 3 seed + khoảng 41 TC khác C0 × 3 seed, nhân 3 pass ≈ **4.284 lượt gọi** trước khi trừ trùng text giữa seed/câu. `prepare` in chính xác `calls_with_sharing` và `calls_saved`. Số request retry thực tế có thể cao hơn.

Chấm xem trước **chỉ câu context đổi của seed 101**, có thể chạy ngay khi C0 và L-T s101 đã hoàn tất, tách khỏi phân tích chính:

```bash
$PY reproduce/graph_repair/acc/share_judge.py prepare --model qwen --only-changed
$PY reproduce/graph_repair/acc/share_judge.py run --model qwen --only-changed
```

Đầu ra `judge_preview/qwen/` là **PREVIEW**, không được `analyze.py` đọc. Chỉ xem trước, không dùng để quyết định. Phân tích phụ phép so L-T thô dùng `--include-raw-lt` ở cả hai lệnh `prepare` và `run`; judge riêng tại `judge_shared/qwen/with_raw_lt/` để không thay đổi run chính. Có thể thêm sau khi run chính đã hoàn tất.

## 5. Phân tích offline

```bash
$PY reproduce/graph_repair/acc/analyze.py --model qwen
```

Đọc `runs/lihua_world/temporal_acc/qwen/ANALYSIS.md` và `.json`: primary **L-TC vs L-C0**, 435 câu mỗi seed, acc/err/neither majority và mean±sd ba pass, b/c/p McNemar chính xác **acc riêng, err riêng**, nhóm changed/unchanged và Single/Multi/Null. Nhóm unchanged phải có 0 cặp lệch theo cấu trúc CRN; code sẽ từ chối nếu khác. Khi có verdict L-T từ `--include-raw-lt`, báo secondary L-T thô vs L-C0. Quy tắc đăng ký: ba seed cùng chiều, p<0,05 mỗi seed cho acc; báo err theo cùng chuẩn, và chỉ gọi thắng nếu acc tăng cùng err giảm. Khi cả Qwen và Phi hoàn tất, `--model all` còn viết `temporal_acc/ANALYSIS.md/.json` gộp hai báo cáo, không gộp seed/model thành câu độc lập.

## Sai khác tooling

Các file `reproduce/research/{qa_run,llm_trace,judge_run,judge_session,analyze_lihua_ablation,slm_smoke,compat_gate,kw_gate,launch_detached,run_phased_grouped,run_phased_dev}` và hai serving JSON được sao y từ worktree Phi 07/11; `modal_slm.py` cũng sao y để hỗ trợ Phi. `gemini_common.py` sao y bản Phi vì bản cũ ở đây thiếu tham số `llm_max_async` mà `phased_qa.py` yêu cầu (sai khác 9 dòng, mặc định các script cũ vẫn 8). `phased_qa.py` chỉ thêm tên arm `L-T` dùng fusion C0, map `MINIRAG_TEMPORAL=1` và ép C0 `=0`, cùng nhãn đăng ký mới; không sửa pha A/B/C, prompt, sampling, retry, thứ tự hay kết quả cũ. Worktree giữ `minirag` temporal của nó; `operate.py` ở đây có thêm nhánh temporal và các nhánh graph repair opt-in so với Phi, đều bị ép tắt ở C0/L-T trừ temporal. `run.py`, `share_judge.py`, `analyze.py` là wrapper/cổng mới; `modal_budget_guard.sh` sao y từ root. CSV 435 sao y từ Phi, hash `72da5461…`. Pha context **chưa chạy trong bước chuẩn bị này**; hồi quy 435/435 là cổng tương lai, chưa phải kết quả đã đạt.
