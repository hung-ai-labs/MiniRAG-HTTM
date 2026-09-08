"""Step 0 - index the dataset into MiniRAG using the Gemini API.

    export GEMINI_API_KEY=your_key
    python ./reproduce/Step_0_index.py --workingdir ./LiHua-World
"""

import os

from gemini_common import build_rag, get_args  # noqa: E402
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

args = get_args("MiniRAG indexing (Gemini)")
rag = build_rag(args)


def find_txt_files(root_path):
    txt_files = []
    for root, dirs, files in os.walk(root_path):
        for file in sorted(files):
            if file.endswith(".txt"):
                txt_files.append(os.path.join(root, file))
    return sorted(txt_files)


WEEK_LIST = find_txt_files(args.datapath)

if args.evidence:
    import csv
    import re

    by_stem = {os.path.basename(p)[:-4]: p for p in WEEK_LIST}
    with open(args.querypath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    wanted = []
    for row in rows:
        for d, h, m in re.findall(r"(\d{8})_(\d{2}):(\d{2})", row["Evidence"]):
            path = by_stem.get(f"{d}_{h}{m}")
            if path and path not in wanted:
                wanted.append(path)
    WEEK_LIST = wanted
    print(f"evidence mode: {len(rows)} questions -> {len(WEEK_LIST)} documents")
elif args.limit:
    WEEK_LIST = WEEK_LIST[: args.limit]

for id, WEEK in enumerate(WEEK_LIST):
    print(f"{id}/{len(WEEK_LIST)} {WEEK}")
    with open(WEEK, encoding="utf-8", errors="ignore") as f:
        rag.insert(f.read())

print("Indexing done ->", args.workingdir)
