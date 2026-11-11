"""Pinned public RECOMP extractive encoder; CPU only, no generative API.

Author inference: attention-mask mean pooling, raw dot product, no L2 normalize.
Long target turns are encoded in <=510-wordpiece scoring windows; selection
still keeps complete utterances. Every comparator sees the same window scores.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
import time

MODEL='fangyuan/hotpotqa_extractive_compressor'
REVISION='25d11ad98ac802590c903af50d8735049679e8ef'
WEIGHTS_SHA256='10108c9f3d4add5785a3d3f6f97cdf58befda3742d26c5d14c12df554e14579b'
DEFAULT_MODEL_DIR=Path(__file__).resolve().parents[1]/'.models'/'recomp-hotpotqa'


class RecompEncoder:
    def __init__(self,directory=DEFAULT_MODEL_DIR,cache_dir=None):
        import torch
        from transformers import AutoConfig,AutoModel,AutoTokenizer
        self.torch=torch;torch.set_num_threads(4);directory=Path(directory)
        weights_hash=hashlib.sha256((directory/'pytorch_model.bin').read_bytes()).hexdigest()
        if weights_hash!=WEIGHTS_SHA256:raise ValueError('Not the pinned public RECOMP weights')
        self.tokenizer=AutoTokenizer.from_pretrained(directory,local_files_only=True)
        self.model=AutoModel.from_config(AutoConfig.from_pretrained(directory,local_files_only=True))
        # weights_only prevents loading arbitrary pickled Python objects.
        state=torch.load(directory/'pytorch_model.bin',map_location='cpu',weights_only=True)
        removed=[k for k in ('embeddings.position_ids','embeddings.token_type_ids') if k in state]
        for k in removed:state.pop(k)
        self.model.load_state_dict(state,strict=True);self.model.eval()
        self.provenance={'model':MODEL,'revision':REVISION,'device':'CPU','local_files_only':True,
            'pooling':'attention_mask_mean','similarity':'raw_dot_product','l2_normalize':False,
            'unlearned_obsolete_buffers_removed':removed,'max_length':512,
            'long_input_policy':'510 wordpiece scoring windows; target source units not split',
            'weights_sha256':weights_hash,
            'config_sha256':hashlib.sha256((directory/'config.json').read_bytes()).hexdigest(),
            'tokenizer_sha256':hashlib.sha256((directory/'tokenizer.json').read_bytes()).hexdigest(),
            'author_code':'https://github.com/carriex/recomp/blob/main/run_extractive_compressor.py',
            'adaptation':'Whole utterance ranking + local source adjacency, not original fixed1/2-sentence evaluation',
            'trained_on_current_gold':False,'QA_calls':0,'judge_calls':0}
        self.cache_dir=Path(cache_dir) if cache_dir else None
        if self.cache_dir:self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.cache={};self.token_counts={};self.encoded_windows=0;self.cache_hits=0;self.elapsed=0.

    def key(self,text):
        return hashlib.sha256((json.dumps(self.provenance,sort_keys=True)+'\n'+text).encode()).hexdigest()

    def encode(self,texts):
        import numpy as np
        missing=[]
        for text in dict.fromkeys(texts):
            if text in self.cache:continue
            target=self.cache_dir/(self.key(text)+'.npy') if self.cache_dir else None
            ids=self.tokenizer(text,add_special_tokens=False,truncation=False)['input_ids']
            self.token_counts[text]=len(ids)
            if target is not None and target.exists():
                arr=np.load(target,allow_pickle=False)
                if arr.ndim!=2 or arr.shape[1]!=768 or not np.isfinite(arr).all():raise ValueError('Corrupt RECOMP vector cache')
                self.cache[text]=arr;self.cache_hits+=1
            else:missing.append((text,ids,target))
        jobs=[]
        for text,ids,target in missing:
            segments=[ids[i:i+510] for i in range(0,len(ids),510)] or [[]]
            for segment in segments:
                jobs.append((text,[self.tokenizer.cls_token_id,*segment,self.tokenizer.sep_token_id]))
        jobs.sort(key=lambda x:len(x[1]));collected={}
        started=time.perf_counter()
        for start in range(0,len(jobs),16):
            batch=jobs[start:start+16]
            tokens=self.tokenizer.pad([{'input_ids':ids,'attention_mask':[1]*len(ids)} for _,ids in batch],padding=True,return_tensors='pt')
            with self.torch.inference_mode():
                hidden=self.model(**tokens).last_hidden_state
                mask=tokens['attention_mask'].unsqueeze(-1).bool()
                pooled=hidden.masked_fill(~mask,0.).sum(dim=1)/mask.sum(dim=1)
            for (text,_),vec in zip(batch,pooled.numpy()):collected.setdefault(text,[]).append(vec)
            self.encoded_windows+=len(batch)
        self.elapsed+=time.perf_counter()-started
        for text,ids,target in missing:
            arr=np.stack(collected[text]);self.cache[text]=arr
            if target is not None:
                # Atomic publication prevents another query worker reading half a cache file.
                fd, pending = tempfile.mkstemp(dir=self.cache_dir, suffix='.npy')
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        np.save(stream, arr, allow_pickle=False)
                    os.replace(pending, target)
                finally:
                    if os.path.exists(pending):os.unlink(pending)
        return [self.cache[t] for t in texts]

    def score(self,query,cats):
        import numpy as np
        units=[s for cat in cats.values() for s in cat['segments'] if s['kind']!='header']
        self.encode([query,*[u['score_text'] for u in units]])
        q=self.cache[query]
        return {u['id']:float(np.max(q@self.cache[u['score_text']].T)) for u in units}
