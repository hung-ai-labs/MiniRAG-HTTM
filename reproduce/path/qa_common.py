"""Free Gemini transport for controlled QA; unchanged repository limiter."""
import asyncio
import json
from path_common import configure_free_gemini,read,append
MODEL='gemini-flash-lite-latest'

class DailyQuotaExhausted(RuntimeError): pass

def quota_metadata(body):
    result=[]
    def visit(value):
        if isinstance(value,dict):
            if 'quotaId' in value:
                result.append({k:v for k,v in value.items() if k in ('quotaId','quotaMetric','quotaValue','quotaDimensions')})
            for v in value.values(): visit(v)
        elif isinstance(value,list):
            for v in value: visit(v)
    visit(body)
    return result

class FreeAPI:
    def __init__(self,output):
        configure_free_gemini()
        from minirag.llm import gemini
        self.gemini=gemini;self.output=output;self.daily=set()
        self.pool=gemini._get_pool('chat')
        self.resolved={}
        for r in read(output/'api_calls.jsonl'):
            if r.get('success'): self.resolved.setdefault(r['role'],r['resolved_model'])
        print(json.dumps({'api':'public Gemini free tier','keys':len(self.pool.keys),
                          'rpm':self.pool.rpm,'tpm':self.pool.tpm,'requested_model':MODEL}),flush=True)

    async def call(self,prompt,system=None,role='generation'):
        from openai import RateLimitError,AuthenticationError,PermissionDeniedError
        messages=([{'role':'system','content':system}] if system else [])+[{'role':'user','content':prompt}]
        cost=self.gemini._estimate_tokens(''.join(m['content'] for m in messages))+1000
        for attempt in range(max(3,len(self.pool.keys)*2)):
            if set(self.pool.keys)<=self.daily:
                raise DailyQuotaExhausted('All configured free-tier keys reached daily quota')
            key=await self.pool.acquire(cost)
            if key in self.daily: continue
            try:
                response=await asyncio.wait_for(self.gemini._client(key,self.gemini.GEMINI_BASE_URL).chat.completions.create(
                    model=MODEL,messages=messages,max_tokens=1024 if role=='generation' else 16),timeout=180)
            except Exception as exc:
                metadata=quota_metadata(getattr(exc,'body',None))
                daily=any('PerDay' in q.get('quotaId','') or 'per_day' in q.get('quotaMetric','').lower() for q in metadata)
                append(self.output/'api_calls.jsonl',{'success':False,'role':role,'status':getattr(exc,'status_code',None),
                    'kind':type(exc).__name__,'quota':metadata,'daily_quota':daily})
                if isinstance(exc,RateLimitError): self.pool.penalize(key)
                elif isinstance(exc,(AuthenticationError,PermissionDeniedError)): self.pool.disable(key)
                if daily:
                    self.daily.add(key)
                    print(f'Free daily quota exhausted: {len(self.daily)} configured key(s)',flush=True)
                    continue
                print(f'API retry {attempt+1}: {type(exc).__name__}; status={getattr(exc,"status_code",None)}',flush=True)
                if attempt+1==max(3,len(self.pool.keys)*2): raise RuntimeError('API failed; run remains incomplete') from None
                await asyncio.sleep(10*(attempt+1)); continue
            self.pool.succeeded(key)
            resolved=getattr(response,'model',None) or MODEL
            if role in self.resolved and self.resolved[role]!=resolved:
                raise RuntimeError('Provider resolved model changed within this run')
            self.resolved[role]=resolved
            content=response.choices[0].message.content if response.choices else None
            if not content: raise RuntimeError('Empty API output; not scored')
            if r'\u' in content: content=self.gemini.safe_unicode_decode(content.encode('utf-8'))
            usage=getattr(response,'usage',None)
            append(self.output/'api_calls.jsonl',{'success':True,'role':role,'resolved_model':resolved,
                'finish_reason':response.choices[0].finish_reason,'usage':usage.model_dump() if usage else None})
            return content
        raise DailyQuotaExhausted('No healthy free-tier capacity; progress retained')
