"""V5d Step 0 -- offline floor test of HHEM-2.1-Open as an answer-support verifier.

Pre-registered in ROADMAP (committed before this ran): the rule, the premises and the two
kill gates below are fixed. Labels (Type, judge verdicts, Evidence) only form the two
evaluation populations and the diagnostic gold premise; they never enter the decision rule.

Not the MiniRAG runtime: reads V3's saved answers, touches no index and no pipeline code.

    .venv/bin/python reproduce/v5d_hhem_floor.py <hhem_dir> <flan_t5_base_dir>

The model's own remote code (modeling_hhem_v2.py) is NOT executed: it loads its tokenizer and
config from `google/flan-t5-base` by name, unpinned, and its constructor ignores overrides.
Its inference is reproduced below line for line and checked against the model card's
published scores before any scoring.
"""

import collections
import csv
import hashlib
import json
import os
import re
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np  # noqa: E402
import torch  # noqa: E402
import transformers  # noqa: E402
from safetensors.torch import load_file  # noqa: E402
from transformers import AutoConfig, AutoTokenizer, T5ForTokenClassification  # noqa: E402

HHEM_REV = "8e4a2e6e96c708cc76c2344f7e4757df2515292c"
FLAN_REV = "7bcac572ce56db69c1ea7c8af255c5d7c9672fc2"
WEIGHTS_SHA256 = "634de18a38cf1e991c1acd0f7a9e0d30f7ea187fba42bb4798f862d3edd31e72"

THRESHOLD = 0.5    # pre-registered: flagged (would abstain) iff answer score < 0.5
FAR_KILL = 0.10    # stop V5d if > 10 % of correct non-Null answers are flagged
DETECT_KILL = 6    # stop V5d if < 6 of the 18 wrong Null answers are flagged
BUDGET = 4000      # proxy Sources: A1 token budget, same as v5_signal_feasibility.py
DEVICE = "cpu"     # float32 CPU is the reference; no MPS kernels in the decision path

PROMPT = ("<pad> Determine if the hypothesis is true given the premise?\n\n"
          "Premise: {text1}\n\nHypothesis: {text2}")
CARD_PAIRS = [
    ("The capital of France is Berlin.", "The capital of France is Paris."),
    ("I am in California", "I am in United States."),
    ("I am in United States", "I am in California."),
    ("A person on a horse jumps over a broken down airplane.", "A person is outdoors, on a horse."),
    ("A boy is jumping on skateboard in the middle of a red bridge.", "The boy skates down the sidewalk on a red bridge"),
    ("A man with blond-hair, and a brown shirt drinking out of a public water fountain.", "A blond man wearing a brown shirt is reading a book."),
    ("Mark Wahlberg was a fan of Manny.", "Manny was a fan of Mark Wahlberg."),
]
CARD_SCORES = [0.011061512865126133, 0.6473632454872131, 0.1290171593427658,
               0.8969419002532959, 0.18462494015693665, 0.005031010136008263,
               0.05432349815964699]

hhem_dir, flan_dir = sys.argv[1], sys.argv[2]
torch.set_grad_enabled(False)
t_start = time.time()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------- model: the remote code's inference, pinned ----------
got = sha256(f"{hhem_dir}/model.safetensors")
if got != WEIGHTS_SHA256:
    sys.exit(f"weights sha256 {got} != pinned {WEIGHTS_SHA256}")
tok = AutoTokenizer.from_pretrained(flan_dir)
model = T5ForTokenClassification(AutoConfig.from_pretrained(flan_dir))
raw = load_file(f"{hhem_dir}/model.safetensors")
state = {k[len("t5."):]: v for k, v in raw.items() if k.startswith("t5.")}
missing, unexpected = model.load_state_dict(state, strict=False)
if unexpected or any(not k.endswith("embed_tokens.weight") for k in missing):
    sys.exit(f"state dict mismatch: missing={missing} unexpected={unexpected}")
model.eval().to(DEVICE)


