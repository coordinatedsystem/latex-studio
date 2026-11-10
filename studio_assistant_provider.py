"""DeepSeek adapter: frozen calls, bounded transport retries and cooperative cancellation.

Ported architecture from DeepSeek Harness (MIT, see third-party notice).
"""
import copy,json,re,threading
import studio_ai
from studio_assistant_protocol import decode

class DeepSeekProvider:
    def __init__(self,owner):self.owner=owner
    def request(self,s,messages,tools,journal=None):
        owner=self.owner
        config=studio_ai.assistant_for(owner.storage.data).config(True)['deepseek']
        if not config.get('configured'):raise ValueError('请先配置 DeepSeek 服务')
        payload={'model':config['model'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools),'tool_choice':'auto','thinking':{'type':'disabled'},'stream':False,'max_tokens':4000}
        # Never persist headers or credentials. Retry the same frozen request only.
        for attempt in range(3):
            owner.checkpoint();result={};done=threading.Event()
            def send(result=result,done=done):
                try:result['value']=studio_ai.request_json('https://api.deepseek.com/chat/completions',copy.deepcopy(payload),{'Authorization':'Bearer '+config['key']})
                except Exception as exc:result['error']=exc
                finally:done.set()
            owner.update(s,requestCount=s['requestCount']+1)
            if journal:
                from studio_assistant_session import digest
                header={'model':config['model'],'tools':tools,'thinking':payload['thinking'],'max_tokens':payload['max_tokens']}
                latest=next((e['data'] for e in reversed(journal.events) if e['type']=='request/header'),None)
                if latest!=header:journal.append('request/header',header)
                journal.append('request/start',{'number':s['requestCount'],'attempt':attempt,'headerHash':digest(header)})
            threading.Thread(target=send,daemon=True).start()
            while not done.wait(.1):owner.checkpoint()
            owner.checkpoint()
            if 'error' not in result:break
            error=result['error']
            retry=isinstance(error,ValueError) and bool(re.search(r'HTTP (?:429|500|502|503|504)',str(error)))
            if journal:journal.append('request/error',{'retry':bool(retry and attempt<2),'message':str(error)[:500]})
            if not retry or attempt==2:raise error
            owner.update(s,stage='服务暂时繁忙，正在重试…')
            if owner.cancel_event.wait(1+attempt):owner.checkpoint()
        response=result['value'];usage=response.get('usage',{})
        s['tokens']+=max(0,int(usage.get('total_tokens',0)))
        for key,field in [('prompt_tokens','prompt_tokens'),('completion_tokens','completion_tokens'),('cached_tokens','prompt_cache_hit_tokens')]:s['usage'][key]+=max(0,int(usage.get(field,0)))
        if journal:journal.append('request/end',{'usage':usage})
        return decode(response['choices'][0])
