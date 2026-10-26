#!/usr/bin/env bash
# Superseded by phased_qa.py (amendment S2); kept as the record of the C0 smoke run.
#
# One MultiHop-RAG QA run with the pre-registered settings (MULTIHOP_RAG_ROADMAP.md,
# "Thông số chạy cố định", commit 7013291). Only the retrieval switches differ
# between C0..C3; everything else is fixed here so no run can drift.
#
#   reproduce/research/run_mhr_qa.sh C0 <questions.csv> <run-dir> <seed>
#
# Writes <run-dir>/run_note.json (config, seed, registration and HEAD commits),
# then qa_run.py's own manifest, generation log and answers.csv. Judging is a
# separate step (judge_run.py) so configs compared on one seed can be judged
# back to back.
set -euo pipefail
cd "$(dirname "$0")/../.."

config=$1 questions=$2 run_dir=$3 seed=$4
REGISTRATION=7013291
INDEX=indexes/multihop_rag-qwen-full609

# GROUP_BASE, then each config's single change.
export MINIRAG_ANSWER_TYPE_FIX=1 MINIRAG_PATH2CHUNK_FIX=0 MINIRAG_CHUNK_CUT=
unset MINIRAG_CHUNK_FUSION
mode=mini
case "$config" in
  C0) ;;
  C1) export MINIRAG_CHUNK_FUSION=vector_bm25 ;;
  C2) export MINIRAG_CHUNK_FUSION=vector ;;
  C3) mode=naive ;;
  *) echo "unknown config $config (C0..C3)" >&2; exit 2 ;;
esac

# Generation stays at the registered 1024 even if the shell still holds the
# indexing cap of 4096.
export MINIRAG_MAX_TOKENS=1024 MINIRAG_SLM_SEED=$seed PYTHONUTF8=1 PYTHONUNBUFFERED=1
mkdir -p "$run_dir"
export MINIRAG_CONTEXT_LOG=$run_dir/context.jsonl

PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
"$PY" - "$run_dir" "$config" "$seed" "$questions" "$REGISTRATION" "$mode" <<'EOF'
import json, subprocess, sys
from datetime import datetime, timezone
run_dir, config, seed, questions, registration, mode = sys.argv[1:]
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
note = {"config": config, "seed": int(seed), "questions": questions, "mode": mode,
        "registration_commit": registration, "head_commit": head,
        "started_at": datetime.now(timezone.utc).isoformat()}
open(f"{run_dir}/run_note.json", "w", encoding="utf-8").write(json.dumps(note, indent=2) + "\n")
EOF

exec "$PY" reproduce/research/qa_run.py --questions "$questions" --workingdir "$INDEX" \
  --run-dir "$run_dir/qa" --concurrency 4 --llm-max-async 4 --mode "$mode" \
  --serving-config reproduce/research/serving_qwen_modal.json