def predict(pairs, max_tokens=8000):
    """P(consistent) per (premise, hypothesis): softmax over logits at token 0, class 1."""
    texts = [PROMPT.format(text1=p, text2=h) for p, h in pairs]
    lens = [len(tok(t).input_ids) for t in texts]
    order = sorted(range(len(texts)), key=lambda i: lens[i])
    out = [None] * len(texts)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and (j - i + 1) * lens[order[j]] <= max_tokens:
            j += 1
        idx = order[i:j]
        enc = tok([texts[k] for k in idx], return_tensors="pt", padding=True).to(DEVICE)
        probs = torch.softmax(model(**enc).logits[:, 0, :], dim=-1)[:, 1]
        for k, s in zip(idx, probs.tolist()):
            out[k] = s
        i = j
    return out, lens


card, _ = predict(CARD_PAIRS)
card_diff = max(abs(a - b) for a, b in zip(card, CARD_SCORES))
if card_diff > 1e-3:
    sys.exit(f"does not reproduce the model card: max |diff| = {card_diff:.2e}")

# ---------- data ----------
qs = {r["Question"]: r for r in csv.DictReader(open("dataset/LiHua-World/qa/query_set.csv", encoding="utf-8"))}
ans = {r["Question"]: r["minirag"] for r in csv.DictReader(open("logs/qwen637_v3.csv", encoding="utf-8"))}
votes = collections.defaultdict(list)
for r in csv.DictReader(open("logs/qwen637_v3_judged.csv", encoding="utf-8")):
    votes[r["question"]].append(r["verdict"])
maj = {q: collections.Counter(v).most_common(1)[0][0] for q, v in votes.items()}
Q = [q for q in maj if q in ans and q in qs]
typ = {q: qs[q]["Type"] for q in Q}

chunks = json.load(open("LiHua-World-qwen-modal/kv_store_text_chunks.json", encoding="utf-8"))
ctext = [c["content"] for c in chunks.values()]
ctok = [c["tokens"] for c in chunks.values()]
time2idx = collections.defaultdict(set)
for i, t in enumerate(ctext):
    m = re.match(r"Time:\s*(\d{8}_\d{2}:\d{2})", t)
    if m:
        time2idx[m.group(1)].add(i)


def sentences(a):
    """Pre-registered split: strip markdown, break glued list items, split on sentence ends;
    keep pieces of >= 4 words; an answer with none is one hypothesis."""
    a = re.sub(r"[*#`]+", "", a)
    a = re.sub(r"(?<=[:.!?])\s*(?=(?:\d+\.|-)\s)", "\n", a)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])|\n", a)]
    keep = [p for p in parts if len(p.split()) >= 4]
    return keep or [a.strip()]


N_all = [q for q in Q if typ[q] != "Null" and maj[q] == "accurate"]
gold = {q: sorted(set().union(*[time2idx.get(t.strip(), set())
                                for t in qs[q]["Evidence"].split("<and>")]))
        for q in N_all}
N = [q for q in N_all if gold[q]]
N_unmapped = [q for q in N_all if not gold[q]]
P = [q for q in Q if typ[q] == "Null" and maj[q] == "error"]
P_info = [q for q in Q if typ[q] == "Null" and maj[q] == "neither"]

from sentence_transformers import SentenceTransformer  # noqa: E402

emb = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
E_c = emb.encode(ctext, normalize_embeddings=True, batch_size=64)


def proxy_sources(q):
    e = emb.encode([q], normalize_embeddings=True)[0]
    picked, used = [], 0
    for j in np.argsort(-(E_c @ e)):
        if used + ctok[j] > BUDGET:
            break
        picked.append(int(j))
        used += ctok[j]
    return picked


premises = {q: gold[q] for q in N}
for q in P + P_info:
    premises[q] = proxy_sources(q)

# ---------- score ----------
sents = {q: sentences(ans[q]) for q in premises}
keys, pair_text = {}, []
for q, prem in premises.items():
    for s in sents[q]:
        for c in prem:
            k = (c, s)
            if k not in keys:
                keys[k] = len(pair_text)
                pair_text.append((ctext[c], s))
t0 = time.time()
scores, lens = predict(pair_text)
t_score = time.time() - t0

result = {}
for q, prem in premises.items():
    per_sent = [max(scores[keys[(c, s)]] for c in prem) for s in sents[q]]
    worst = int(np.argmin(per_sent))
    result[q] = {"type": typ[q], "verdict": maj[q], "n_premise_chunks": len(prem),
                 "sentences": sents[q], "sentence_scores": per_sent,
                 "answer_score": per_sent[worst], "flagged": per_sent[worst] < THRESHOLD,
                 "weakest_sentence": sents[q][worst]}

