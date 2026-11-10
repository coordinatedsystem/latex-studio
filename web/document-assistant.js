'use strict';
// Conversation UI owns its state; existing review and document panes stay independent.
const studioAssistant={surface:'conversation',mode:'chat',project:null,id:null,job:null,contexts:[],pages:[],attachments:[],ticket:0,polling:false,timer:null,renderKey:null};
function conversationRemember(){try{if(studioAssistant.project)localStorage.setItem('studio.assistant.'+studioAssistant.project,JSON.stringify({id:studioAssistant.id,mode:studioAssistant.mode}));}catch{}}
function conversationNotice(message=''){const el=$('#conversationError');el.textContent=message;el.hidden=!message;}
function conversationWatch(fn){return async(...args)=>{try{conversationNotice();await fn(...args);}catch(e){conversationNotice(e.message);}};}
function conversationSurface(surface){studioAssistant.surface=surface;$('#writingWorkbench').classList.toggle('conversation-enabled',surface==='conversation');$$('[data-assistant-surface]').forEach(b=>b.classList.toggle('active',b.dataset.assistantSurface===surface));writingSetView('content');conversationControls();}
function conversationControls(){
 const running=!!studioAssistant.job?.running;
 $$('[data-assistant-mode]').forEach(b=>{b.disabled=running;b.classList.toggle('active',b.dataset.assistantMode===studioAssistant.mode);b.setAttribute('aria-pressed',String(b.dataset.assistantMode===studioAssistant.mode));});
 $('#conversationSend').hidden=running;$('#conversationStop').hidden=!running;$('#conversationSend').disabled=studioAssistant.sending||!$('#conversationInput').value.trim();
 $('#conversationHistory').disabled=running;$('#conversationContext').disabled=running;$('#conversationUpload').disabled=running;$('#conversationNew').disabled=running;$('#conversationInput').disabled=running;
 $('#conversationBudget').hidden=studioAssistant.mode!=='agent';$('#conversationModeHint').textContent=studioAssistant.mode==='chat'?'围绕文档讨论':'完成任务并验证结果';
 const job=studioAssistant.job;$('#conversationApply').hidden=job?.chatMode!=='agent'||job?.success!==true||!job?.verified||!job?.changedPaths?.length||job?.applied||running;$('#conversationApply').disabled=!!job?.stale;
 $('#conversationUndo').hidden=!job?.applied;$('#conversationUndo').disabled=!job?.canUndo||running;
 $('#conversationPreview').hidden=!job?.verified||!job?.changedPaths?.length||running;
 $('#conversationUsage').textContent=job?`${(job.tokens||0).toLocaleString()} tokens · ${job.requestCount||0} 次请求`+(job.usage?.cached_tokens?` · 缓存 ${job.usage.cached_tokens.toLocaleString()}`:''):'';
 $('#conversationStage').textContent=studioAssistant.sending?'准备中…':job?.stage||'就绪';
 $('#conversationContextList').innerHTML=[...studioAssistant.contexts.map((c,i)=>`<span>${esc(c.path)} · 选区<button type="button" data-context-remove="${i}" aria-label="移除选区">×</button></span>`),...studioAssistant.pages.map((n,i)=>`<span>第 ${n} 页<button type="button" data-page-remove="${i}" aria-label="移除页面">×</button></span>`),...studioAssistant.attachments.map((a,i)=>`<span>${esc(a.name)}<button type="button" data-attachment-remove="${i}" aria-label="移除附件">×</button></span>`)].join('');
}
function conversationRender(){
 const job=studioAssistant.job,key=job?.id+':'+job?.revision+':'+job?.applied+':'+job?.undone;
 conversationControls();if(key===studioAssistant.renderKey)return;studioAssistant.renderKey=key;
 const list=$('#conversationMessages'),nearBottom=list.scrollHeight-list.scrollTop-list.clientHeight<100,scrollTop=list.scrollTop;
 const expanded=[...list.querySelectorAll('[data-event-index] details[open]')].map(el=>el.closest('[data-event-index]').dataset.eventIndex);
 const messages=job?.messages||[];
 list.innerHTML=messages.length?messages.map(m=>`<article class="conversation-message ${m.role==='user'?'from-user':'from-assistant'}"><header>${m.role==='user'?'你':'Studio'}</header><div>${esc(m.content)}</div></article>`).join(''):'<div class="conversation-empty"><span>✦</span><p>从文档开始对话</p></div>';
 if(job?.events?.length){list.insertAdjacentHTML('beforeend',`<details class="conversation-tools" ${job.running?'open':''}><summary>${job.running?'<span class="spinner"></span> ':''}${esc(job.stage)} · ${job.events.filter(e=>e.status!=='running').length} 个步骤</summary><ol>${job.events.map((e,i)=>`<li data-event-index="${i}" class="${e.status}"><span>${esc(e.label)}</span>${e.detail?`<details><summary>详情</summary><pre>${esc(e.detail)}</pre></details>`:''}</li>`).join('')}</ol></details>`);}
 if(job?.changedPaths?.length)list.insertAdjacentHTML('beforeend',`<div class="conversation-changes">${job.changedPaths.map(path=>`<button type="button" data-assistant-diff="${esc(path)}">${esc(path)} <span>查看修改</span></button>`).join('')}</div>`);
 if(job?.running)list.insertAdjacentHTML('beforeend',`<div class="conversation-working"><span class="spinner"></span>${esc(job.stage)}</div>`);
 for(const index of expanded){const details=list.querySelector('[data-event-index="'+index+'"] details');if(details)details.open=true;}
 list.scrollTop=nearBottom?list.scrollHeight:scrollTop;
}
async function conversationPoll(){
 if(studioAssistant.polling||!studioAssistant.id)return;const project=studioAssistant.project,id=studioAssistant.id,ticket=studioAssistant.ticket;const pollKey=project+':'+id+':'+ticket;studioAssistant.polling=pollKey;
 try{
  const job=await api('ai/assistant/job?id='+encodeURIComponent(id)+'&revision='+(studioAssistant.job?.revision??''));
  if(project!==state?.projectId||ticket!==studioAssistant.ticket||id!==studioAssistant.id)return;
  if(!job.unchanged){studioAssistant.job=job;if(!studioAssistant.attachments.length&&job.attachments?.length)studioAssistant.attachments=job.attachments;if(!studioAssistant.pages.length&&job.pages?.length)studioAssistant.pages=job.pages;conversationRender();}
  if(!job.running){clearInterval(studioAssistant.timer);studioAssistant.timer=null;}
 }catch(e){if(project===state?.projectId&&ticket===studioAssistant.ticket){clearInterval(studioAssistant.timer);conversationNotice(e.message);}}finally{if(studioAssistant.polling===pollKey)studioAssistant.polling=false;}
}
async function conversationProject(next){
 if(studioAssistant.project===next.projectId)return;
 clearInterval(studioAssistant.timer);studioAssistant.polling=false;studioAssistant.sending=false;studioAssistant.ticket++;studioAssistant.project=next.projectId;studioAssistant.id=null;studioAssistant.job=null;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.renderKey=null;
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
 const project=state.projectId,ticket=studioAssistant.ticket;studioAssistant.sending=true;conversationControls();
 try{
  await saveAll();if(project!==state.projectId)throw new Error('项目已切换');
  const job=await api('ai/assistant/start',{mode:studioAssistant.mode,main:prefs.main,question,resume:studioAssistant.id,contexts:studioAssistant.contexts,pages:studioAssistant.pages,attachments:studioAssistant.attachments.map(a=>a.id),stepLimit:Number($('#conversationStepLimit').value)});
  if(project!==state.projectId||ticket!==studioAssistant.ticket)return;
  studioAssistant.id=job.id;studioAssistant.job=job;$('#conversationInput').value='';conversationRemember();conversationRender();clearInterval(studioAssistant.timer);studioAssistant.timer=setInterval(conversationPoll,1200);await conversationPoll();
 }finally{studioAssistant.sending=false;conversationControls();}
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
 handle.onpointermove=e=>{if(!start||!handle.hasPointerCapture(e.pointerId))return;const height=Math.max(140,Math.min(panel.clientHeight*.65,start.height+start.y-e.clientY));panel.style.setProperty('--composer-height',height+'px');};
 handle.onpointerup=e=>{if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);start=null;};handle.onlostpointercapture=()=>{start=null;};
 handle.onkeydown=e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();const height=e.key==='Home'?200:Math.max(140,Math.min(panel.clientHeight*.65,$('#conversationComposer').clientHeight+(e.key==='ArrowUp'?16:-16)));panel.style.setProperty('--composer-height',height+'px');}};
}
function conversationInstall(){
 $('.ai-heading h1').textContent='AI 助手';$('.ai-heading-actions').insertAdjacentHTML('afterbegin','<div class="conversation-surface"><button type="button" data-assistant-surface="conversation" class="active">对话</button><button type="button" data-assistant-surface="review">审阅工具</button></div>');
 $('.writing-review').insertAdjacentHTML('beforeend',`<section id="studioConversation" aria-label="AI 对话"><header class="conversation-header"><div role="group" aria-label="助手模式"><button type="button" data-assistant-mode="chat" class="active" aria-pressed="true">Chat</button><button type="button" data-assistant-mode="agent" aria-pressed="false">Agent</button></div><button type="button" id="conversationHistory" class="text-button">历史</button><button type="button" id="conversationNew" class="text-button">新对话</button></header><div id="conversationMessages" class="conversation-messages" aria-live="polite"></div><div class="conversation-result-actions"><button id="conversationPreview" hidden>查看效果</button><button id="conversationApply" class="primary" hidden>确认应用</button><button id="conversationUndo" hidden>撤销应用</button></div><div id="conversationComposerResize" role="separator" tabindex="0" aria-label="调整输入区高度" aria-orientation="horizontal"></div><div id="conversationComposer"><div class="conversation-context-toolbar"><button id="conversationContext" type="button">＋ 关联所选内容</button><button id="conversationUpload" type="button">附件</button><span id="conversationModeHint"></span></div><div id="conversationContextList" class="conversation-context-list"></div><textarea id="conversationInput" placeholder="描述你的问题或目标…" aria-label="对话内容" maxlength="8000"></textarea><div class="conversation-send-row"><label id="conversationBudget" hidden>步骤 <select id="conversationStepLimit"><option value="12">12</option><option value="24">24</option><option value="6">6</option></select></label><button type="button" id="conversationSend" class="primary">发送 ↑</button><button type="button" id="conversationStop" hidden>停止</button></div></div><p id="conversationError" role="alert" hidden></p><footer class="conversation-status"><span id="conversationStage">就绪</span><span id="conversationUsage"></span></footer><input id="conversationFiles" type="file" accept=".tex,.bib,.sty,.cls,.txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp" multiple hidden></section>`);
 $('#writingDiff').insertAdjacentHTML('afterend','<div id="conversationPdf" hidden></div>');
 $$('[data-assistant-surface]').forEach(b=>b.onclick=()=>conversationSurface(b.dataset.assistantSurface));
 $$('[data-assistant-mode]').forEach(b=>b.onclick=()=>{studioAssistant.mode=b.dataset.assistantMode;conversationRemember();conversationControls();});
 $('#conversationInput').oninput=conversationControls;$('#conversationInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();conversationWatch(conversationSend)();}};
 $('#conversationSend').onclick=conversationWatch(conversationSend);$('#conversationStop').onclick=conversationWatch(async()=>{await api('ai/assistant/cancel',{id:studioAssistant.id});await conversationPoll();});
 $('#conversationNew').onclick=()=>{studioAssistant.ticket++;clearInterval(studioAssistant.timer);studioAssistant.id=null;studioAssistant.job=null;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.renderKey=null;conversationRemember();conversationRender();writingSetView('content');};
 $('#conversationContext').onclick=conversationWatch(conversationContext);$('#conversationUpload').onclick=()=>$('#conversationFiles').click();$('#conversationFiles').onchange=conversationWatch(async e=>{await conversationUpload([...e.target.files]);e.target.value='';});
 $('#conversationContextList').onclick=e=>{if(studioAssistant.job?.running)return;for(const [key,field] of [['contextRemove','contexts'],['pageRemove','pages'],['attachmentRemove','attachments']])if(e.target.dataset[key]!==undefined){studioAssistant[field].splice(Number(e.target.dataset[key]),1);conversationControls();}};
 $('#conversationMessages').onclick=conversationWatch(async e=>{const button=e.target.closest('[data-assistant-diff]');if(button)await conversationDiff(button.dataset.assistantDiff);});
 $('#conversationHistory').onclick=conversationWatch(conversationHistory);$('#conversationPreview').onclick=conversationWatch(conversationPreview);$('#conversationApply').onclick=conversationWatch(()=>conversationApply());$('#conversationUndo').onclick=conversationWatch(()=>conversationApply(true));
 conversationSetupResize();conversationSurface('conversation');conversationRender();if(state?.projectId)conversationProject(state).catch(e=>conversationNotice(e.message));
}
writingSetView=uiPatchRegistry.wrap('writingSetView',writingSetView,'document-assistant.js',previous=>function(view){if($('#conversationPdf'))$('#conversationPdf').hidden=true;return previous(view);});
hubNotifyState=uiPatchRegistry.wrap('hubNotifyState',hubNotifyState,'document-assistant.js',previous=>function(next){previous(next);conversationProject(next).catch(e=>conversationNotice(e.message));});
conversationInstall();
