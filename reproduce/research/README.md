# `reproduce/research/` — công cụ của đợt Qwen trên dataset mới

Bản đồ các script theo từng bước. **Không đổi tên hay chuyển chỗ các file này:** code Phase 3 và các nhánh 2Wiki nạp chúng
theo đường dẫn, và nhiều manifest ghi sha256 của chúng.

- MultiHop-RAG: kế hoạch và sửa đổi ở [`docs/research/multihop_rag/`](../../docs/research/multihop_rag/MULTIHOP_RAG_ROADMAP.md),
  kết quả ở [`results/multihop_rag/`](../../results/multihop_rag/README.md).
- Protocol dùng chung với 2Wiki: [`docs/research/PROTOCOL_QWEN_NEW_DATASETS.md`](../../docs/research/PROTOCOL_QWEN_NEW_DATASETS.md).
- Test offline: `python -m unittest discover tests/research` (không gọi mạng).
- Trên Windows luôn đặt `PYTHONUTF8=1`.

## Dùng chung cho mọi dataset

| File | Làm gì |
|---|---|
| [`serving_qwen_modal.json`](serving_qwen_modal.json) | Cấu hình Qwen đã ghim (revision, vLLM, dtype, sampling) |
| [`slm_smoke.py`](slm_smoke.py) | Kiểm endpoint Qwen trên Modal trước mỗi lượt tốn tiền |
| [`llm_trace.py`](llm_trace.py) | Ghi metadata từng request HTTP (model trả về, `finish_reason`, token) mà không sửa `minirag/` |
| [`index_run.py`](index_run.py) | Index bằng Qwen: chặn Gemini, chỉ ghi vào `indexes/<dataset-id>-*`, resume theo lô, kiểm 6 liên kết |
| [`phased_qa.py`](phased_qa.py) | QA 3 pha: từ khoá (GPU) → truy hồi (CPU) → sinh (GPU); cấu hình C0–C3, C_orig |
| [`judge_run.py`](judge_run.py) | Chấm 3 lượt Gemini, hợp đồng nhãn chặt, đa số + mean ± sd, phiếu trống (S4) |
| [`compare_mhr.py`](compare_mhr.py) | Phép so ghép cặp đã đăng ký: McNemar, bootstrap 10.000 lần, biên −3 |
| [`qa_run.py`](qa_run.py), [`benchmark_qa.py`](benchmark_qa.py), [`QA_PARALLEL.md`](QA_PARALLEL.md) | Runner QA song song kiểu một tiến trình (có trước 3 pha); các script khác dùng lại hàm tiện ích của nó |

## MultiHop-RAG theo thứ tự chạy

| Bước | File | Đầu ra |
|---|---|---|
| 1. Chuẩn hoá dữ liệu | [`prepare_multihop_rag.py`](prepare_multihop_rag.py) | `dataset/MultiHop-RAG/processed/` |
| 2. Đếm chunk | [`count_mhr_chunks.py`](count_mhr_chunks.py) | `processed/chunk_stats.json` |
| 3. Chia dev / test | [`make_mhr_split.py`](make_mhr_split.py) | `dataset/MultiHop-RAG/splits/` |
| 4. Index | `index_run.py` (ở trên) | `indexes/multihop_rag-qwen-full609/` |
| 5. Ánh xạ evidence → chunk | [`map_mhr_evidence.py`](map_mhr_evidence.py) | `processed/gold_chunks.jsonl` |
| 6. Dev 400: QA + chấm | [`run_phased_dev.sh`](run_phased_dev.sh) (gọi `phased_qa.py`, `judge_run.py`) | `runs/multihop_rag/dev400/` |
| 7. Phân tích dev | `compare_mhr.py` | `results/multihop_rag/dev400/` |
| 8. Phase 3 (test 2.156 câu) | [`mhr_phase3/`](mhr_phase3/): `validate.py` (kiểm context dùng chung khớp dev) → `pipeline.py --execute-test` (producer/consumer, `judge_worker.py`) → `analysis.py` | `runs/multihop_rag/test_phase3/`, báo cáo |
| 8a. Vận hành Phase 3 | [`recover_mhr_phase3_windows.py`](recover_mhr_phase3_windows.py), [`mhr_phase3_fair_judge.py`](mhr_phase3_fair_judge.py), [`mhr_phase3_handoff.py`](mhr_phase3_handoff.py) | khôi phục / hàng đợi chấm / bàn giao tiến trình |
| 8b. Sửa đổi A1 + báo cáo | [`mhr_phase3_structured_rejudge.py`](mhr_phase3_structured_rejudge.py), [`MHR_PHASE3_STRUCTURED_REJUDGE.txt`](MHR_PHASE3_STRUCTURED_REJUDGE.txt), [`mhr_phase3_amended_analysis.py`](mhr_phase3_amended_analysis.py), [`plot_mhr_phase3_report.py`](plot_mhr_phase3_report.py) | `results/multihop_rag/phase3_test/` |

Hướng dẫn Phase 3 đầy đủ: [`docs/research/multihop_rag/MHR_PHASE3_ACCELERATION.md`](../../docs/research/multihop_rag/MHR_PHASE3_ACCELERATION.md).

## Đã thay thế — giữ làm hồ sơ, không dùng nữa

| File | Thay bằng | Lý do giữ |
|---|---|---|
| [`run_mhr_qa.sh`](run_mhr_qa.sh) | `phased_qa.py` (sửa đổi S2) | hồ sơ của lượt smoke C0 một tiến trình |
| [`shard_mhr_qa.py`](shard_mhr_qa.py) | `phased_qa.py` (S2) | hồ sơ của sửa đổi S1 (8 shard, hỏng vì hết RAM) |
