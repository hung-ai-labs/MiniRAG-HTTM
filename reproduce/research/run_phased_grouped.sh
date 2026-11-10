#!/usr/bin/env bash
# Phased QA grouped by phase across seeds (LiHua MiniCPM amendment M2): the same phase_qa.py calls as
# run_phased_dev.sh, ordered so the GPU phases run back to back instead of one cold start per config.
#
#   reproduce/research/run_phased_grouped.sh <phase> <questions.csv> <out-dir> "<seeds>" L-C0 L-B2 ...
#
# <phase> is keywords (every seed), contexts (every seed x config, CPU only) or answers (every seed x config).
# Optional: INDEX=<frozen index dir>, SERVING=<serving json>, WORKERS=<phase B processes>. Generation only; judge
# each seed with judge_session.py. Every step resumes, so after an interruption run the same command again.
set -euo pipefail
cd "$(dirname "$0")/../.."
phase=$1 questions=$2 out=$3 seeds=$4; shift 4
export PYTHONUTF8=1 PYTHONUNBUFFERED=1
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
stamp() { echo "=== $* $(date -u +%FT%TZ)"; }
idx=(); [ -n "${INDEX:-}" ] && idx=(--index "$INDEX")
srv=(); [ -n "${SERVING:-}" ] && srv=(--serving "$SERVING")

for seed in $seeds; do
  case "$phase" in
    keywords)
      stamp "keywords seed $seed"
      "$PY" reproduce/research/phased_qa.py keywords --questions "$questions" --seed "$seed" --out "$out" \
        "${idx[@]}" "${srv[@]}";;
    contexts|answers)
      for config in "$@"; do
        stamp "$phase $config seed $seed"
        if [ "$phase" = contexts ]; then
          "$PY" reproduce/research/phased_qa.py contexts --config "$config" --questions "$questions" --seed "$seed" \
            --out "$out" --workers "${WORKERS:-3}" "${idx[@]}" "${srv[@]}"
        else
          "$PY" reproduce/research/phased_qa.py answers --config "$config" --questions "$questions" --seed "$seed" \
            --out "$out" "${srv[@]}"
        fi
      done;;
    *) echo "unknown phase $phase" >&2; exit 2;;
  esac
done
stamp "$phase done"
