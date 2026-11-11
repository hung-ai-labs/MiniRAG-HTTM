#!/bin/zsh
# A-Z: Table 1 (C0 -> + source-time -> + F -> + CE -> + set selection) for one SLM,
# on the 435 held-out questions, 3 generation rounds x 3 DeepSeek judge passes.
# Every step is resumable: rerun the same command after any interruption.
#
#   zsh reproduce/evidence_set/run_ladder.sh qwen
#   zsh reproduce/evidence_set/run_ladder.sh phi      # builds the Phi index first (Phi does the extraction)
set -e
cd "${0:A:h}/../.."
PY=.venv/bin/python
export PYTHONUNBUFFERED=1
SLM=${1:?usage: run_ladder.sh qwen|phi}
ROUNDS=${ROUNDS:-3}
export MINIRAG_EVSET_SLM=$SLM

if [ "$SLM" = phi ]; then
  if [ ! -f LiHua-World-phi-modal/INDEX_DONE ]; then
    echo "== index (Phi-3.5-mini on Modal builds its own graph)"
    env GEMINI_API_BASE="$(cat ~/.config/minirag/phi_url)/v1" GEMINI_API_KEY_ONLY="$(cat ~/.config/minirag/slm_key)" \
        MINIRAG_MAX_TOKENS=1024 GEMINI_RPM=100000 GEMINI_TPM=100000000 \
        $PY reproduce/Step_0_index.py --workingdir ./LiHua-World-phi-modal --evidence --model minirag-slm
    date > LiHua-World-phi-modal/INDEX_DONE
  fi
  # the scorer is trained on this SLM's own dev200 pools
  $PY -m reproduce.evidence_set.pipeline capture --split dev200
fi
$PY -m reproduce.evidence_set.pipeline all --split nondev --rounds $ROUNDS
