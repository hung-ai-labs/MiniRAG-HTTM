#!/usr/bin/env bash
# Phased QA for several configs on one question set and seed, then judging (amendment S2).
#
#   reproduce/research/run_phased_dev.sh <questions.csv> <out-dir> <seed> C0 C1 C2 C3
#
# Optional: INDEX=<frozen index dir> (default: MultiHop full609), JUDGE_MODEL=<Gemini id> (default
# gemini-flash-lite-latest; LiHua ablation v2 pins gemini-3.5-flash-lite), WORKERS=<phase B processes>,
# SKIP_JUDGE=1 (phases A-C only; LiHua ablation v2 judges each seed in one judge_session.py session).
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
idx=(); [ -n "${INDEX:-}" ] && idx=(--index "$INDEX")
for config in "$@"; do  # LiHua ablation v2 judges only through judge_session.py, with the pinned model
  case "$config" in L-*) [ -n "${SKIP_JUDGE:-}" ] || { echo "L-* configs need SKIP_JUDGE=1 (judge with judge_session.py)" >&2; exit 2; };; esac
done
jm=(--judgemodel "${JUDGE_MODEL:-gemini-flash-lite-latest}")

stamp "keywords seed $seed"
"$PY" reproduce/research/phased_qa.py keywords --questions "$questions" --seed "$seed" --out "$out" "${idx[@]}"
for config in "$@"; do
  stamp "contexts $config"
  "$PY" reproduce/research/phased_qa.py contexts --config "$config" --questions "$questions" --seed "$seed" \
    --out "$out" --workers "${WORKERS:-3}" "${idx[@]}"
  stamp "answers $config"
  "$PY" reproduce/research/phased_qa.py answers --config "$config" --questions "$questions" --seed "$seed" --out "$out"
done
if [ -n "${SKIP_JUDGE:-}" ]; then  # generation only; judge later in one session (judge_session.py)
  stamp "generation done, judging skipped"
  exit 0
fi
for config in "$@"; do
  run="$out/${config}_s$seed"
  resume=(); [ -f "$run/judge/manifest.json" ] && resume=(--resume)
  stamp "judge $config"
  "$PY" reproduce/research/judge_run.py --questions "$questions" --answers "$run/answers.csv" \
    --run-dir "$run/judge" "${jm[@]}" "${resume[@]}" || "$PY" reproduce/research/judge_run.py --questions "$questions" \
    --answers "$run/answers.csv" --run-dir "$run/judge" "${jm[@]}" --resume
done
stamp "done"
