"""Local persistent request budget. No credentials or source text are stored."""
from pathlib import Path
from datetime import datetime
import threading
from studio_storage import read_json, write_json

class Usage:
    def __init__(self,data):
        self.path=Path(data)/'ai-usage.json';self.lock=threading.RLock()
    def load(self):
        value=read_json(self.path,{})
        day=datetime.now().astimezone().strftime('%Y-%m-%d')
        if value.get('day')!=day:
            value={'day':day,'limit':value.get('limit',20),'requests':0,'tokens':0,'failures':0}
        return value
    def status(self):
        with self.lock:
            value=self.load();return {**value,'remaining':max(0,value['limit']-value['requests']) if value['limit'] else None}
    def configure(self,limit):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 0<=limit<=10000:
            raise ValueError('每日上限请输入 0～10000 的整数；0 表示不限')
        with self.lock:
            value=self.load();value['limit']=limit;write_json(self.path,value);return self.status()
    def request(self,call,*args,**kwargs):
        with self.lock:
            value=self.load()
            if value['limit'] and value['requests']>=value['limit']:
                raise ValueError('今日 AI 请求已达上限，可在“AI 用量”调整；未发出请求')
            day=value['day'];value['requests']+=1;write_json(self.path,value)
        try:
            response=call(*args,**kwargs)
        except Exception:
            with self.lock:
                value=self.load()
                if value['day']==day:value['failures']+=1;write_json(self.path,value)
            raise
        with self.lock:
            value=self.load()
            if value['day']==day:
                usage=response.get('usage',{}) if isinstance(response,dict) else {}
                try:tokens=max(0,int(usage.get('total_tokens',0)))
                except (TypeError,ValueError):tokens=0
                value['tokens']+=tokens;write_json(self.path,value)
        return response

_instances={}
_lock=threading.Lock()
def usage_for(data):
    key=str(Path(data).resolve())
    with _lock:
        if key not in _instances:_instances[key]=Usage(data)
        return _instances[key]
