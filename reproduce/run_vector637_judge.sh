#!/bin/zsh
# Chấm ablation vector thuần khi QA xong, và SAU chuỗi chấm lặp V3 để hai lượt không tranh quota
# Gemini. Trước khi chấm: kiểm context-log của lượt chạy khớp A1(top-30 vector) tính offline --
# kết quả chỉ tính khi kiểm này ĐẠT (đăng ký trước trong ROADMAP). So với baseline, V3 gốc (phép
# so chính) và hai lượt lặp V3.
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1 GEMINI_RPM=13 GEMINI_TPM=3000
unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_ANSWER_TYPE_FIX \
      MINIRAG_PATH2CHUNK_FIX MINIRAG_CHUNK_CUT MINIRAG_CHUNK_FUSION MINIRAG_CONTEXT_LOG \
      MINIRAG_MAX_TOKEN_TEXT_UNIT MINIRAG_SLM_MODEL
S=/private/tmp/claude-501/-Users-hunggoodboy-Documents-HTTM-TK-MiniRAG-HTTM/98feb849-7098-448d-a4e3-1eadc18112bd/scratchpad
until grep -q "STAGE: QA_vec_DONE" logs/vector637_qa.log 2>/dev/null; do sleep 300; done
until grep -q "STAGE: ALL_DONE" logs/v3_replicates_judge.log 2>/dev/null; do sleep 300; done

echo "=== STAGE: CHECK_CTX_vec === $(date '+%d/%m %H:%M')"
# Bản sao index: khởi tạo MiniRAG ghi log vào working dir, không để nó chạm index thật.
rm -rf $S/qwen_index_check && cp -R ./LiHua-World-qwen-modal $S/qwen_index_check
.venv/bin/python reproduce/check_vector_ctx.py --workingdir $S/qwen_index_check \
    --ctxlog ./logs/qwen637_vec_ctx.jsonl 2>&1 | grep -v -E "^INFO|Query:" | tee ./logs/check_vector_ctx.txt

echo "=== STAGE: JUDGE_vec === $(date '+%d/%m %H:%M')"
until .venv/bin/python reproduce/Step_2_evaluate.py --inputpath ./logs/qwen637_vec.csv --repeats 3; do
  echo "=== chưa đủ quota / còn câu lỗi, chờ 20 phút === $(date '+%H:%M')"; sleep 1200
done
.venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_fix_judged.csv \
    --new ./logs/qwen637_vec_judged.csv --ctx ./logs/qwen637_vec_ctx.jsonl \
    --label vec | tee ./logs/compare_vec.txt
for r in v3 v3_r2 v3_r3; do
  [ -f ./logs/qwen637_${r}_judged.csv ] || continue
  .venv/bin/python reproduce/compare_variants.py --base ./logs/qwen637_${r}_judged.csv \
      --new ./logs/qwen637_vec_judged.csv --ctx ./logs/qwen637_vec_ctx.jsonl \
      --basectx ./logs/qwen637_${r}_ctx.jsonl --label vec | tee ./logs/compare_vec_vs_${r}.txt
done
echo "=== STAGE: ALL_DONE === $(date '+%d/%m %H:%M')"
