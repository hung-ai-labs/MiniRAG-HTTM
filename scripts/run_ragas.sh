#!/bin/zsh
cd /Users/hunggoodboy/Documents/HTTM-TK/MiniRAG-HTTM
export PYTHONUNBUFFERED=1
PY=.venv/bin/python
BACKOFF=900

# wait out the context collector if it is still going
while pgrep -f Step_3_collect_context >/dev/null; do sleep 60; done

echo "=== STAGE: CONTEXT ==="
until $PY reproduce/Step_3_collect_context.py --workingdir ./LiHua-World-gemini \
      --outputpath ./logs/gemini_output.csv >> logs/context_collect.log 2>&1; do
  echo "=== context failed, sleeping ${BACKOFF}s ==="
  sleep $BACKOFF
done
echo "=== STAGE: CONTEXT_DONE ==="

echo "=== STAGE: RAGAS ==="
until $PY reproduce/Step_4_ragas.py --input ./logs/gemini_output_context.jsonl \
      --output ./logs/ragas_scores.csv --stratified 200 >> logs/ragas.log 2>&1; do
  echo "=== ragas failed, sleeping ${BACKOFF}s ==="
  sleep $BACKOFF
done
echo "=== STAGE: RAGAS_DONE ==="
tail -12 logs/ragas.log
