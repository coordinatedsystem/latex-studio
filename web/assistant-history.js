'use strict';
let conversationDeleted=null;try{conversationDeleted=JSON.parse(localStorage.getItem('66Catzzz.deleted')||'null');}catch{}
async function conversationHistoryPanel(){
 const requestedProject=state.projectId,projects=await api('ai/assistant/history-tree');if(requestedProject!==state.projectId)return;
 modal('66Catzzz · 会话',`<div class="cat-history"><input id="catHistorySearch" aria-label="搜索历史会话" placeholder="搜索会话或轮次"><div id="catHistoryUndo" ${conversationDeleted?'':'hidden'}><span>会话已删除，原文未改动</span><button type="button" id="catRestore">撤销删除</button></div>${projects.map(p=>`<details class="cat-project" ${p.id===state.projectId?'open':''}><summary><span>⌑</span> ${esc(p.name)} <small>${p.conversations.length} 个会话</small></summary>${p.conversations.map(c=>`<section class="cat-thread" data-history-search="${esc((c.title+' '+c.turns.map(t=>t.question).join(' ')).toLowerCase())}"><div class="cat-thread-heading"><button type="button" data-cat-open="${c.latestId}" data-cat-project="${p.id}">${esc(c.title)}</button><button type="button" class="cat-delete" data-cat-delete="${c.id}" data-cat-project="${p.id}" title="删除会话，可撤销" aria-label="删除会话 ${esc(c.title)}">×</button></div><details class="cat-turns"><summary>${c.turns.length} 轮对话 · ${esc(new Date(c.updated*1000).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}))}</summary>${c.turns.map((t,i)=>`<button type="button" data-cat-open="${t.id}" data-cat-project="${p.id}"><small>${i+1} · ${t.chatMode==='agent'?'Agent':'Chat'}</small><span>${esc(t.question)}</span></button>`).join('')}</details></section>`).join('')||'<p class="cat-history-empty">暂无会话</p>'}</details>`).join('')}</div>`);
 $('#catHistorySearch').oninput=e=>{$$('[data-history-search]').forEach(n=>n.hidden=!n.dataset.historySearch.includes(e.target.value.trim().toLowerCase()));};
 $$('[data-cat-open]').forEach(button=>button.onclick=conversationWatch(async()=>{
  const project=projects.find(p=>p.id===button.dataset.catProject);if(!project)return;
  if(state.projectId!==project.id){await hubSwitch('projects/open',{path:project.root});hubView('ai');}
  const id=button.dataset.catOpen,pid=state.projectId,job=await api('ai/assistant/job?id='+id+'&full=1');if(pid!==state.projectId)return;
  studioAssistant.ticket++;studioAssistant.id=id;studioAssistant.job=job;studioAssistant.contexts=[];studioAssistant.pages=[];studioAssistant.attachments=[];studioAssistant.mode=job.chatMode||'chat';studioAssistant.renderKey=null;
  closeModal();conversationRemember();conversationSurface('conversation');conversationRender();if(job.running){clearInterval(studioAssistant.timer);studioAssistant.timer=setInterval(conversationPoll,1200);}
 }));
 $$('[data-cat-delete]').forEach(button=>button.onclick=conversationWatch(async()=>{
  const pid=button.dataset.catProject,result=await api('ai/assistant/delete-conversation',{conversationId:button.dataset.catDelete,projectId:pid});conversationDeleted={token:result.restoreToken,projectId:pid};try{localStorage.setItem('66Catzzz.deleted',JSON.stringify(conversationDeleted));}catch{}
  if(result.ids.includes(studioAssistant.id)){$('#conversationNew').click();}
  await conversationHistoryPanel();
 }));
 if(conversationDeleted)$('#catRestore').onclick=conversationWatch(async()=>{await api('ai/assistant/restore-conversation',conversationDeleted);conversationDeleted=null;try{localStorage.removeItem('66Catzzz.deleted');}catch{}await conversationHistoryPanel();});
}
