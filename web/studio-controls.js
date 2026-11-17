'use strict';
// Progressive disclosure: context controls live in a menu; permissions appear only when requested.
const agentContextKeys={history:'历史对话',selection:'所选内容',diagnostics:'上次编译日志',references:'引用检查',glossary:'术语表',attachments:'关联附件',layout:'PDF 与版面检查'};
function agentContextPolicy(){
 const settings={};for(const key of Object.keys(agentContextKeys))settings[key]=$('#agentContext_'+key)?.checked!==false;return settings;
}
function agentContextLoad(){
 let saved={};try{saved=JSON.parse(localStorage.getItem('studio.context.'+state?.projectId)||'{}');}catch{}
 for(const key of Object.keys(agentContextKeys)){const input=$('#agentContext_'+key);if(input)input.checked=saved[key]!==false;}
}
function agentPermissionCard(list,job){
 const p=job?.pendingPermission;if(!p)return;
 list.insertAdjacentHTML('beforeend',`<section class="agent-permission" role="group" aria-label="操作授权"><div class="agent-permission-title">${p.capability==='browser'?'允许访问网页？':'允许修改配套文件？'}</div><code>${esc(p.target)}</code><p>${p.capability==='browser'?'仅执行列出的网页操作。不会读取浏览器登录信息。':'在候选副本中修改，编译验证后仍需确认应用。'}</p><div><button type="button" data-permission="deny">拒绝</button><button type="button" data-permission="once">仅这次</button><button type="button" class="primary" data-permission="session">本轮允许</button></div></section>`);
 list.querySelectorAll('[data-permission]').forEach(button=>button.onclick=conversationWatch(async()=>{
  list.querySelectorAll('[data-permission]').forEach(b=>b.disabled=true);
  try{const result=await api('ai/assistant/permission',{id:job.id,requestId:p.id,decision:button.dataset.permission});if(studioAssistant.id===job.id){studioAssistant.job=result;conversationRender();}}
  finally{list.querySelectorAll('[data-permission]').forEach(b=>b.disabled=false);}
 }));
}
const projectSyncState={project:null,busy:false,last:0,status:null};
async function projectSyncNow(required=false){
 if(projectSyncState.busy){if(required)throw new Error('正在同步原文件夹，请稍后再发送');return;}
 const project=state?.projectId;if(!project)return;
 projectSyncState.busy=true;
 try{
  const result=await api('projects/sync',{});if(project!==state?.projectId)return;
  projectSyncState.project=project;projectSyncState.status=result;projectSyncState.last=Date.now();
  const button=$('#projectSourceLink');if(button){button.classList.toggle('has-conflicts',!!result.conflicts?.length);button.textContent=result.conflicts?.length?'同步冲突 · '+result.conflicts.length:result.linked?'已关联原文件夹':'关联原文件夹';}
  if(result.updated?.length)await checkExternalChanges();
  if(required&&(result.error||result.conflicts?.length))throw new Error(result.error||'原文件夹与项目都有修改，请先处理同步冲突');
  return result;
 }catch(error){if(required)throw error;}
 finally{projectSyncState.busy=false;}
}
function projectSyncDialog(){
 const result=projectSyncState.project===state?.projectId?projectSyncState.status:null;
 modal('原文件夹同步',`<p>关联后，每隔数秒同步单边改动。两边都改过的文件由你选择；覆盖前保存备份，不会自动删除文件。</p><label class="field"><span>原始项目文件夹的完整路径</span><input id="projectSourcePath" value="${esc(result?.source||'')}" placeholder="D:\\文档\\论文"></label><div class="dialog-actions"><button type="button" id="projectSourceDisconnect">取消关联</button><button type="button" class="primary" id="projectSourceConnect">关联并检查</button></div><div id="projectSyncConflicts"></div>`);
 function showConflicts(status){
  const region=$('#projectSyncConflicts');if(!region)return;
  region.innerHTML=status?.error?`<p>${esc(status.error)}</p>`:(status?.conflicts||[]).map((c,i)=>`<div class="sync-conflict"><code>${esc(c.path)}</code><div><button type="button" data-sync-choice="source" data-sync-index="${i}" ${c.sourceHash?'':'disabled'}>使用原文件夹版</button><button type="button" data-sync-choice="local" data-sync-index="${i}" ${c.localHash?'':'disabled'}>使用当前项目版</button></div></div>`).join('')||'<p>没有冲突</p>';
  region.querySelectorAll('[data-sync-choice]').forEach(b=>b.onclick=conversationWatch(async()=>{
   const conflict=status.conflicts[Number(b.dataset.syncIndex)];const project=state.projectId;
   const next=await api('projects/sync',{resolution:{...conflict,choice:b.dataset.syncChoice}});
   if(project!==state.projectId)return;projectSyncState.status=next;showConflicts(next);await checkExternalChanges();
  }));
 }
 showConflicts(result);
 $('#projectSourceConnect').onclick=conversationWatch(async()=>{await saveAll();const project=state.projectId;const status=await api('projects/sync/connect',{path:$('#projectSourcePath').value.trim()});if(project!==state.projectId)return;projectSyncState.status=status;projectSyncState.project=project;showConflicts(status);await checkExternalChanges();});
 $('#projectSourceDisconnect').onclick=conversationWatch(async()=>{projectSyncState.status=await api('projects/sync/disconnect',{});closeModal();await projectSyncNow();});
}
function studioControlsInstall(){
 const header=$('.conversation-header');if(!header)return;
 header.insertAdjacentHTML('beforeend',`<details class="agent-options"><summary title="上下文与工具" aria-label="上下文与工具">${icon('settings')}</summary><div class="agent-options-popover"><strong>本轮上下文</strong>${Object.entries(agentContextKeys).map(([key,label])=>`<label><input type="checkbox" id="agentContext_${key}" checked><span>${label}</span></label>`).join('')}<p>关闭后不发送对应历史资料，并禁用相应工具。编译验证始终保留。</p><div class="agent-policy-note">配套文件与网页操作 · 按需授权</div></div></details>`);
 header.querySelectorAll('.agent-options input').forEach(input=>input.onchange=()=>{try{localStorage.setItem('studio.context.'+state?.projectId,JSON.stringify(agentContextPolicy()));}catch{}});
 $('.agent-options-popover').insertAdjacentHTML('beforeend','<button type="button" id="agentSourceSync" class="text-button">原文件夹同步 ↗</button>');
 $('#agentSourceSync').onclick=()=>{$('.agent-options').open=false;projectSyncNow().then(projectSyncDialog);};
 $('.main-toolbar')?.insertAdjacentHTML('beforeend','<button type="button" id="projectSourceLink" class="text-button" title="同步导入副本与原文件夹">关联原文件夹</button>');
 if($('#projectSourceLink'))$('#projectSourceLink').onclick=()=>projectSyncNow().then(projectSyncDialog);
 agentContextLoad();
}
hubNotifyState=uiPatchRegistry.wrap('hubNotifyState',hubNotifyState,'studio-controls.js',previous=>function(next){
 previous(next);if(projectSyncState.project!==next.projectId){projectSyncState.project=next.projectId;projectSyncState.status=null;projectSyncState.last=0;agentContextLoad();}
 if(!next.running&&!next.aiBusy&&!next.packageBusy&&!next.pagePreviewBusy&&Date.now()-projectSyncState.last>5000)projectSyncNow();
});
studioControlsInstall();
