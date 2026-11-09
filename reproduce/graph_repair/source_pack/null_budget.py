"""Thu DIAG cho 20 câu Null của dev (chỉ truy hồi, offline, không sinh câu trả lời). Không sửa runner dùng chung:
nhập eval_offline làm module và dùng lại run_diagnose_query.

  $env:GEMINI_API_KEY='offline-dummy'; $env:TIKTOKEN_CACHE_DIR="$PWD\\data-gym-cache"
  .\\.venv\\Scripts\\python.exe -X utf8 reproduce\\graph_repair\\source_pack\\null_budget.py --name c0
  ... --name p_ff  --env MINIRAG_PACK_FILL=firstfit
  ... --name p_d05f --env MINIRAG_PACK_ALPHA=0.5 --env MINIRAG_PACK_FILL=firstfit
"""
import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reproduce"))
sys.path.insert(0, os.path.join(ROOT, "reproduce", "path"))

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--env", action="append", default=[])
ap.add_argument("--index", default=os.path.join(ROOT, "LiHua-World-qwen-modal"))
args = ap.parse_args()

out = os.path.join(ROOT, "logs", "graph_repair", "p_pack", "null", args.name)
os.makedirs(os.path.join(out, "cache"), exist_ok=True)
for k, v in {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "MINIRAG_KW_CACHE_ONLY": "1",
             "MINIRAG_DIAG_LOG": os.path.join(out, "diag.jsonl")}.items():
    os.environ[k] = v
if os.path.exists(os.environ["MINIRAG_DIAG_LOG"]):
    os.remove(os.environ["MINIRAG_DIAG_LOG"])

import eval_offline as eo  # noqa: E402
from c_ablation import environment  # noqa: E402
from screen_variant import dev_rows  # noqa: E402

os.environ.update(environment("C0"))
os.environ["MINIRAG_ANSWER_TYPE_FIX"] = "1"
for kv in args.env:
    key, _, val = kv.partition("=")
    assert key.startswith("MINIRAG_PACK_"), f"chỉ nhận MINIRAG_PACK_*: {kv}"
    os.environ[key] = val
eo.OUT_DIR = out
eo.KW_CACHE = os.path.join(ROOT, "logs", "path", "cache", "kw_cache.jsonl")

rows = [r for r in dev_rows() if r.get("Type") == "Null"]
assert len(rows) == 20, len(rows)


async def main():
    with tempfile.TemporaryDirectory(prefix="minirag-null-", ignore_cleanup_errors=True) as tmp:
        for e in os.scandir(args.index):
            if e.is_file() and e.name.endswith((".json", ".graphml")):
                shutil.copy2(e.path, tmp)
        rag = eo.build_rag(argparse.Namespace(workingdir=tmp, model="Qwen/Qwen2.5-3B-Instruct", embedmodel="local"))
        recs = await eo.evaluate_dataset(rag, rows, {}, mode_name=f"null-{args.name}")
    with open(os.path.join(out, "records.jsonl"), "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{args.name}: {len(recs)} câu Null, env={args.env}")


asyncio.run(main())
