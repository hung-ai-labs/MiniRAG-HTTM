"""Step 1 - run the LiHua-World query set against the indexed graph (Gemini).

    export GEMINI_API_KEY=your_key
    python ./reproduce/Step_1_QA.py --outputpath ./logs/gemini_output.csv
"""

import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_HERE)
sys.path.append(os.path.dirname(_HERE))  # repo root, so `minirag` imports here too

from tqdm import trange  # noqa: E402
from minirag import QueryParam  # noqa: E402
from gemini_common import build_query_param, build_rag, get_args  # noqa: E402

args = get_args("MiniRAG QA (Gemini)")
rag = build_rag(args)
QPARAM = build_query_param(args)

QUESTION_LIST = []
GA_LIST = []
qpath = args.questions or args.querypath
with open(qpath, mode="r", encoding="utf-8") as question_file:
    reader = csv.DictReader(question_file)
    for row in reader:
        QUESTION_LIST.append(row["Question"])
        GA_LIST.append(row["Gold Answer"])

if args.limit:
    QUESTION_LIST = QUESTION_LIST[: args.limit]
    GA_LIST = GA_LIST[: args.limit]


def run_experiment(output_path):
    headers = ["Question", "Gold Answer", "minirag"]

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    q_already = []
    if os.path.exists(output_path):
        with open(output_path, mode="r", encoding="utf-8") as question_file:
            reader = csv.DictReader(question_file)
            for row in reader:
                q_already.append(row["Question"])

    row_count = len(q_already)
    print("row_count", row_count)

    with open(output_path, mode="a", newline="", encoding="utf-8") as log_file:
        writer = csv.writer(log_file)
        if row_count == 0:
            writer.writerow(headers)

        for QUESTIONid in trange(row_count, len(QUESTION_LIST)):
            QUESTION = QUESTION_LIST[QUESTIONid]
            Gold_Answer = GA_LIST[QUESTIONid]
            print()
            print("QUESTION", QUESTION)
            print("Gold_Answer", Gold_Answer)

            try:
                minirag_answer = (
                    rag.query(QUESTION, param=QPARAM)
                    .replace("\n", "")
                    .replace("\r", "")
                )
            except Exception as e:
                print("Error in minirag_answer", e)
                minirag_answer = "Error"

            writer.writerow([QUESTION, Gold_Answer, minirag_answer])
            log_file.flush()

    print(f"Experiment data has been recorded in the file: {output_path}")


run_experiment(args.outputpath)