with open("logs/v5d_step0_scores.jsonl", "w", encoding="utf-8") as f:
    for q, r in result.items():
        f.write(json.dumps({"question": q, **r}, ensure_ascii=False) + "\n")

# ---------- report ----------
flag = lambda qq: sum(result[q]["flagged"] for q in qq)
far = flag(N) / len(N)
det = flag(P)
print("V5d STEP 0 -- HHEM-2.1-Open offline floor test (pre-registered)")
print(f"model   vectara/hallucination_evaluation_model @ {HHEM_REV}")
print(f"        weights sha256 {WEIGHTS_SHA256} (verified)")
print(f"        tokenizer/config google/flan-t5-base @ {FLAN_REV}")
print(f"runtime transformers {transformers.__version__}, torch {torch.__version__}, device {DEVICE}, float32")
print(f"        state dict: missing {list(missing)} (tied embeddings), unexpected {list(unexpected)}")
print(f"card    model-card scores reproduced, max |diff| = {card_diff:.2e}")
print(f"pairs   {len(pair_text)} unique (premise chunk, answer sentence); tokens median "
      f"{int(np.median(lens))}, max {max(lens)}; scoring {t_score / 60:.1f} min; total {(time.time() - t_start) / 60:.1f} min")
print(f"rule    split answer into sentences; sentence score = max over premise chunks; "
      f"answer score = min over sentences; flagged iff < {THRESHOLD}")
print()
print(f"GATE 1  false abstention on correct non-Null answers (gold Evidence chunks as premise)")
print(f"        flagged {flag(N)}/{len(N)} = {far * 100:.1f}%   kill if > {FAR_KILL * 100:.0f}%   "
      f"-> {'FAIL' if far > FAR_KILL else 'pass'}")
for t in ("Single", "Multi"):
    sub = [q for q in N if typ[q] == t]
    print(f"          {t:<6} {flag(sub)}/{len(sub)} = {flag(sub) / len(sub) * 100:.1f}%")
print(f"        not evaluable (Evidence maps to no chunk): {len(N_unmapped)} of {len(N_all)}; "
      f"worst case counting them flagged: {(flag(N) + len(N_unmapped)) / len(N_all) * 100:.1f}%")
print(f"GATE 2  detection on wrong Null answers (proxy Sources: MiniLM ranking to {BUDGET} tokens)")
print(f"        flagged {det}/{len(P)}   kill if < {DETECT_KILL}   -> {'FAIL' if det < DETECT_KILL else 'pass'}")
print(f"        (informational) Null answers judged neither: flagged {flag(P_info)}/{len(P_info)}")
stop = far > FAR_KILL or det < DETECT_KILL
print()
print("VERDICT " + ("STOP V5d -- a pre-registered kill criterion is met. No threshold tuning."
                    if stop else "Step 0 passed both gates. The 50-query pilot still needs approval."))

q_n = np.quantile([result[q]["answer_score"] for q in N], [.1, .25, .5, .75, .9])
q_p = np.quantile([result[q]["answer_score"] for q in P], [.1, .25, .5, .75, .9])
print("\n(informational) answer-score quantiles p10 p25 p50 p75 p90")
print("  correct non-Null  " + " ".join(f"{x:.3f}" for x in q_n))
print("  wrong Null        " + " ".join(f"{x:.3f}" for x in q_p))
print("\nwrong Null answers: score, flagged, weakest sentence")
for q in P:
    r = result[q]
    print(f"  {r['answer_score']:.3f} {'FLAG' if r['flagged'] else '    '} | {q[:70]}\n"
          f"         -> {r['weakest_sentence'][:150]}")
print("\ncorrect non-Null answers flagged (first 12): score, weakest sentence")
for q in [q for q in N if result[q]["flagged"]][:12]:
    r = result[q]
    print(f"  {r['answer_score']:.3f} {r['type']:<6} | {q[:70]}\n"
          f"         -> {r['weakest_sentence'][:150]}")
print("\nper-question scores: logs/v5d_step0_scores.jsonl")
