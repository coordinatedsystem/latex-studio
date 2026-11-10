'use strict';
// Conversation UI owns its state; existing review and document panes stay independent.
const studioAssistant={surface:'conversation',mode:'chat',project:null,id:null,job:null,contexts:[],pages:[],attachments:[],ticket:0,polling:false,timer:null,renderKey:null};
function conversationRemember(){try{if(studioAssistant.project)localStorage.setItem('studio.assistant.'+studioAssistant.project,JSON.stringify({id:studioAssistant.id,mode:studioAssistant.mode}));}catch{}}
function conversationNotice(message=''){const el=$('#conversationError');el.textContent=message;el.hidden=!message;}
function conversationWatch(fn){return async(...args)=>{try{conversationNotice();await fn(...args);}catch(e){conversationNotice(e.message);}};}
function conversationSurface(surface){studioAssistant.surface=surface;$('#writingWorkbench').classList.toggle('conversation-enabled',surface==='conversation');$$('[data-assistant-surface]').forEach(b=>b.classList.toggle('active',b.dataset.assistantSurface===surface));writingSetView('content');conversationControls();}
function conversationControls(){
 const running=!!studioAssistant.job?.running||!!studioAssistant.sending;
 $$('[data-assistant-mode]').forEach(b=>{b.disabled=running;b.classList.toggle('active',b.dataset.assistantMode===studioAssistant.mode);b.setAttribute('aria-pressed',String(b.dataset.assistantMode===studioAssistant.mode));});
 $('#conversationSend').hidden=running;$('#conversationStop').hidden=!running;$('#conversationStop').disabled=!!studioAssistant.stopping;$('#conversationStop').setAttribute('aria-label',studioAssistant.stopping?'正在停止':'停止生成');$('#conversationStop').title=studioAssistant.stopping?'正在停止后续操作':'停止 · Esc';$('#conversationSend').disabled=studioAssistant.sending||!$('#conversationInput').value.trim();
 $('#conversationHistory').disabled=running;$('#conversationContext').disabled=running;$('#conversationUpload').disabled=running;$('#conversationNew').disabled=running;$('#conversationInput').disabled=false;
 $('#conversationModeHint').textContent=studioAssistant.mode==='chat'?'围绕文档讨论':'完成任务并验证结果';
 const job=studioAssistant.job;$('#conversationApply').hidden=job?.chatMode!=='agent'||job?.success!==true||!job?.verified||!job?.changedPaths?.length||job?.applied||running;$('#conversationApply').disabled=!!job?.stale;
 $('#conversationUndo').hidden=!job?.applied;$('#conversationUndo').disabled=!job?.canUndo||running;
 $('#conversationPreview').hidden=!job?.verified||!job?.changedPaths?.length||running;
 $('#conversationUsage').textContent=job?`${(job.tokens||0).toLocaleString()} tokens · ${job.requestCount||0} 次请求`+(job.usage?.cached_tokens?` · 缓存 ${job.usage.cached_tokens.toLocaleString()}`:''):'';
 $('#conversationStage').textContent=studioAssistant.stopping?'正在停止…':studioAssistant.sending?'准备中…':job?.running?job.stage:'';
 $('#conversationContextList').innerHTML=[...studioAssistant.contexts.map((c,i)=>`<span>${esc(c.path)} · 选区<button type="button" data-context-remove="${i}" aria-label="移除选区">×</button></span>`),...studioAssistant.pages.map((n,i)=>`<span>第 ${n} 页<button type="button" data-page-remove="${i}" aria-label="移除页面">×</button></span>`),...studioAssistant.attachments.map((a,i)=>`<span>${esc(a.name)}<button type="button" data-attachment-remove="${i}" aria-label="移除附件">×</button></span>`)].join('');
}
function conversationToolSteps(events){
 const steps=[];
 for(const [index,event] of events.entries()){
  if(event.tool==='thinking'){steps.push({...event,index,narrative:true});continue;}
  const previous=steps.at(-1);
  if(previous?.tool===event.tool&&previous.status==='running'&&event.status!=='running')Object.assign(previous,event,{detail:[previous.detail,event.detail].filter(Boolean).join(' · ')});
  else steps.push({...event,index});
 }
 return steps;
}
function conversationMessageHtml(text){
 const inline=line=>line.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
 return esc(text).split(/(```[\s\S]*?```)/g).map(part=>{
  if(part.startsWith('```'))return '<pre class="conversation-code">'+part.replace(/^```[^\n]*\n?|```$/g,'')+'</pre>';
  const blocks=[];let paragraph=[],items=[],ordered=false;
  const flushParagraph=()=>{if(paragraph.length){blocks.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[];}};
  const flushItems=()=>{if(items.length){const tag=ordered?'ol':'ul';blocks.push('<'+tag+'>'+items.map(item=>'<li>'+inline(item)+'</li>').join('')+'</'+tag+'>');items=[];}};
  for(const line of part.split('\n')){
   if(!line.trim()){flushParagraph();flushItems();continue;}
   const heading=line.match(/^#{1,4}\s+(.+)$/),bullet=line.match(/^[-*]\s+(.+)$/),number=line.match(/^\d+[.)]\s+(.+)$/);
   if(heading){flushParagraph();flushItems();blocks.push('<strong class="conversation-answer-heading">'+inline(heading[1])+'</strong>');}
   else if(bullet||number){flushParagraph();if(items.length&&ordered!==!!number)flushItems();ordered=!!number;items.push((bullet||number)[1]);}
   else{flushItems();paragraph.push(line);}
  }
  flushParagraph();flushItems();return blocks.join('');
 }).join('');
}
function conversationRender(){
 const job=studioAssistant.job,key=job?.id+':'+job?.revision+':'+job?.applied+':'+job?.undone;
 conversationControls();if(key===studioAssistant.renderKey)return;studioAssistant.renderKey=key;
 const list=$('#conversationMessages'),nearBottom=list.scrollHeight-list.scrollTop-list.clientHeight<100,scrollTop=list.scrollTop;
 const previousLog=list.querySelector('.conversation-tools'),workOpen=previousLog&&previousLog.dataset.job===job?.id?previousLog.open:!!job?.running;
 const allMessages=job?.messages||[],finalMessage=!job?.running&&allMessages.at(-1)?.role==='assistant'?allMessages.at(-1):null;
 const messages=finalMessage?allMessages.slice(0,-1):allMessages;
 list.innerHTML=messages.length?messages.map(m=>`<article class="conversation-message ${m.role==='user'?'from-user':'from-assistant'}"><header>${m.role==='user'?'你':'Studio'}${m.mode?' · '+(m.mode==='agent'?'Agent':'Chat'):''}</header><div>${conversationMessageHtml(m.content)}</div></article>`).join(''):'<div class="conversation-empty"><span>✦</span><p>从文档开始对话</p></div>';
 const steps=conversationToolSteps(job?.events||[]);
 if(steps.length){list.insertAdjacentHTML('beforeend',`<details class="conversation-tools" data-job="${esc(job.id)}" ${workOpen?'open':''}><summary>${job.running?'<span class="spinner"></span> ':''}${job.running?esc(job.stage):job.stopRequested?'已停止的工作记录':'查看工作记录'}</summary><ol>${steps.map(e=>`<li data-event-index="${e.index}" class="${e.status}"><span class="conversation-step-icon" aria-hidden="true">${e.status==='running'?'◌':e.status==='failed'?'!':'✓'}</span><div><strong>${e.narrative?'工作说明':esc(e.label)}</strong>${e.detail?`<p>${esc(e.detail)}</p>`:''}</div></li>`).join('')}</ol></details>`);}
 if(finalMessage)list.insertAdjacentHTML('beforeend',`<article class="conversation-message from-assistant"><header>Studio${finalMessage.mode?' · '+(finalMessage.mode==='agent'?'Agent':'Chat'):''}</header><div>${conversationMessageHtml(finalMessage.content)}</div></article>`);
 if(job?.changedPaths?.length)list.insertAdjacentHTML('beforeend',`<div class="conversation-changes">${job.changedPaths.map(path=>`<button type="button" data-assistant-diff="${esc(path)}">${esc(path)} <span>查看修改</span></button>`).join('')}</div>`);
 if(job?.running)list.insertAdjacentHTML('beforeend',`<div class="conversation-working"><span class="spinner"></span>${esc(job.stage)}</div>`);
 list.scrollTop=nearBottom?list.scrollHeight:scrollTop;
}
async function conversationPoll(){
 if(studioAssistant.polling||!studioAssistant.id)return;const project=studioAssistant.project,id=studioAssistant.id,ticket=studioAssistant.ticket;const pollKey=project+':'+id+':'+ticket;studioAssistant.polling=pollKey;
 try{
  const job=await api('ai/assistant/job?id='+encodeURIComponent(id)+'&revision='+(studioAssistant.job?.revision??''));
  if(project!==state?.projectId||ticket!==studioAssistant.ticket||id!==studioAssistant.id)return;
  if(!job.unchanged){if((job.revision??0)<(studioAssistant.job?.revision??0))return;studioAssistant.stopping=!!job.running&&(!!studioAssistant.stopRequested||!!job.stopRequested);studioAssistant.job=job;if(!studioAssistant.attachments.length&&job.attachments?.length)studioAssistant.attachments=job.attachments;if(!studioAssistant.pages.length&&job.pages?.length)studioAssistant.pages=job.pages;conversationRender();}
  if(!job.running){clearInterval(studioAssistant.timer);studioAssistant.timer=null;}
 }catch(e){if(project===state?.projectId&&ticket===studioAssistant.ticket){clearInterval(studioAssistant.timer);conversationNotice(e.message);}}finally{if(studioAssistant.polling===pollKey)studioAssistant.polling=false;}
}
async function conversationProject(next){
 if(studioAssistant.project===next.projectId)return;
 clearInterval(studioAssistant.timer);studioAssistant.polling=false;studioAssistant.sending=false;studioAssistant.stopping=false;studioAssistant.stopRequested=false;studioAssistant.ticket++;studioAssistant.project=next.projectId;studioAssistant.id=null;studioAssistant.job=null;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.renderKey=null;
 try{const saved=JSON.parse(localStorage.getItem('studio.assistant.'+next.projectId)||'null');if(saved){studioAssistant.id=saved.id;studioAssistant.mode=saved.mode==='agent'?'agent':'chat';}}catch{}
 conversationRender();if(studioAssistant.id){await conversationPoll();if(studioAssistant.job?.running)studioAssistant.timer=setInterval(conversationPoll,1200);}
}
async function conversationContext(){
 if([...models.values()].some(i=>i.dirty))throw new Error('请先保存文件，再关联选区');
 if(writing.mode==='source'&&writing.range?.end>writing.range.start){
  const c={path:writing.file};
  // Server offsets use Unicode code points, as Python strings do.
  c.start=Array.from(writing.full.slice(0,writing.range.start)).length;c.end=Array.from(writing.full.slice(0,writing.range.end)).length;
  if(!studioAssistant.contexts.some(x=>JSON.stringify(x)===JSON.stringify(c)))studioAssistant.contexts.push(c);
 }else if(writing.mode==='pdf'){studioAssistant.pages=[...new Set([...studioAssistant.pages,...writing.pages])];}
 else throw new Error('请先在左侧选择内容');conversationControls();
}
async function conversationSend(){
 if(studioAssistant.sending||studioAssistant.job?.running)return;const question=$('#conversationInput').value.trim();if(!question)return;
 const project=state.projectId,ticket=studioAssistant.ticket;studioAssistant.sending=true;studioAssistant.stopRequested=false;studioAssistant.stopping=false;conversationControls();
 try{
  await saveAll();if(project!==state.projectId)throw new Error('项目已切换');
  const job=await api('ai/assistant/start',{mode:studioAssistant.mode,main:prefs.main,question,resume:studioAssistant.id,contexts:studioAssistant.contexts,pages:studioAssistant.pages,attachments:studioAssistant.attachments.map(a=>a.id),stepLimit:24});
  if(project!==state.projectId||ticket!==studioAssistant.ticket)return;
  studioAssistant.id=job.id;studioAssistant.job=job;if(studioAssistant.stopRequested){await conversationStop(true);return;}$('#conversationInput').value='';conversationRemember();conversationRender();clearInterval(studioAssistant.timer);studioAssistant.timer=setInterval(conversationPoll,1200);await conversationPoll();
 }finally{studioAssistant.sending=false;conversationControls();}
}
async function conversationStop(queued=false){
 if(studioAssistant.stopping&&!queued)return;
 studioAssistant.stopRequested=true;studioAssistant.stopping=true;conversationControls();
 if(!studioAssistant.job?.running)return;
 const id=studioAssistant.id,project=studioAssistant.project,ticket=studioAssistant.ticket;let timer;
 try{
  const job=await Promise.race([api('ai/assistant/cancel',{id}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('停止请求暂未确认，请再次点击停止')),5000);})]);
  if(id!==studioAssistant.id||project!==state.projectId||ticket!==studioAssistant.ticket)return;
  if((job.revision??0)>=(studioAssistant.job?.revision??0))studioAssistant.job=job;
  studioAssistant.stopping=!!job.running;conversationRender();
  if(!studioAssistant.timer)studioAssistant.timer=setInterval(conversationPoll,700);
  await conversationPoll();
 }catch(error){studioAssistant.stopping=false;conversationControls();throw error;}
 finally{clearTimeout(timer);}
}
async function conversationUpload(files){
 const project=state.projectId,ticket=studioAssistant.ticket;
 for(const file of files){
  if(file.size>8*1024*1024)throw new Error('单个附件上限 8 MB');
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
  const result=await api('ai/assistant/attachment',{name:file.name,content:btoa(binary)});
  if(project!==state.projectId||ticket!==studioAssistant.ticket)return;studioAssistant.attachments.push(result);conversationControls();
 }
}
async function conversationHistory(){
 const project=state.projectId,history=await api('ai/assistant/history');if(project!==state.projectId)return;
 modal('最近对话',`<div class="conversation-history">${history.map(j=>`<button type="button" data-conversation-history="${j.id}"><strong>${esc(j.question?.slice(0,100)||'对话')}</strong><span>${j.chatMode==='agent'?'Agent':'Chat'} · ${esc(j.stage)}</span></button>`).join('')||'<p>暂无对话</p>'}</div>`);
 $$('[data-conversation-history]').forEach(b=>b.onclick=conversationWatch(async()=>{if(project!==state.projectId)return;studioAssistant.id=b.dataset.conversationHistory;studioAssistant.job=null;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.ticket++;closeModal();conversationRemember();await conversationPoll();if(studioAssistant.job?.running){clearInterval(studioAssistant.timer);studioAssistant.timer=setInterval(conversationPoll,1200);}}));
}
async function conversationDiff(path){
 const id=studioAssistant.id,project=state.projectId;const diff=await api('ai/assistant/diff?id='+id+'&path='+encodeURIComponent(path));if(id!==studioAssistant.id||project!==state.projectId)return;
 modal(path,`<div class="conversation-diff"><section><h3>修改前</h3><pre>${esc(diff.before)}</pre></section><section><h3>候选修改</h3><pre>${esc(diff.after)}</pre></section></div>`);
}
async function conversationPreview(){
 const id=studioAssistant.id,project=state.projectId;const effects=await api('ai/assistant/effects?id='+id);if(id!==studioAssistant.id||project!==state.projectId)return;
 writingSetView('content');$('#writingContent').hidden=true;const host=$('#conversationPdf');host.hidden=false;
 host.innerHTML=`<div class="conversation-pdf-toolbar"><button type="button" id="conversationReturn">返回文档</button><label>页次 <select id="conversationPdfPage">${Array.from({length:effects.afterPages||1},(_,i)=>`<option>${i+1}</option>`).join('')}</select></label></div><div class="conversation-pdf-pair"><figure><figcaption>修改前</figcaption><img id="conversationPdfBefore" alt="修改前" ${effects.beforePages?'':'hidden'}></figure><figure><figcaption>候选修改</figcaption><img id="conversationPdfAfter" alt="候选修改"></figure></div>`;
 const paint=()=>{const n=Number($('#conversationPdfPage').value);for(const side of ['Before','After']){const image=$('#conversationPdf'+side);image.hidden=side==='Before'&&n>(effects.beforePages||0);image.src='/api/ai/assistant/effect-image?id='+id+'&which='+side.toLowerCase()+'&page='+n+'&project='+encodeURIComponent(project);}};
 $('#conversationReturn').onclick=()=>writingSetView('content');$('#conversationPdfPage').onchange=paint;paint();
}
async function conversationApply(undo=false){
 if([...models.values()].some(i=>i.dirty))throw new Error('请先保存当前文件');
 const id=studioAssistant.id,project=state.projectId;const result=await api('ai/assistant/'+(undo?'undo':'apply'),{id});if(project!==state.projectId||id!==studioAssistant.id)return;
 studioAssistant.job=result.job;for(const path of result.files){const info=models.get(path);if(!info?.model)continue;const data=await api('file?path='+encodeURIComponent(path));if(project!==state.projectId)return;info.model.setValue(data.content);info.revision=data.revision;info.dirty=false;}
 clearTimeout(autoTimer);clearTimeout(saveTimer);renderTabs();renderOutline();conversationRender();writingSetView('content');await poll();await compile();toast(undo?'已撤销修改':'修改已应用');
}
function conversationSetupResize(){
 const handle=$('#conversationComposerResize'),panel=$('#studioConversation');let start=null;
 handle.onpointerdown=e=>{if(e.button!==0)return;start={y:e.clientY,height:$('#conversationComposer').getBoundingClientRect().height};handle.setPointerCapture(e.pointerId);e.preventDefault();};
 handle.onpointermove=e=>{if(!start||!handle.hasPointerCapture(e.pointerId))return;const height=Math.max(120,Math.min(panel.clientHeight*.65,start.height+start.y-e.clientY));panel.style.setProperty('--composer-height',height+'px');};
 handle.onpointerup=e=>{if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);start=null;};handle.onlostpointercapture=()=>{start=null;};
 handle.onkeydown=e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();const height=e.key==='Home'?150:Math.max(120,Math.min(panel.clientHeight*.65,$('#conversationComposer').clientHeight+(e.key==='ArrowUp'?16:-16)));panel.style.setProperty('--composer-height',height+'px');}};
}
function conversationInstall(){
 $('.ai-heading h1').textContent='AI 助手';$('.ai-heading-actions').insertAdjacentHTML('afterbegin','<div class="conversation-surface"><button type="button" data-assistant-surface="conversation" class="active">对话</button><button type="button" data-assistant-surface="review">审阅工具</button></div>');
 $('.writing-review').insertAdjacentHTML('beforeend',`<section id="studioConversation" aria-label="AI 对话"><header class="conversation-header"><div role="group" aria-label="助手模式"><button type="button" data-assistant-mode="chat" class="active" aria-pressed="true">Chat</button><button type="button" data-assistant-mode="agent" aria-pressed="false">Agent</button></div><button type="button" id="conversationHistory" class="text-button">历史</button><button type="button" id="conversationNew" class="text-button" aria-label="新对话" title="新对话">＋</button><button id="conversationFocus" type="button" class="text-button" aria-label="展开对话" title="展开对话">⤢</button><details class="conversation-info"><summary aria-label="对话用量" title="对话信息">•••</summary><div id="conversationUsage"></div></details></header><div id="conversationMessages" class="conversation-messages" aria-live="polite"></div><div class="conversation-result-actions"><button id="conversationPreview" hidden>查看效果</button><button id="conversationApply" class="primary" hidden>确认应用</button><button id="conversationUndo" hidden>撤销应用</button></div><div id="conversationComposerResize" role="separator" tabindex="0" aria-label="调整输入区高度" aria-orientation="horizontal"></div><div id="conversationComposer"><div id="conversationContextList" class="conversation-context-list"></div><textarea id="conversationInput" placeholder="向 Studio 提问，或描述要完成的任务" aria-label="对话内容" maxlength="8000"></textarea><div class="conversation-send-row"><details id="conversationAttachMenu" class="conversation-attach"><summary aria-label="关联内容" title="关联内容与附件">＋</summary><div><button id="conversationContext" type="button">关联所选内容</button><button id="conversationUpload" type="button">上传附件</button></div></details><span id="conversationModeHint"></span><button type="button" id="conversationSend" class="primary" title="发送 · Enter" aria-label="发送">↑</button><button type="button" id="conversationStop" title="停止 · Esc" aria-label="停止生成" hidden>■</button></div></div><p id="conversationError" role="alert" hidden></p><footer class="conversation-status"><span id="conversationStage">就绪</span></footer><input id="conversationFiles" type="file" accept=".tex,.bib,.sty,.cls,.txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp" multiple hidden></section>`);
 $('#writingDiff').insertAdjacentHTML('afterend','<div id="conversationPdf" hidden></div>');
 $$('[data-assistant-surface]').forEach(b=>b.onclick=()=>conversationSurface(b.dataset.assistantSurface));
 $$('[data-assistant-mode]').forEach(b=>b.onclick=()=>{studioAssistant.mode=b.dataset.assistantMode;conversationRemember();conversationControls();});
 $('#conversationFocus').onclick=()=>{const focused=$('#writingWorkbench').classList.toggle('conversation-focus');$('#conversationFocus').setAttribute('aria-label',focused?'返回文档分栏':'展开对话');$('#conversationFocus').title=focused?'返回文档分栏':'展开对话';writingEditor?.layout();writingDiffEditor?.layout();};
 $('#conversationInput').oninput=conversationControls;$('#conversationInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&!studioAssistant.job?.running){e.preventDefault();conversationWatch(conversationSend)();}};
 $('#conversationSend').onclick=conversationWatch(conversationSend);$('#conversationStop').onclick=conversationWatch(()=>conversationStop());
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.dataset.view==='ai'&&(studioAssistant.sending||studioAssistant.job?.running)){e.preventDefault();conversationWatch(()=>conversationStop())();}});
 $('#conversationNew').onclick=()=>{studioAssistant.ticket++;clearInterval(studioAssistant.timer);studioAssistant.id=null;studioAssistant.job=null;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.renderKey=null;conversationRemember();conversationRender();writingSetView('content');};
 $('#conversationContext').onclick=conversationWatch(async()=>{await conversationContext();$('#conversationAttachMenu').open=false;});$('#conversationUpload').onclick=()=>{$('#conversationAttachMenu').open=false;$('#conversationFiles').click();};$('#conversationFiles').onchange=conversationWatch(async e=>{await conversationUpload([...e.target.files]);e.target.value='';});
 $('#conversationContextList').onclick=e=>{if(studioAssistant.job?.running)return;for(const [key,field] of [['contextRemove','contexts'],['pageRemove','pages'],['attachmentRemove','attachments']])if(e.target.dataset[key]!==undefined){studioAssistant[field].splice(Number(e.target.dataset[key]),1);conversationControls();}};
 $('#conversationMessages').onclick=conversationWatch(async e=>{const button=e.target.closest('[data-assistant-diff]');if(button)await conversationDiff(button.dataset.assistantDiff);});
 $('#conversationHistory').onclick=conversationWatch(conversationHistory);$('#conversationPreview').onclick=conversationWatch(conversationPreview);$('#conversationApply').onclick=conversationWatch(()=>conversationApply());$('#conversationUndo').onclick=conversationWatch(()=>conversationApply(true));
 conversationSetupResize();conversationSurface('conversation');conversationRender();if(state?.projectId)conversationProject(state).catch(e=>conversationNotice(e.message));
}
writingSetView=uiPatchRegistry.wrap('writingSetView',writingSetView,'document-assistant.js',previous=>function(view){if($('#conversationPdf'))$('#conversationPdf').hidden=true;return previous(view);});
hubNotifyState=uiPatchRegistry.wrap('hubNotifyState',hubNotifyState,'document-assistant.js',previous=>function(next){previous(next);conversationProject(next).catch(e=>conversationNotice(e.message));});
conversationInstall();
