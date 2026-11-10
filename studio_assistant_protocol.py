"""Native function contracts and response decoding for the document assistant."""
import json

def function(name,description,properties=None,required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties or {},'required':list(required)}}}
S={'type':'string'};I={'type':'integer'};B={'type':'boolean'}
def tool_definitions(mode):
    tools=[function('list_files','列出项目文件'),function('read_file','读取指定文件行范围；start>=1，每次最多160行。默认80行。',{'path':S,'start':{'type':'integer','minimum':1},'lines':{'type':'integer','minimum':1,'maximum':160}},('path',)),
           function('search','字面检索，优先检索必要片段',{'query':S,'path':S},('query',)),function('diagnostics','读取精简编译报错'),function('environment','查看可用字体与编译环境'),function('references','检查引用'),function('glossary','读取术语表'),
           function('layout_check','检查 PDF 版面几何和页次，默认关联页或代表页，不重读全文。',{'pages':{'type':'array','items':I,'maxItems':12}}),
           function('read_page','读取 PDF 页面；需要视觉判断时 visual=true，最多按需查看代表页。',{'page':I,'visual':B},('page',)),
           function('read_attachment','读取明确关联的附件，PDF 可指定 page 和 visual',{'id':S,'start':I,'lines':I,'page':I,'visual':B},('id',))]
    if mode=='agent':tools.extend([function('edit','先读取文件，再按准确原文替换副本',{'path':S,'before':S,'after':S,'replace_all':B},('path','before','after')),function('compile','编译候选并验证 PDF；源码未变则复用结果'),function('resources','恢复编译器已知缺少的公共资源')])
    return tools

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
