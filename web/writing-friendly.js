'use strict';
let writingEntry=null,writingOpeningProject=null,writingRestoring=false,writingSaveTimer=null,writingRecoveryKind=null,writingLastFingerprint='';
const writingViewSaves=new Map();let writingDocumentRequest=null;
const writingOriginalLoadDocument=writingLoadDocument;
writingLoadDocument=function(){if(writingDocumentRequest)return writingDocumentRequest;writingDocumentRequest=writingOriginalLoadDocument().finally(()=>{writingDocumentRequest=null;});return writingDocumentRequest;};
const writingReading={surface:'source',projectId:null,page:1};
const writingWait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function writingDirty(){return [...models.values()].some(i=>i.model&&i.dirty);}
function writingRequestSignature(){return JSON.stringify([$('#writingTask').value,$('#writingProvider').value,$('#writingLanguage').value,$('#writingInstruction').value]);}
function writingRequestCount(){return $('#writingProvider').value==='local'?0:writing.mode==='pdf'?writing.pages.size:$('#writingTask').value==='workflow'?2:1;}
function writingPrimaryKind(){
 if(writing.applied)return 'continue';
 if(writing.stale&&writing.result?.edits?.length)return 'rebase';
 if(!writing.stale&&!writing.result?.edits?.length&&writing.context?.mode==='pages'&&((writing.result?.failedPages?.length||0)+(writing.result?.pendingPages?.length||0)))return 'retry';
 if(!writing.result||!writing.result.edits?.length||writing.requestSignature&&writing.requestSignature!==writingRequestSignature())return 'generate';
 return writingSamePreview()?'apply':'preview';
}
function writingUXControls(){
 const locked=writing.busy||!!state?.running||!!state?.packageBusy,kind=writingPrimaryKind();
 const hasScope=writing.mode==='pdf'?writing.pages.size>0:!!writing.range&&writing.range.end>writing.range.start;
 const count=kind==='generate'?writingRequestCount():kind==='retry'?new Set([...(writing.result?.failedPages||[]),...(writing.result?.pendingPages||[])]).size:0;
 const needs=writingDirty()||writing.needsPreparation||!writing.doc?.totalPages;
 const label={generate:needs?'保存并获取建议':'获取建议',retry:'重试未完成页',preview:'预览所选修改',apply:'确认应用',rebase:'重新关联并预览',continue:'继续修改'}[kind];
 $('#writingPrimaryAction').textContent=writing.preparing?writing.prepareStage||'准备中…':writing.job?.running?'获取建议中…':writing.preview?.running?'编译预览中…':label;
 $('#writingPrimaryAction').disabled=locked||(kind==='generate'&&!hasScope)||(['preview','rebase','apply'].includes(kind)&&!writing.selected.size);
 $('#writingCost').textContent=writing.mode==='pdf'?writing.pages.size+' 页':'源码选区';
 let hint='';if(!hasScope&&kind==='generate')hint=writing.mode==='pdf'?'请至少选择一页':'请先选择源码范围';else if(['preview','rebase','apply'].includes(kind)&&!writing.selected.size)hint='请至少勾选一条建议';else if(writing.stale)hint='原建议已保留，重新关联后才能应用';else if(kind==='preview')hint='先查看真实 PDF 效果';else if(kind==='apply')hint='预览已通过，确认后写回源码';else if(kind==='continue')hint='已应用 '+(writing.appliedCount||writing.selected.size)+' 处修改';
 $('#writingActionHint').textContent=hint;$('#writingActionHint').hidden=!hint||writing.busy;
 $('#writingCancelTask').hidden=!(writing.preparing||writing.job?.running);$('#writingCancelTask').disabled=!!writing.stopRequested;
 $('#writingRegenerate').hidden=!writing.result||writing.applied||writing.busy||kind==='generate';
 $('#writingUndo').disabled=locked||writing.canUndo===false;$('#writingUndo').title=writing.canUndo===false?'源码后来已修改，可从文件历史恢复':'';
 const pending=[...new Set([...(writing.result?.failedPages||[]),...(writing.result?.pendingPages||[])])];
 $('#writingRetryPages').hidden=writing.busy||!pending.length||writing.context?.mode!=='pages'||writing.result?.rebased||writing.applied;
 $('#writingRetryPages').textContent='重试 '+pending.length+' 页';
 $$('[data-writing-retry-page]').forEach(b=>b.disabled=locked||writing.stale||writing.applied);
 const progress=writing.job?.progress;$('#writingProgress').hidden=!writing.job?.running||!progress;
 if(progress){$('#writingProgressBar').max=progress.total||1;$('#writingProgressBar').value=progress.processed||0;$('#writingProgressText').textContent='已处理 '+progress.processed+'/'+progress.total+' 页'+(progress.currentPage?' · 当前第 '+progress.currentPage+' 页':'')+(progress.failed?' · '+progress.failed+' 页待重试':'');}
 $('#writingSelectCurrentPage').disabled=locked||writing.pages.has(writing.page);$('#writingSelectCurrentPage').textContent=writing.pages.has(writing.page)?'此页已选':'选此页';
 if(writing.view==='comparison'&&writing.preview?.success){$('#writingContentState').textContent=writing.stale?'历史预览 · 请重新关联':'当前候选预览';if(writing.stale&&!$('#writingCompareMeta').textContent.startsWith('历史预览'))$('#writingCompareMeta').textContent='历史预览 · '+$('#writingCompareMeta').textContent;}
}
function writingSettings(){return {task:$('#writingTask').value,provider:$('#writingProvider').value,language:$('#writingLanguage').value,instruction:$('#writingInstruction').value};}
function writingWorkspaceSave(){
 if(writingRestoring||!writing.project||writingOpeningProject!==writing.project)return;
 try{localStorage.setItem('studio.writing.'+writing.project,JSON.stringify({task:writing.context?.id||null,mode:writing.mode,page:writing.page,pages:[...writing.pages],selectionMode:writing.selectionMode,file:writing.file,range:writing.range,view:writing.view,settings:writingSettings()}));}catch{}
}
function writingRemember(){
 writingWorkspaceSave();if(!writing.context||writing.context.projectId!==state?.projectId)return;
 const id=writing.context.id,project=state.projectId,view={view:writing.view,comparePage:writing.comparePage,settings:writingSettings()};
 if(writing.result)view.selected=[...writing.selected];
 clearTimeout(writingViewSaves.get(id));writingSaveTimer=setTimeout(()=>{writingViewSaves.delete(id);if(project===state?.projectId)api('ai/task-view',{id,view}).catch(()=>{});},180);writingViewSaves.set(id,writingSaveTimer);
}
function writingEditIdentity(edit){return edit.key||JSON.stringify([edit.path||writing.context?.path,edit.fileStart??edit.start,edit.before,edit.after]);}
function writingAcceptResult(result){
 const fingerprint=JSON.stringify([writing.context?.id,result.edits,result.issues,result.pageStates,result.failedPages,result.pendingPages]);if(fingerprint===writingLastFingerprint)return;
 const old=writing.result?.edits||[],known=new Set(old.map(writingEditIdentity)),chosen=new Set(old.filter((_,i)=>writing.selected.has(i)).map(writingEditIdentity));
 writing.selected=new Set((result.edits||[]).map((e,i)=>[e,i]).filter(([e])=>!known.has(writingEditIdentity(e))||chosen.has(writingEditIdentity(e))).map(([,i])=>i));
 writing.result=result;writingLastFingerprint=fingerprint;writing.preview=null;writingDisposeDiff();writingStep(1);if(writing.view==='comparison')writingSetView('content');writingRenderResult();if(writing.view==='diff')writingShowDiff();writingRemember();
}
function writingPageStates(result){
 return result.pageStates?.length?'<div class="writing-page-states">'+result.pageStates.map(p=>`<span class="${esc(p.status)}">第 ${p.page} 页 ${p.status==='completed'?'✓':p.status==='running'?'…':p.status==='failed'?'×':'待处理'}${p.status==='failed'?`<button data-writing-retry-page="${p.page}" title="仅重试此页，新增 1 次请求">重试</button>`:''}</span>`).join('')+'</div>':'';
}
async function writingAwaitCompile(project){
 const start=Date.now();
 while(true){
  if(writing.stopRequested)throw new Error('已停止准备，尚未调用 AI');
  reviewGuard(project);const next=await api('state');reviewGuard(project);
  state=next;
  if(!next.running){if(!next.success)throw new Error('文档编译失败。\n'+(next.lines||[]).slice(-22).join('\n'));return;}
  if(Date.now()-start>180000)throw new Error('编译等待较久，请在编辑器检查进度；未发送 AI 请求');
  await writingWait(450);
 }
}
async function writingRefreshSource(oldFull,range){
 if(writing.mode!=='source')return;
 const before=oldFull.slice(range.start,range.end),whole=range.start===0&&range.end===oldFull.length;
 await writingReadSource(false,true);
 if(!whole){const start=writing.full.indexOf(before);if(start<0||writing.full.indexOf(before,start+1)>=0)throw new Error('所选文字已变化或无法唯一定位，请重新选择源码范围');writing.range={start,end:start+before.length};}
 writingHighlightSource();
}
async function writingPrepareBeforeAI(localOnly=false){
 const project=state.projectId,full=writing.full,range=writing.range?{...writing.range}:null;
 if(!localOnly&&typeof aiConfig!=='undefined'&&$('#writingProvider').value!=='local'&&!aiConfig?.[$('#writingProvider').value]?.configured)throw new Error('请先配置所选 AI 服务的密钥');
 writing.preparing=true;writing.stopRequested=false;writing.preparationOwnCompile=false;writing.prepareStage='保存中…';writingControls();
 try{
  await saveAll();reviewGuard(project);if(writing.stopRequested)throw new Error('已停止准备，尚未调用 AI');
  if(state.running){writing.prepareStage='等待编译…';writingControls();await writingAwaitCompile(project);}
  const ready=await api('ai/readiness');reviewGuard(project);
  if(ready.needsCompile){writing.prepareStage='编译中…';writingStatus('正在准备文档，完成后继续。');writingControls();writing.preparationOwnCompile=true;await compile();await writingAwaitCompile(project);}
  if(writingDirty())throw new Error('源码在准备期间又发生变化，请停止输入后再试；尚未调用 AI');
  writing.prepareStage='关联内容…';writingControls();await writingLoadDocument();
  if(range)await writingRefreshSource(full,range);
  if(writing.mode==='pdf'&&[...writing.pages].some(p=>p>(writing.doc?.totalPages||0)))throw new Error('所选页次已超出当前 PDF，请调整处理范围');
  writing.needsPreparation=false;writing.requestSignature=writingRequestSignature();
 }finally{writing.preparing=false;writing.preparationOwnCompile=false;writingControls();}
}
function writingCaptureEntry(action){
 if(document.body.dataset.view!=='editor'){writingEntry=null;return;}
 const selection=editor?.getSelection();
 if(action==='aiSelection'||writingReading.surface==='source'&&selection&&!selection.isEmpty())writingEntry={kind:'source',projectId:state.projectId};
 else if(writingReading.surface==='pdf'&&writingReading.projectId===state.projectId)writingEntry={kind:'pdf',projectId:state.projectId,page:writingReading.page};
 else writingEntry=null;
}
function writingTrackPdf(app,ticket,project){
 const frame=$('#pdfFrame'),position=()=>{if(ticket===pdfTicket&&project===state?.projectId){writingReading.projectId=project;writingReading.page=app.page||1;}};
 app.eventBus.on('pagechanging',position);position();
 try{for(const event of ['pointerdown','wheel','keydown'])frame.contentDocument.addEventListener(event,()=>{if(ticket===pdfTicket){position();writingReading.surface='pdf';}},{passive:true});}catch{}
}
let writingEditorTracked=false;
async function writingOpened(useSelection){
 if(!writingEditorTracked&&editor){writingEditorTracked=true;editor.onDidFocusEditorWidget?.(()=>{writingReading.surface='source';});}
 const entry=writingEntry;writingEntry=null;
 if(entry?.projectId===state.projectId&&!writing.job?.running){
  writingOpeningProject=state.projectId;
  if(entry.kind==='pdf'){if(writing.mode!=='pdf'||!writing.pages.has(entry.page)){writingReset();await writingSetMode('pdf');writing.pages=new Set([Math.max(1,Math.min(entry.page,writing.doc?.totalPages||1))]);writing.selectionMode='single';$('#writingSelectionMode').value='single';$('#writingPageSelectionToolbar').hidden=true;}writingShowPage(entry.page);writingRenderThumbnails();}
  else if(!useSelection){await writingSetMode('source');await writingReadSource(true);}
  writingWorkspaceSave();return;
 }
 if(writingOpeningProject===state.projectId)return;writingOpeningProject=state.projectId;
 let saved;try{saved=JSON.parse(localStorage.getItem('studio.writing.'+state.projectId)||'null');}catch{}
 if(saved?.task){try{await writingRestoreTask(saved.task,true);return;}catch{}}
 if(saved){
  writingRestoring=true;
  try{writing.mode=saved.mode==='source'?'source':'pdf';writing.selectionMode=saved.selectionMode==='multiple'?'multiple':'single';$('#writingSelectionMode').value=writing.selectionMode;writing.pages=new Set((saved.pages||[1]).filter(p=>Number.isInteger(p)&&p>0&&p<=Math.max(1,writing.doc?.totalPages||1)));writing.page=saved.page||1;if(saved.file)writing.file=saved.file;writingPopulateFiles();await writingSetMode(writing.mode);if(writing.mode==='pdf')writingShowPage(writing.page);if(saved.settings)writingSetSettings(saved.settings);}
  finally{writingRestoring=false;}
 }
}
function writingSetSettings(settings){
 if([...$('#writingTask').options].some(o=>o.value===settings.task))$('#writingTask').value=settings.task;
 if(['local','deepseek','youdao'].includes(settings.provider))$('#writingProvider').value=settings.provider;
 if(['en','zh-CHS','ja','de','fr'].includes(settings.language))$('#writingLanguage').value=settings.language;
 $('#writingInstruction').value=String(settings.instruction||'').slice(0,1600);writingTaskControls();
}
async function writingRestoreTask(ident,automatic=false,provided=null){
 if(writing.busy&&!provided)return;
 const project=state.projectId,c=provided||await api('ai/task?id='+encodeURIComponent(ident));reviewGuard(project);
 if(automatic&&c.undone)throw new Error('此任务已撤销');
 writingRemember();writingRestoring=true;
 try{
  writingReset();writing.project=c.projectId;writing.mode=c.mode==='source'?'source':'pdf';writing.pages=new Set(c.pages||[c.page]);writing.page=c.page;writing.selectionMode=writing.pages.size>1?'multiple':'single';$('#writingSelectionMode').value=writing.selectionMode;
  if(writing.mode==='source'){writing.file=c.path;writingPopulateFiles();await writingReadSource(false,true);writing.range={start:Math.min(writing.full.length,Array.from(writing.full).slice(0,c.start).join('').length),end:Math.min(writing.full.length,Array.from(writing.full).slice(0,c.end).join('').length)};writingHighlightSource();}
  writing.context=c;writing.result=c.result;writing.job={...c.job,result:c.result};writing.preview=c.preview?.id?c.preview:null;writing.applied=c.applied;writing.canUndo=c.canUndo;writing.appliedCount=c.preview?.selected?.length||c.result?.edits?.length||0;writing.stopRequested=false;
  writing.stale=!!c.stale||writingDirty()||!!c.undone;writing.busy=!!c.job?.running;writing.selected=new Set(c.view?.selected||c.preview?.selected||c.result?.edits?.map((_,i)=>i)||[]);
  writingLastFingerprint=JSON.stringify([c.id,c.result?.edits,c.result?.issues,c.result?.pageStates,c.result?.failedPages,c.result?.pendingPages]);
  $('#writingPdfToolbar').hidden=writing.mode!=='pdf';$('#writingSourceToolbar').hidden=writing.mode!=='source';$('#writingPdfScroll').hidden=writing.mode!=='pdf';$('#writingSourceEditor').hidden=writing.mode!=='source';$('#writingPageSelectionToolbar').hidden=writing.mode!=='pdf'||writing.selectionMode!=='multiple';$('#writingThumbnails').hidden=writing.mode!=='pdf'||$('#writingThumbnailsToggle').getAttribute('aria-expanded')!=='true';
  writingShowPage(c.page);writingRenderThumbnails();if(c.view?.settings)writingSetSettings(c.view.settings);writing.requestSignature=writingRequestSignature();
  if(c.result)writingRenderResult();
  if(writing.preview?.success){writingRenderComparison(c.view?.comparePage);writingStep(writing.applied?3:2);writingSetView(c.view?.view==='diff'?'diff':'comparison');}
  else{writingStep(c.result?1:0);if(writing.stale&&c.result?.edits?.length)writingSetView('diff');}
  writingStatus(writing.busy?'已恢复任务，继续查看进度。':writing.stale?'历史建议已保留，请重新关联后预览。':writing.applied?'已应用 '+writing.appliedCount+' 处修改。':'任务已恢复');
  if(writing.busy){clearInterval(writingTimer);writingTimer=setInterval(writingPoll,700);}
  $('#writingHistoryPanel').hidden=true;$('#writingHistoryToggle').setAttribute('aria-expanded','false');
 }finally{writingRestoring=false;writingControls();writingWorkspaceSave();}
}
async function writingHistoryOpen(){
 const project=state.projectId,tasks=await api('ai/tasks');reviewGuard(project);
 $('#writingHistoryList').innerHTML=tasks.length?tasks.map(t=>`<button data-writing-task="${t.id}" ${writing.busy&&t.id!==writing.context?.id?'disabled':''}><strong>${t.mode==='source'?esc(t.path)+' · 第 '+t.startLine+'–'+t.endLine+' 行':'第 '+t.pages.join('、')+' 页'}</strong><span>${t.count} 条建议 · ${t.running?'处理中':t.undone?'已撤销':t.applied?'已应用':t.failedPages.length?'有页面待重试':'待审阅'}</span><time>${new Date((t.updated||t.created||0)*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time></button>`).join(''):'<p>暂无任务</p>';
 $('#writingHistoryPanel').hidden=false;$('#writingHistoryToggle').setAttribute('aria-expanded','true');
}
async function writingRetry(pages=null){
 if(writing.busy)return;writingGuard();writingClean();
 pages=pages||[...new Set([...(writing.result?.failedPages||[]),...(writing.result?.pendingPages||[])])];if(!pages.length)return;
 writingRemember();writing.busy=true;writing.stopRequested=false;writing.preview=null;writingError();writingSetView('content');writingControls();
 try{writing.job=await api('ai/start',{task:'pages_edit',provider:'deepseek',pageContext:writing.context.id,retryPages:pages,instruction:writing.context.request?.instruction||$('#writingInstruction').value});writingWorkspaceSave();clearInterval(writingTimer);writingTimer=setInterval(writingPoll,700);await writingPoll();}
 catch(e){writing.busy=false;throw e;}finally{writingControls();}
}
async function writingRebase(){
 if(writing.busy)return;const id=writing.context?.id,selected=[...writing.selected];if(!id)return;
 writingRemember();writing.busy=true;writingControls();
 try{await writingPrepareBeforeAI(true);const context=await api('ai/task-rebase',{id,selected});writing.busy=false;await writingRestoreTask(context.id,false,context);if(writing.selected.size)await writingPreview();}
 finally{writing.busy=false;writingControls();}
}
async function writingPrimary(){
 if(writing.busy)return;writingError();const kind=writingPrimaryKind();
 if(kind==='generate')return writingStart();if(kind==='retry')return writingRetry();if(kind==='preview')return writingPreview();if(kind==='apply')return writingApply();if(kind==='rebase')return writingRebase();
 writingReset();await writingLoadDocument();if(writing.mode==='source')await writingReadSource();
}

