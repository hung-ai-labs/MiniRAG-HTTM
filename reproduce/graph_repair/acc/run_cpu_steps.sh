#!/bin/sh
# RUNBOOK steps 0-1 (CPU only): tests, prepare, contexts L-C0/L-T x 3 seeds x {qwen, phi}, gates.
set -e
cd /e/Project/MiniRAG/.worktrees/temporal
PY=/e/Project/MiniRAG/.venv/Scripts/python.exe
export GEMINI_API_KEY=offline-dummy
date +"%T step0 tests+prepare"
$PY -m unittest tests.test_temporal_acc -v 2>&1 | tail -3
$PY reproduce/graph_repair/acc/run.py prepare --model qwen
$PY reproduce/graph_repair/acc/run.py prepare --model phi
for model in qwen phi; do
  for seed in 101 202 303; do
    for arm in L-C0 L-T; do
      date +"%T contexts $model s$seed $arm"
      $PY reproduce/graph_repair/acc/run.py contexts --model "$model" --seed "$seed" --arm "$arm"
    done
  done
  date +"%T gate $model"
  $PY reproduce/graph_repair/acc/run.py gate --model "$model"
done
date +"%T CPU steps done"
