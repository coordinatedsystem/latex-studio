"""Durable append-only model history and bounded request projection.

Architecture port of DeepSeek Harness session/agent-loop contracts. Local data only.
"""
import copy,hashlib,json,os,threading,time
from pathlib import Path
from studio_assistant_context import compact_tool,tool_history
from studio_assistant_protocol import replay

def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()

def context_size(messages):
    # Base64 byte length is not a text-token estimate. Count image evidence separately.
    size=0
    for message in messages:
        content=message.get('content')
        if isinstance(content,list):
            size+=sum(4000 if part.get('type')=='image_url' else len(encoded(part)) for part in content)
        else:size+=len(encoded(message))
    return size


class SessionJournal:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.events=[];self.messages=[];self.lock=threading.RLock()
        if self.path.exists():
            raw=self.path.read_bytes();lines=raw.splitlines(keepends=True);valid=0
            for index,line in enumerate(lines):
                if not line.endswith(b'\n'):break
                try:event=json.loads(line)
                except (ValueError,UnicodeError):
                    if index!=len(lines)-1 or line.endswith(b'\n'):raise ValueError('助手事件记录损坏，不能自动重放')
                    break
                if not isinstance(event,dict) or not isinstance(event.get('data'),dict) or not isinstance(event.get('type'),str):raise ValueError('助手事件格式无效')
                if event.get('seq')!=len(self.events)+1:raise ValueError('助手事件序号不连续')
                self.events.append(event);self.fold(event);valid+=len(line)
            if valid<len(raw):
                # Preserve the interrupted tail for diagnosis before repairing framing.
                backup=self.path.with_suffix('.interrupted-'+str(time.time_ns()))
                backup.write_bytes(raw[valid:])
                with self.path.open('r+b') as file:file.truncate(valid)
                self.append('session/recovered',{'interruptedTail':True})
    def fold(self,event):
        data=event['data']
        if event['type']=='context/reset':self.messages=copy.deepcopy(data['messages'])
        elif event['type']=='context/append':self.messages.extend(copy.deepcopy(data['messages']))
    def append(self,kind,data):
        with self.lock:
            event={'seq':len(self.events)+1,'type':kind,'data':copy.deepcopy(data),'at':time.time()}
            with self.path.open('ab') as file:
                file.write((encoded(event)+'\n').encode());file.flush();os.fsync(file.fileno())
            self.events.append(event);self.fold(event);return event['seq']
    def context(self,messages,request=True):
        with self.lock:
            prefix=0
            for a,b in zip(self.messages,messages):
                if a!=b:break
                prefix+=1
            reused=len(encoded(self.messages[:prefix])) if prefix else 0
            if prefix==len(self.messages):
                if len(messages)>prefix:self.append('context/append',{'messages':messages[prefix:]})
            else:self.append('context/reset',{'messages':messages,'reason':'projection-change'})
            snapshot=copy.deepcopy(self.messages)
            if request:self.append('request/context',{'hash':digest(snapshot),'messageCount':len(snapshot),'chars':len(encoded(snapshot)),'reusedPrefixChars':reused})
            return snapshot,reused
    def recover_interrupted_turn(self):
        boundary=next((e for e in reversed(self.events) if e['type'] in {'turn/start','turn/end'}),None)
        if not boundary or boundary['type']!='turn/start':return
        calls={};projected={c['id'] for message in self.messages for c in message.get('tool_calls',[])}
        for event in list(self.events)[boundary['seq']:]:
            data=event['data']
            if event['type']=='assistant/response':
                for call in data.get('value',{}).get('calls',[]):
                    if call.get('id'):calls[call['id']]={'call':call,'started':False,'output':None}
            elif event['type']=='tool/call' and data.get('id') in calls:calls[data['id']]['started']=True
            elif event['type']=='tool/result' and data.get('id') in calls:calls[data['id']]['output']=data['result']
        suffix=[]
        for ident,entry in calls.items():
            if ident in projected:continue
            call=entry['call'];output=entry['output']
            if output is None:
                recovery=ToolCallRecovery([call])
                if entry['started']:recovery.started(call)
                record=recovery.recover()[0]
            else:
                record={'tool':call['tool'],'args':call.get('args',{}),'summary':{k:v for k,v in output.items() if k in {'error','success','edits','path','revision'}},'content':encoded(output)[:9000],'nativeCall':{'id':ident,'type':'function','function':{'name':call['tool'],'arguments':encoded(call.get('args',{}))}}}
            self.append('tool/recovered',record);suffix.extend(replay(compact_tool(record)))
        if suffix:self.context(self.messages+suffix,request=False)
        self.close_step('interrupted')
        self.append('turn/end',{'success':False,'reason':'interrupted','automaticallyRetriedTools':False})

    def close_step(self,reason='settled'):
        for event in reversed(self.events):
            if event['type']=='step/end':return
            if event['type']=='step/start':
                self.append('step/end',{'step':event['data']['step'],'reason':reason});return
    def request_contexts(self,attempts=False):
        messages=[];result=[]
        for event in self.events:
            if event['type']=='context/reset':messages=copy.deepcopy(event['data']['messages'])
            elif event['type']=='context/append':messages.extend(copy.deepcopy(event['data']['messages']))
            elif event['type']=='request/context':
                if digest(messages)!=event['data']['hash']:raise ValueError('请求历史校验失败')
                if not attempts:result.append(copy.deepcopy(messages))
            elif attempts and event['type']=='request/start':result.append(copy.deepcopy(messages))
        return result

