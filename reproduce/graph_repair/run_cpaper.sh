#!/bin/sh
# Prepared only. Run sequentially after the shared offline job has finished.
cd /e/Project/MiniRAG/.worktrees/c-paper || exit 1
E=logs/graph_repair/cpaper
PY=/e/Project/MiniRAG/.venv/Scripts/python.exe
INDEX=/e/Project/MiniRAG/LiHua-World-qwen-modal
export PYTHONIOENCODING=utf-8 MINIRAG_KW_CACHE_ONLY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TIKTOKEN_CACHE_DIR="$PWD/data-gym-cache"
export GEMINI_API_KEY=offline-dummy
unset MINIRAG_PAPER_MODE MINIRAG_EDGE_SCORE MINIRAG_PATH_SELECT MINIRAG_PATH_SELECT_LOG
unset MINIRAG_CPAPER_CHUNK_NODES MINIRAG_CPAPER_EDGE_DESC MINIRAG_CPAPER_INTERSECTION MINIRAG_CPAPER_EQ2 MINIRAG_CPAPER_EQ3

# C0 must match the frozen 180 records before the paper arm can start.
"$PY" reproduce/graph_repair/run_offline.py --phase cpaper --name c0_off_reg --arm C0 --index "$INDEX" || exit 1
"$PY" -c "
import json, sys
load = lambda p: {r['query']: r['chunk_ids'] for r in map(json.loads, open(p, encoding='utf-8'))}
a = load('logs/c_ablation/graph/C0/C0_records.jsonl')
b = load('$E/c0_off_reg/C0_records.jsonl')
same = sum(a.get(q) == ids for q, ids in b.items())
print(f'C0 regression: {same}/{len(a)} identical chunk_ids')
sys.exit(0 if same == len(a) == len(b) == 180 else 1)" || { echo 'C0 regression failed; C-paper aborted'; exit 1; }

# eval_offline passes top_k=60 to seeds; paper mode itself enforces 5 chunks/6000 tokens.
"$PY" reproduce/graph_repair/run_offline.py --phase cpaper --name c_paper --arm C0 --index "$INDEX" \
  --env MINIRAG_PAPER_MODE=1 || exit 1
"$PY" reproduce/graph_repair/compare_cpaper.py || exit 1
