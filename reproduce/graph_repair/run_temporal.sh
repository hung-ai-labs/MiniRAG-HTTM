#!/bin/sh
# Prepared only. Run after the independent C-paper dev batch has completed.
set -eu
cd /e/Project/MiniRAG/.worktrees/temporal
PY=/e/Project/MiniRAG/.venv/Scripts/python.exe
INDEX=/e/Project/MiniRAG/LiHua-World-qwen-modal
PAPER_BASE=/e/Project/MiniRAG/.worktrees/c-paper/logs/graph_repair/cpaper/c_paper/C0_records.jsonl
E=logs/graph_repair/temporal
export PYTHONIOENCODING=utf-8 MINIRAG_KW_CACHE_ONLY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TIKTOKEN_CACHE_DIR="$PWD/data-gym-cache"
export GEMINI_API_KEY=offline-dummy
unset MINIRAG_TEMPORAL MINIRAG_TEMPORAL_H MINIRAG_TEMPORAL_EXPAND MINIRAG_PAPER_MODE
unset MINIRAG_EDGE_SCORE MINIRAG_PATH_SELECT MINIRAG_PATH_SELECT_LOG
unset MINIRAG_CPAPER_CHUNK_NODES MINIRAG_CPAPER_EDGE_DESC MINIRAG_CPAPER_INTERSECTION MINIRAG_CPAPER_EQ2 MINIRAG_CPAPER_EQ3

# Verify frozen registration before touching any retrieval arm.
"$PY" -c "import hashlib,pathlib,sys; p=pathlib.Path('reproduce/graph_repair/TEMPORAL_REGISTRATION.md'); line=pathlib.Path('$E/REGISTRATION.sha256').read_text(encoding='utf-8-sig').split()[0]; sys.exit(0 if hashlib.sha256(p.read_bytes()).hexdigest()==line else 1)" || exit 1

"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name c0_off --arm C0 --index "$INDEX"
"$PY" -c "
import json,sys
load=lambda p:{r['question']:r['chunk_ids'] for r in map(json.loads,open(p,encoding='utf-8'))}
a=load('logs/c_ablation/graph/C0/C0_records.jsonl'); b=load('$E/c0_off/C0_records.jsonl')
n=sum(a.get(q)==v for q,v in b.items()); print(f'C0 switch-off regression: {n}/180')
sys.exit(0 if n==len(a)==len(b)==180 else 1)" || { echo 'C0 regression failed'; exit 1; }

"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name c0_full --arm C0 --index "$INDEX" --env MINIRAG_TEMPORAL=1
"$PY" reproduce/graph_repair/compare_temporal.py --stage c0 --index "$INDEX" || { echo 'C0 temporal screen failed; stop and report'; exit 1; }
"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name c0_h1 --arm C0 --index "$INDEX" --env MINIRAG_TEMPORAL=1 --env MINIRAG_TEMPORAL_H=1
"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name c0_noexpand --arm C0 --index "$INDEX" --env MINIRAG_TEMPORAL=1 --env MINIRAG_TEMPORAL_EXPAND=0

# This is the dev record produced by the separate C-paper worktree; read it only here.
test -f "$PAPER_BASE" || { echo 'C-paper dev baseline is not ready'; exit 1; }
"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name paper_full --arm C0 --index "$INDEX" --env MINIRAG_PAPER_MODE=1 --env MINIRAG_TEMPORAL=1
"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name paper_h1 --arm C0 --index "$INDEX" --env MINIRAG_PAPER_MODE=1 --env MINIRAG_TEMPORAL=1 --env MINIRAG_TEMPORAL_H=1
"$PY" reproduce/graph_repair/run_offline.py --phase temporal --name paper_noexpand --arm C0 --index "$INDEX" --env MINIRAG_PAPER_MODE=1 --env MINIRAG_TEMPORAL=1 --env MINIRAG_TEMPORAL_EXPAND=0
"$PY" reproduce/graph_repair/compare_temporal.py --stage all --index "$INDEX" --paper-baseline "$PAPER_BASE"
