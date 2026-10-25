# MultiHop-RAG dataset

`raw/` is the original release, unchanged: `corpus.json` (609 news articles) and
`MultiHopRAG.json` (2,556 questions: comparison 856, inference 816, temporal 583,
null 301). There are no question IDs and no official split.

`processed/` is generated from `raw/` by
`reproduce/research/prepare_multihop_rag.py` and committed byte-for-byte
(`-text` in `.gitattributes`), so every machine indexes and asks exactly the same
strings. Do not edit it by hand.

| File | Contents | Used by |
|---|---|---|
| `docs.jsonl` | `doc_id` (= url), `minirag_doc_id`, metadata, `text` = the exact string to index | indexing |
| `queries.jsonl` | `query_id`, `question`, `type` (no answers) | anything that must not see gold |
| `gold.jsonl` | `query_id`, `answer`, `evidence` (`doc_id`, `fact`) | judging, retrieval scoring |
| `questions.csv` | `Question`, `Gold Answer`, `Type`, `query_id` | `qa_run.py --questions`, `Step_2_evaluate.py --queryset` |
| `manifest.json` | input/output sha256, counts, text format version | provenance checks |

`query_id` is `mhr-NNNN`, the row position in `MultiHopRAG.json`. `minirag_doc_id`
is the ID `MiniRAG.insert` assigns to `text`, which links index records back to
articles.

## Indexed text

Each article is indexed as a short header followed by the body:

```text
Title: <title>
Source: <outlet>
Author: <author>            (omitted for the 68 articles without one)
Published: November 27, 2023 (2023-11-27T08:45:59+00:00)
Category: <category>

<body>
```

91% of questions name the outlet and 33% name a date, while the outlet appears in
only 31% of bodies and the publication date in none, so the body alone would
leave most questions unanswerable. The URL is not included. Only the first
chunk of a long article carries the header; the chunker is unchanged.
Changing this format changes the index: bump `TEXT_FORMAT_VERSION` in the script
and re-index.

## Chunks

`processed/chunk_stats.json` (`reproduce/research/count_mhr_chunks.py`, MiniRAG's
own chunker and defaults): **1,656 chunks**, so about 3,312 index LLM calls before
retries. The shortest article is 1,113 tokens, above the 1,100-token stride, so
every article spans at least two chunks and **1,047 chunks (63%) carry no
Title/Source/Published header**. 73 tail chunks are no longer than the
100-token overlap and repeat the end of the previous chunk.

## Dev / internal-test split

`splits/` holds the frozen split (`reproduce/research/make_mhr_split.py`, seed 13):
**dev 400** questions stratified by type (comparison 134, inference 128,
temporal 91, null 47) and an **internal test** of the other 2,156 (722 / 688 /
492 / 254). Only `dev400.csv` exists as a question file; the internal-test CSV
is written with `--emit-test` when the final confirmation opens it.

The corpus is shared, so the split cannot separate evidence: 1,604 of the 1,902
test questions with evidence share at least one evidence article with dev, and
638 have exactly the evidence set of some dev question
(`split_manifest.json`, `evidence_overlap`). Report this as a limitation.

## Regenerate or verify

```sh
python reproduce/research/prepare_multihop_rag.py           # write processed/
python reproduce/research/prepare_multihop_rag.py --check   # verify, write nothing
python reproduce/research/count_mhr_chunks.py --check
python reproduce/research/make_mhr_split.py --check
```

The script refuses raw files whose sha256 differs from the pinned values, and
refuses to overwrite differing processed files without `--force`.
