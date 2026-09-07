#!/bin/zsh
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1          # otherwise progress prints sit in an 8KB buffer
PY=.venv/bin/python
WD=./LiHua-World-gemini
OUT=./logs/gemini_output.csv
BACKOFF=600                        # quota is per-day; do not hammer it on repeat failure

run_stage () {   # $1 = label, $2.. = command
  local label=$1; shift
  echo "=== STAGE: $label ==="
  local n=0
  until "$@"; do
    n=$((n+1))
    echo "=== $label failed (attempt $n), sleeping ${BACKOFF}s then resuming ==="
    sleep $BACKOFF
  done
  echo "=== STAGE: ${label}_DONE ==="
}

run_stage INDEX $PY reproduce/Step_0_index.py --workingdir $WD --evidence
run_stage QA    $PY reproduce/Step_1_QA.py --workingdir $WD --outputpath $OUT
run_stage SCORE $PY reproduce/Step_2_evaluate.py --inputpath $OUT

echo "=== STAGE: ALL_DONE ==="
tail -5 logs/score_gemini.log 2>/dev/null
