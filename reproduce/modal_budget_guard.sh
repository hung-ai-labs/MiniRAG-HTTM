#!/bin/sh
# Modal budget guard: stop every running Modal app when the remaining monthly credit drops to STOP_AT.
# Usage: sh reproduce/modal_budget_guard.sh [CREDIT=30] [STOP_AT=1.0] [INTERVAL_S=300]
# Account: the modal CLI honours MODAL_PROFILE, e.g.
#   MODAL_PROFILE=nguyenhuuanhtai426 sh reproduce/modal_budget_guard.sh 30 1.0 300
# Always run the guard with the SAME profile as the GPU job it protects.
# Run it in the background for the whole duration of any GPU step. Exit 0 = budget hit and apps stopped;
# exit 3 = cannot read billing (stop GPU work by hand). Modal billing can lag the real spend: with an A100
# running (~2.8 USD/h) the true remaining credit can be lower than printed.
M=/e/Project/MiniRAG/.venv/Scripts/modal.exe
CREDIT=${1:-30}; STOP_AT=${2:-1.0}; INTERVAL=${3:-300}
fails=0
while true; do
  summary=$("$M" billing summary 2>&1)
  used=$(printf '%s\n' "$summary" | sed -n 's/.*Credits: *| *-\{0,1\}\([0-9.]*\).*/\1/p' | head -1)
  # A fresh workspace prints no "Credits:" line until something is spent; fall back to Metered Cost (>= credits used).
  [ -n "$used" ] || used=$(printf '%s\n' "$summary" | sed -n 's/.*Metered Cost: *| *\([0-9.]*\).*/\1/p' | head -1)
  billed=$(printf '%s\n' "$summary" | sed -n 's/.*Billed Cost: *| *\$\{0,1\}\([0-9.]*\).*/\1/p' | head -1)
  if [ -z "$used" ] || [ -z "$billed" ]; then
    fails=$((fails+1)); echo "$(date +%T) cannot parse billing summary ($fails)"; printf '%s\n' "$summary" | tail -3
    [ "$fails" -ge 3 ] && exit 3
  else
    fails=0
    left=$(awk "BEGIN{printf \"%.2f\", $CREDIT - $used}")
    running=$("$M" app list --json 2>/dev/null | tr -d '\r' | awk -F'"' '/"app_id"/{id=$4} /"tasks"/{if ($4+0>0) print id}')
    echo "$(date +%T) credit used $used / $CREDIT, left $left, billed $billed, apps with tasks: ${running:-none}"
    if awk "BEGIN{exit !($left <= $STOP_AT || $billed > 0)}"; then
      echo "$(date +%T) BUDGET LIMIT: left $left <= $STOP_AT (or billed > 0) - stopping all Modal apps"
      "$M" app list --json 2>/dev/null | tr -d '\r' | awk -F'"' '/"app_id"/{id=$4} /"state"/{if ($4=="deployed"||$4=="ephemeral"||$4=="running") print id}' |
        while read -r app; do "$M" app stop -y "$app" && echo "stopped $app"; done
      echo "Log in to the next Modal account (modal token new / modal profile activate) before any further GPU step."
      exit 0
    fi
  fi
  sleep "$INTERVAL"
done