class ModelContext:
    def __init__(self,base,journal,max_chars=60000,seed=None,accepted=0):
        self.base=copy.deepcopy(base);self.messages=copy.deepcopy(seed if seed is not None else base);self.journal=journal
        self.max_chars=max_chars;self.accepted=accepted;self.compactions=0;self.notices=set()
    def prepare(self,trail,notice=None,request=True):
        # Existing messages never move during normal growth: DeepSeek can cache the prefix.
        for record in trail[self.accepted:]:self.messages.extend(replay(compact_tool(record)))
        self.accepted=len(trail)
        if notice and notice not in self.notices:
            self.messages.append({'role':'user','content':notice});self.notices.add(notice)
        if context_size(self.messages)>self.max_chars:
            self.messages=copy.deepcopy(self.base)+tool_history(trail)
            if notice:self.messages.append({'role':'user','content':notice})
            self.compactions+=1;self.journal.append('context/compacted',{'count':self.compactions})
        snapshot,reused=self.journal.context(self.messages,request=request)
        return snapshot,{'contextChars':context_size(snapshot),'reusedPrefixChars':reused,'compactions':self.compactions}


class ToolCallRecovery:
    """DSH-style conservative settlement: never replay an uncertain mutation automatically."""
    def __init__(self,calls=()):self.pending=[{'call':copy.deepcopy(call),'started':False} for call in calls]
    def started(self,call):
        for entry in self.pending:
            if entry['call']==call:entry['started']=True;return
    def settled(self,call):
        for i,entry in enumerate(self.pending):
            if entry['call']==call:self.pending.pop(i);return
    def recover(self):
        records=[]
        for entry in self.pending:
            call=entry['call'];name=call.get('tool','unknown');args=call.get('args',{})
            code='TOOL_OUTCOME_UNKNOWN' if entry['started'] else 'ABORTED_BEFORE_DISPATCH'
            output={'error':code,'message':'执行结果未知。先检查当前候选状态，不要直接重复编辑。' if entry['started'] else '本次调用尚未执行；仍有需要时可以重新调用。'}
            records.append({'tool':name,'args':args,'summary':output,'content':encoded(output),'nativeCall':{'id':call['id'],'type':'function','function':{'name':name,'arguments':encoded(args)}} if call.get('id') else None})
        self.pending=[];return records