// One concise message with a local recovery action; technical logs stay folded.
const writingRawError=writingError;
writingError=function(message=''){
 if(!$('#writingErrorText'))return writingRawError(message);
 $('#writingError').hidden=!message;writingRecoveryKind=null;$('#writingRecovery').hidden=true;$('#writingErrorDetails').hidden=true;if(!message)return;
 let summary=String(message).split('\n')[0],label='';writing.lastError=String(message);
 const missing=String(message).match(/(?:File|file|find|open|load)[^\n]{0,100}?[`'"“]?([\w-]+\.(?:sty|cls))[`'"”]?[^\n]{0,80}(?:not found|missing|找不到|不存在)/i)||String(message).match(/([\w-]+\.(?:sty|cls))[^\n]{0,60}(?:not found|missing)/i);
 if(missing){writing.missingPackage=missing[1];summary='编译缺少宏包 '+missing[1];label='安装并重新编译';writingRecoveryKind='package';}
 else if(/密钥|认证|鉴权|余额|API Key|401|403/i.test(message)){summary='AI 服务配置或账户状态需要检查';label='服务配置';writingRecoveryKind='settings';}
 else if(/已变化|更新|未保存|请先保存|源码映射|重新关联|唯一匹配/.test(message)){if(writing.applied){label='查看文件历史';writingRecoveryKind='history';}else if(writing.context&&writing.result?.edits?.length){summary='原建议已保留，请保存并重新关联';label='保存并重新关联';writingRecoveryKind='rebase';writing.stale=true;}else{label='保存并编译';writingRecoveryKind='prepare';}}
 else if(/页次|页码|选择一页/.test(message)){label='调整页次';writingRecoveryKind='scope';}
 else if(/任务.*失效|暂无.*任务/.test(message)){label='最近任务';writingRecoveryKind='tasks';}
 else if(/编译|控制序列|Undefined control/.test(message)){summary='编译未通过，原文件保留';label='定位源码';writingRecoveryKind='source';}
 else if(/源码范围|字符|无法可靠定位/.test(message)){label='选择源码范围';writingRecoveryKind='source';}
 else if(/宏包.*管理/.test(message)){label='宏包管理';writingRecoveryKind='manager';}
 $('#writingErrorText').textContent=summary.slice(0,180);$('#writingRecovery').textContent=label;$('#writingRecovery').hidden=!label;
 $('#writingErrorDetails').hidden=String(message).length<=180&&!String(message).includes('\n');$('#writingErrorLog').textContent=String(message).slice(-6500);
};
async function writingRecovery(){
 if(writingRecoveryKind==='settings')return aiSettings();if(writingRecoveryKind==='rebase')return writingRebase();if(writingRecoveryKind==='tasks')return writingHistoryOpen();
 if(writingRecoveryKind==='scope'){$('#writingPageRange').focus();return;}
 if(writingRecoveryKind==='package')return writingInstallMissing();
 if(writingRecoveryKind==='manager'){hubView('packages');return;}
 if(writingRecoveryKind==='prepare'){writing.busy=true;try{await writingPrepareBeforeAI(true);writingError();writingStatus('文档已准备好，可继续获取建议。');}finally{writing.busy=false;writingControls();}return;}
 const match=writing.lastError?.match(/([^\s:'"<>]+\.tex):(\d+):/),reported=match?.[1].replaceAll('\\','/');
 const found=reported&&state.files.find(f=>f.path===reported||reported.endsWith('/'+f.path)||f.path===reported.split('/').pop());
 const path=found?.path||writing.context?.path||writing.file||state.main;await openFile(path,found?Number(match[2]):writing.context?.startLine||1);hubView('editor');
 if(writingRecoveryKind==='history')await run('history');
}
async function writingInstallMissing(){
 const name=writing.missingPackage;if(!name)return;writing.busy=true;writingControls();
 try{writingStatus('正在安装 '+name+'…');const catalog=await api('packages?query='+encodeURIComponent(name)+'&filter=all&page=0');const item=catalog.items?.find(p=>p.name===name);if(!item)throw new Error('该宏包未收录，请到宏包管理中检查');
  await api('packages/action',{action:'install',names:[name]});const start=Date.now();while(true){const job=await api('packages/job');writingStatus(job.stage||'正在安装宏包…');if(!job.running){if(!job.success)throw new Error('宏包安装未完成，请到宏包管理中查看日志');break;}if(Date.now()-start>180000)throw new Error('下载仍在进行，可在宏包管理中查看');await writingWait(600);}
  await writingPrepareBeforeAI(true);writingError();writingStatus('宏包已安装，文档已重新编译。');
 }finally{writing.busy=false;writingControls();}
}
$('#writingPrimaryAction').onclick=writingWatch(writingPrimary);
$('#writingHistoryToggle').onclick=writingWatch(writingHistoryOpen);$('#writingHistoryClose').onclick=()=>{$('#writingHistoryPanel').hidden=true;$('#writingHistoryToggle').setAttribute('aria-expanded','false');};
$('#writingHistoryList').onclick=writingWatch(async e=>{const button=e.target.closest('[data-writing-task]');if(button)await writingRestoreTask(button.dataset.writingTask);});
$('#writingRetryPages').onclick=writingWatch(()=>writingRetry());
$('#writingResults').addEventListener('click',writingWatch(async e=>{const button=e.target.closest('[data-writing-retry-page]');if(button)await writingRetry([Number(button.dataset.writingRetryPage)]);}));
$('#writingRegenerate').onclick=writingWatch(async()=>{writingRemember();writing.result=null;writing.preview=null;writing.requestSignature=null;$('.writing-request').classList.remove('compact');$('#writingInstruction').focus();writingStep(0);writingControls();});
$('#writingCancelTask').onclick=writingWatch(async()=>{writing.stopRequested=true;if(writing.preparing){if(writing.preparationOwnCompile&&state.running)await api('cancel',{});writingStatus('正在停止准备…');}else if(writing.job?.running)await api('ai/cancel',{id:writing.job.id});writingControls();});
$('#writingRecovery').onclick=writingWatch(writingRecovery);
$('#writingSelectCurrentPage').onclick=()=>{if(writing.busy)return;writingReset();writing.pages=writing.selectionMode==='single'?new Set([writing.page]):new Set([...writing.pages,writing.page]);writingShowPage(writing.page);};
$('#writingInstruction').addEventListener('input',writingControls);for(const id of ['writingTask','writingProvider','writingLanguage'])$('#'+id).addEventListener('change',writingControls);
window.addEventListener('beforeunload',writingRemember);document.addEventListener('studio-source-change',()=>{writing.needsPreparation=true;writingControls();});
writingUXControls();
