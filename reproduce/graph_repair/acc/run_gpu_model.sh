#!/bin/sh
# RUNBOOK step 2/3 for one SLM: budget guard -> deploy on the NEW Modal account -> G1 smoke -> 6 answer runs -> stop app.
# Usage: sh reproduce/graph_repair/acc/run_gpu_model.sh qwen|phi
# Refuses to start unless all three context gates of that model passed. Always stops the app on exit.
model=$1; [ "$model" = qwen ] || [ "$model" = phi ] || { echo "usage: $0 qwen|phi"; exit 2; }
cd /e/Project/MiniRAG/.worktrees/temporal || exit 1
PY=/e/Project/MiniRAG/.venv/Scripts/python.exe
MODAL=/e/Project/MiniRAG/.venv/Scripts/modal.exe
export MODAL_PROFILE=nguyenhuuanhtai426
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8   # modal prints build logs with characters cp1252 cannot encode
case $model in
  qwen) SERVING=reproduce/research/serving_qwen_modal.json;      APP=minirag-slm ;;
  phi)  SERVING=reproduce/research/serving_phi_rope_modal.json;  APP=minirag-slm-phi-rope ;;
esac
D=runs/lihua_world/temporal_acc/$model
for s in 101 202 303; do
  [ -f "$D/gate_s$s.json" ] || { echo "gate_s$s.json missing for $model - not deploying"; exit 3; }
  $PY -c "import json,sys; g=json.load(open('$D/gate_s$s.json')); sys.exit(0 if g.get('baseline_identical')==435 else 1)" \
    || { echo "gate s$s not 435/435 - not deploying"; exit 3; }
done
echo "$(date +%T) all 3 gates passed for $model"

stop_app() { "$MODAL" app stop -y "$APP" >/dev/null 2>&1 && echo "$(date +%T) app $APP stopped"; [ -n "$GUARD" ] && kill "$GUARD" 2>/dev/null; }
trap 'stop_app' EXIT INT TERM

sh reproduce/modal_budget_guard.sh 30 1.0 300 > "$D/guard.log" 2>&1 & GUARD=$!
echo "$(date +%T) budget guard pid $GUARD"

echo "$(date +%T) deploying $SERVING on $MODAL_PROFILE"
MODAL_IMAGE_BUILDER_VERSION=2025.06 SLM_SERVING=$SERVING "$MODAL" deploy reproduce/modal_slm.py > "$D/deploy.log" 2>&1 || { echo "deploy failed:"; tail -20 "$D/deploy.log"; exit 4; }
# The deploy log wraps long URLs across lines: join lines before matching; app name differs per model.
URL=$(tr -d '\r\n ' < "$D/deploy.log" | grep -oE "https://[A-Za-z0-9-]+--$APP-serve\.[A-Za-z0-9.-]*modal\.run" | head -1)
[ -n "$URL" ] || { echo "no URL in deploy log:"; tail -20 "$D/deploy.log"; exit 4; }
echo "$(date +%T) deployed: $URL"
export MINIRAG_SLM_URL=$URL

# G1 smoke gate: up to 3 attempts (cold start can return 303/500/408), each attempt's output kept.
ok=0
for i in 1 2 3; do
  if $PY reproduce/graph_repair/acc/run.py smoke --model $model > "$D/smoke_try$i.log" 2>&1; then ok=1; break; fi
  echo "$(date +%T) smoke attempt $i failed:"; tail -5 "$D/smoke_try$i.log"; sleep 90
done
[ "$ok" = 1 ] || { echo "G1 smoke failed 3 times - stopping"; exit 5; }
echo "$(date +%T) G1 smoke passed"

for s in 101 202 303; do
  for arm in L-C0 L-T; do
    echo "$(date +%T) answers $model s$s $arm"
    $PY reproduce/graph_repair/acc/run.py answers --model $model --seed $s --arm $arm > "$D/answers_${arm}_s$s.log" 2>&1 \
      || { echo "answers failed ($arm s$s):"; tail -15 "$D/answers_${arm}_s$s.log"; exit 6; }
    tail -1 "$D/answers_${arm}_s$s.log"
  done
done
echo "$(date +%T) all 6 answer runs done for $model"
stop_app; trap - EXIT
"$MODAL" billing report --for today 2>&1 | tail -15
