"""Native function contracts and response decoding for the document assistant."""
import json

def tool_definitions(mode):
    from studio_assistant_tools import builtin_schemas
    return builtin_schemas(mode)

def decode(choice):
    message=choice.get('message',{});calls=message.get('tool_calls') or []
    if calls:
        if choice.get('finish_reason') not in {'tool_calls','stop'}:raise ValueError('工具响应未完整结束')
        return {'message':message.get('content') or '', 'calls':[{'tool':c['function']['name'],'args':json.loads(c['function']['arguments']),'id':c['id']} for c in calls], 'done':False}
    if choice.get('finish_reason')!='stop':raise ValueError('响应未完整结束，已保留当前进度')
    text=message.get('content') or ''
    # Legacy JSON is accepted, but normal final answers need no artificial done flag.
    if text.lstrip().startswith(('{','```json')):
        raw=text.strip()
        if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('响应格式无效')
        if not any(key in value for key in ('message','calls','done','question')):return {'message':text,'calls':[],'done':True}
        return value
    return {'message':text,'calls':[],'done':True}

def replay(record):
    call=record.get('nativeCall')
    if call:
        content=record['content']
        result=[{'role':'assistant','content':None,'tool_calls':[call]},
                {'role':'tool','tool_call_id':call['id'],'content':content if isinstance(content,str) else '页面图像见下一条消息。'}]
        if not isinstance(content,str):result.append({'role':'user','content':content})
        return result
    return [{'role':'assistant','content':json.dumps({'tool':record['tool'],'args':record['args']},ensure_ascii=False)}, {'role':'user','content':record['content']}]
