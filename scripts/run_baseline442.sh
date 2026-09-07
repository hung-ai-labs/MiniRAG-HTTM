#!/bin/zsh
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
PY=.venv/bin/python
WD=./LiHua-World-gemini
OUT=./logs/baseline442_devset.csv
BACKOFF=900

run () {  # $1 = label, rest = command
  local label=$1; shift
  echo "=== STAGE: $label ==="
  until "$@"; do
    echo "=== $label failed, sleeping ${BACKOFF}s ==="; sleep $BACKOFF
  done
  echo "=== STAGE: ${label}_DONE ==="
}

# no --evidence: walk all 442 documents; the 267 already indexed are skipped
run INDEX442 $PY reproduce/Step_0_index.py --workingdir $WD

# baseline config: every retrieval knob left at library defaults
run QA $PY reproduce/Step_1_QA.py --workingdir $WD \
      --questions ./logs/devset.csv --outputpath $OUT

run JUDGE $PY reproduce/Step_2_evaluate.py --inputpath $OUT --repeats 3

echo "=== STAGE: ALL_DONE ==="
