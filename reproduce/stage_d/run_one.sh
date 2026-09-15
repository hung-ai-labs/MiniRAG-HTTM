#!/usr/bin/env bash
# Một lượt tầng D (ROADMAP): QA 435 câu ngoài dev với một chế độ trộn và một seed sinh, rồi chấm 1 lượt Gemini.
#   reproduce/stage_d/run_one.sh b1_s101 rrf_bm25 101 [file câu hỏi] [thư mục ra]
# Cùng biến môi trường với lượt V3 và vector thuần chính thức, thêm MINIRAG_SLM_SEED; không cache parser, không tái dùng câu
# trả lời. Endpoint và khoá như reproduce/screening/run_screen.sh. Chạy lại được: QA và chấm đều resume.
cd "$(dirname "$0")/../.." || exit 1
TAG=$1; FUSION=$2; SEED=$3; Q=${4:-reproduce/stage_d/nondev435.csv}; OUT=${5:-logs/stage_d}
if [ -z "$TAG" ] || [ -z "$FUSION" ] || [ -z "$SEED" ]; then
  echo "dùng: run_one.sh <tag> <chế độ trộn> <seed> [file câu hỏi] [thư mục ra]" >&2; exit 2
fi
CFG="${MINIRAG_CONFIG_DIR:-$HOME/.config/minirag}"
[ -n "$MINIRAG_SLM_URL" ] || MINIRAG_SLM_URL="$(tr -d '[:space:]' 2>/dev/null < "$CFG/slm_url")"
[ -n "$MINIRAG_SLM_KEY" ] || MINIRAG_SLM_KEY="$(tr -d '\n' 2>/dev/null < "$CFG/slm_key")"
if [ -z "$MINIRAG_SLM_URL" ] || [ -z "$MINIRAG_SLM_KEY" ]; then
  echo "Thiếu endpoint hoặc khoá SLM (xem reproduce/screening/HUONG_DAN_CHAY.md)" >&2; exit 1
fi
PY="${PYTHON:-.venv/bin/python}"
mkdir -p "$OUT"
while pgrep -f "Step_1_QA.py" >/dev/null; do echo "$(date +%H:%M) đang có Step_1_QA khác — chờ 60 s"; sleep 60; done

echo "=== QA $TAG (CHUNK_FUSION=$FUSION, seed $SEED, endpoint $MINIRAG_SLM_URL) $(date '+%d/%m %H:%M') ==="
(
  unset MINIRAG_KW_CACHE MINIRAG_KW_CACHE_ONLY MINIRAG_TRUNCATE_SOURCES MINIRAG_MAX_TOKEN_TEXT_UNIT
  export MINIRAG_SLM_URL MINIRAG_SLM_KEY PYTHONUNBUFFERED=1
  source reproduce/slm_env.sh modal >/dev/null || exit 1
  tries=0
  until env MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT= MINIRAG_CHUNK_FUSION="$FUSION" \
          MINIRAG_SLM_SEED="$SEED" MINIRAG_CONTEXT_LOG="$OUT/${TAG}_ctx.jsonl" \
        "$PY" reproduce/Step_1_QA.py --model "$MINIRAG_SLM_MODEL" --workingdir ./LiHua-World-qwen-modal \
          --questions "$Q" --outputpath "$OUT/${TAG}.csv"; do
    tries=$((tries + 1)); [ $tries -ge 6 ] && { echo "QA $TAG lỗi 6 lần — dừng"; exit 1; }
    echo "$(date +%H:%M) QA $TAG lỗi — chờ 5 phút"; sleep 300
  done
) || exit 1

# Kiểm QA trước khi chấm: đủ dòng, đúng thứ tự, không có câu trả lời "Error" (lỗi endpoint không được chấm thành error).
"$PY" - "$Q" "$OUT/${TAG}.csv" <<'EOF' || { echo "QA $TAG không đạt kiểm — không chấm"; exit 3; }
import csv, sys
q = [r["Question"] for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))]
a = list(csv.DictReader(open(sys.argv[2], encoding="utf-8")))
same = [r["Question"] for r in a] == q
err = sum(1 for r in a if r["minirag"].strip() == "Error")
print(f"kiểm QA: {len(a)}/{len(q)} dòng · thứ tự {'khớp' if same else 'LỆCH'} · câu trả lời Error: {err}")
sys.exit(0 if same and err == 0 else 1)
EOF

echo "=== JUDGE $TAG $(date '+%d/%m %H:%M') ==="
(
  unset GEMINI_API_BASE GEMINI_API_KEY_ONLY MINIRAG_MAX_TOKENS MINIRAG_SLM_MODEL MINIRAG_SLM_URL MINIRAG_SLM_KEY MINIRAG_SLM_SEED
  export GEMINI_RPM=13 GEMINI_TPM=3000 PYTHONUNBUFFERED=1
  tries=0
  until "$PY" reproduce/Step_2_evaluate.py --inputpath "$OUT/${TAG}.csv" --repeats 1; do
    tries=$((tries + 1)); [ $tries -ge 6 ] && { echo "chấm $TAG còn judge_failed sau 6 lần — dừng"; exit 4; }
    echo "$(date +%H:%M) chấm $TAG còn judge_failed — chờ 20 phút"; sleep 1200
  done
) || exit 4
echo "=== DONE $TAG $(date '+%d/%m %H:%M') ==="
