"""Two-document synthetic MiniRAG end-to-end check using only local Qwen.

Technical canary, not dataset pilot, benchmark, judge or scientific result.
Uses this repo's existing hf_embed pooling exactly, on CPU and cached weights.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from local_qwen import LocalQwen, OPTIONS, MODEL, PINNED_MODEL_DIGEST, append, write_json

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    ('fixture-doc-a', 'Mira Chen\nMira Chen is a scientist. Mira Chen works at the Alder Research Institute. The Alder Research Institute is located in the city of Riverton.'),
    ('fixture-doc-b', 'Alder Research Institute\nThe Alder Research Institute was founded in 2018 by scientist Mira Chen. The Alder Research Institute conducts research in Riverton.')]
QUESTION = 'In which city is the Alder Research Institute where Mira Chen works located?'


async def run(args, report, client):
    # Restrict loading to the local cache, and leave the GPU to Ollama.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['MINIRAG_ANSWER_TYPE_FIX'] = '1'
    os.environ['MINIRAG_PATH2CHUNK_FIX'] = '0'
    os.environ['MINIRAG_CHUNK_CUT'] = ''
    os.environ['MINIRAG_CHUNK_FUSION'] = 'vector_bm25'
    os.environ['MINIRAG_CONTEXT_LOG'] = str((args.out / 'retrieval.jsonl').resolve())
    os.environ['MINIRAG_KW_CACHE'] = str((args.out / 'keyword_cache.jsonl').resolve())
    os.environ.pop('MINIRAG_KW_CACHE_ONLY', None)
    sys.path.insert(0, str(ROOT))
    from transformers import AutoModel, AutoTokenizer
    from minirag import MiniRAG, QueryParam
    from minirag.llm.hf import hf_embed
    from minirag.utils import EmbeddingFunc, compute_mdhash_id
    from minirag.prompt import PROMPTS

    started = time.perf_counter()
    name = 'sentence-transformers/all-MiniLM-L6-v2'
    tokenizer = AutoTokenizer.from_pretrained(name, local_files_only=True)
    embedding_model = AutoModel.from_pretrained(name, local_files_only=True).to('cpu')
    embedding_model.eval()

    async def embed(texts):
        return await hf_embed(texts, tokenizer=tokenizer, embed_model=embedding_model)

    async def complete(prompt, system_prompt=None, history_messages=None, **kwargs):
        # MiniRAG dataclasses.asdict deep-copies bound methods and their clients.
        # A plain closure keeps the network client's SSLContext out of that copy.
        return await client.complete(prompt, system_prompt=system_prompt,
                                     history_messages=history_messages, **kwargs)

    report['embedding'] = {'model': name, 'dimension': 384, 'device': 'cpu',
                           'implementation': 'existing minirag.llm.hf.hf_embed',
                           'weights_loaded_from_cache_only': True}
    rag = MiniRAG(working_dir=str(args.index), llm_model_func=complete,
                  llm_model_name=MODEL, llm_model_max_async=1, llm_model_max_token_size=200,
                  embedding_func=EmbeddingFunc(embedding_dim=384, max_token_size=1000, func=embed),
                  embedding_func_max_async=1, enable_llm_cache=False,
                  chunk_token_size=1200, chunk_overlap_token_size=100, entity_extract_max_gleaning=1)
    client.phase = 'index'
    for doc_id, text in DOCS:
        client.doc_id = doc_id
        client.chunk_id = compute_mdhash_id(text, prefix='chunk-')
        append(args.out / 'events.jsonl', {'at': datetime.now(timezone.utc).isoformat(), 'event': 'index_doc_start', 'doc_id': doc_id})
        await rag.ainsert(text)
        append(args.out / 'events.jsonl', {'at': datetime.now(timezone.utc).isoformat(), 'event': 'index_doc_end', 'doc_id': doc_id})
    client.doc_id = client.chunk_id = None
    report['index_elapsed_s'] = time.perf_counter()-started
    client.phase, client.query_id = 'kw_parse', 'synthetic-q1'
    param = QueryParam(mode='mini', only_need_context=True, top_k=60, max_token_for_text_unit=4000)
    context = await rag.aquery(QUESTION, param)
    # only_need_context should not silently turn into a canned failure string.
    if context is None or context == PROMPTS['fail_response']:
        report['retrieval_status'] = 'early_exit_no_context'
        write_json(args.out / 'generation.json', {'query_id': client.query_id, 'context': context,
                                                'status': 'early_exit', 'answer': PROMPTS['fail_response']})
        raise ValueError('Synthetic canary retrieval returned no usable context')
    report['retrieval_status'] = 'ok'
    system = PROMPTS['rag_response'].format(context_data=context, response_type=param.response_type)
    client.phase = 'answer'
    answer = await client.complete(QUESTION, system_prompt=system)
    generation = {'query_id': client.query_id, 'question': QUESTION,
                  'context': context, 'system_prompt': system, 'answer': answer,
                  'context_sha256': hashlib.sha256(context.encode()).hexdigest(), 'status': 'ok'}
    write_json(args.out / 'generation.json', generation)
    report['answer'] = answer
    report['synthetic_answer_contains_expected_city'] = 'riverton' in answer.lower()
    report['qa_call_path'] = 'rag.aquery only_need_context (real keyword parser + retrieval), then unchanged rag_response template via same local model'
    await rag._insert_done()
    report['index_files_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in args.index.iterdir() if p.is_file()}
    import networkx as nx
    graph = nx.read_graphml(args.index / 'graph_chunk_entity_relation.graphml')
    report['index_counts'] = {'nodes': graph.number_of_nodes(), 'edges': graph.number_of_edges(),
                              'docs': len(DOCS)}
    report['pipeline_status'] = 'passed' if report['synthetic_answer_contains_expected_city'] else 'answer_requires_review'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    args = parser.parse_args()
    args.out, args.index = args.out.resolve(), args.index.resolve()
    if args.out.exists() or args.index.exists():
        parser.error('Use new run and index directories; existing artifacts are preserved')
    if args.out == args.index or args.out in args.index.parents or args.index in args.out.parents:
        parser.error('Run and index directories must be distinct, non-nested directories')
    args.out.mkdir(parents=True)
    args.index.mkdir(parents=True)
    report = {'purpose': 'two_synthetic_documents_technical_canary_not_2wiki_benchmark',
              'started_at': datetime.now(timezone.utc).isoformat(), 'pipeline_status': 'running',
              'condition': 'local_Qwen2.5_3B_Instruct_GGUF_Q4_K_M', 'model': MODEL,
              'model_digest': PINNED_MODEL_DIGEST, 'options': OPTIONS,
              'caps': {'extract': 4096, 'glean': 4096, 'kw_parse': 1024, 'answer': 1024},
              'python': sys.version.split()[0], 'index': str(args.index),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'client_script_sha256': hashlib.sha256((Path(__file__).parent/'local_qwen.py').read_bytes()).hexdigest()}
    write_json(args.out / 'run_manifest.json', report)
    write_json(args.out / 'synthetic_inputs.json', {'documents': [{'doc_id': i, 'text': t} for i, t in DOCS], 'question': QUESTION})
    client = LocalQwen(args.out)
    try:
        write_json(args.out / 'runtime.json', client.inspect())
        asyncio.run(run(args, report, client))
    except Exception as exc:
        report['pipeline_status'] = 'failed'
        report['error_type'] = type(exc).__name__
        append(args.out/'events.jsonl', {'event': 'failed', 'error_type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        try:
            client.unload()
            report['unloaded_at_end'] = True
        except Exception:
            report['unloaded_at_end'] = False
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(args.out / 'run_manifest.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
