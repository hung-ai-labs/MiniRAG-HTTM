"""Shared offline experiment utilities; no historical C-arm selection here."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'reproduce'))
sys.path.insert(0,str(ROOT/'reproduce/screening'))
os.environ.setdefault('HF_HUB_OFFLINE','1')
os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
from minirag.utils import EmbeddingFunc
from screen_variant import dev_rows,gold_map,evidence,mcnemar_p

CACHE=ROOT/'logs/path/cache/kw_cache.jsonl'
MODEL='gemini-flash-lite-latest'


def digest(data):return hashlib.sha256(data.encode()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def append(path,record):
    with path.open('a',encoding='utf-8') as fh:
        fh.write(json.dumps(record,ensure_ascii=False)+'\n');fh.flush()


async def forbidden_llm(*args,**kwargs):
    raise RuntimeError('Offline context stage attempted an LLM call')


def embedding():
    """Same pinned single-query embedding and RAM loading as previous runs."""
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from safetensors.torch import load
    from transformers import AutoConfig,AutoModel,AutoTokenizer
    torch.set_num_threads(4)
    path=Path(snapshot_download('sentence-transformers/all-MiniLM-L6-v2',
        revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41',local_files_only=True))
    tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
    model=AutoModel.from_config(AutoConfig.from_pretrained(path,local_files_only=True))
    weights=load((path/'model.safetensors').read_bytes())
    weights.pop('embeddings.position_ids',None);model.load_state_dict(weights);model.eval()
    cache={}
    async def embed(texts):
        for text in texts:
            if text not in cache:
                with torch.inference_mode():
                    ids=tokenizer([text],return_tensors='pt',truncation=True).input_ids
                    cache[text]=model(ids).last_hidden_state.mean(dim=1)[0].numpy()
        return np.stack([cache[t] for t in texts]).copy()
    return EmbeddingFunc(embedding_dim=384,max_token_size=1000,func=embed)


def configure_free_gemini():
    """Historical free-tier helper, kept separate from current profile choices."""
    keys=list(dict.fromkeys(v for k,v in os.environ.items()
        if k.startswith('GEMINI_API_KEY') and v.startswith('AIza')))
    if not keys:raise RuntimeError('No configured Gemini free-tier keys')
    for key in list(os.environ):
        if key.startswith('GEMINI_API_KEY') or key in ('GOOGLE_API_KEY','GEMINI_API_BASE',
            'MINIRAG_SLM_URL','MINIRAG_SLM_KEY','MINIRAG_SLM_SEED','MINIRAG_MAX_TOKENS'):
            os.environ.pop(key,None)
    os.environ['GEMINI_API_KEYS']=','.join(keys)
