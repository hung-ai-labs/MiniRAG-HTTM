#!/usr/bin/env bash
# Phased QA for several configs on one question set and seed, then judging (amendment S2).
#
#   reproduce/research/run_phased_dev.sh <questions.csv> <out-dir> <seed> C0 C1 C2 C3
#
# Phase A once (keywords, GPU), then per config phase B (CPU only) and C (GPU),
# then every config is judged back to back in one session, as registered.
# Every step resumes, so after an interruption run the same command again.
set -euo pipefail
cd "$(dirname "$0")/../.."
questions=$1 out=$2 seed=$3; shift 3
export PYTHONUTF8=1 PYTHONUNBUFFERED=1
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
stamp() { echo "=== $* $(date -u +%FT%TZ)"; }

stamp "keywords seed $seed"
"$PY" reproduce/research/phased_qa.py keywords --questions "$questions" --seed "$seed" --out "$out"
for config in "$@"; do
  stamp "contexts $config"
  "$PY" reproduce/research/phased_qa.py contexts --config "$config" --questions "$questions" --seed "$seed" \
    --out "$out" --workers "${WORKERS:-3}"
  stamp "answers $config"
  "$PY" reproduce/research/phased_qa.py answers --config "$config" --questions "$questions" --seed "$seed" --out "$out"
done
for config in "$@"; do
  run="$out/${config}_s$seed"
  resume=(); [ -f "$run/judge/manifest.json" ] && resume=(--resume)
  stamp "judge $config"
  "$PY" reproduce/research/judge_run.py --questions "$questions" --answers "$run/answers.csv" \
    --run-dir "$run/judge" "${resume[@]}" || "$PY" reproduce/research/judge_run.py --questions "$questions" \
    --answers "$run/answers.csv" --run-dir "$run/judge" --resume
done
stamp "done"
