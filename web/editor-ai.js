'use strict';
let editorAiJob=null,editorAiTarget=null,editorAiProject=null,editorAiPending=false,editorAiLastPoll=0,editorAiDiffEditor=null,editorAiDiffModels=[],editorAiDiffKey='',editorAiDiffView=false,editorAiPreview=null,editorAiSequence=0;
let editorAiEffectView=false,editorAiEffectMeta=null,editorAiEffectTicket=0;
let editorAiRecoveredJob=null;
const editorAiWatch=fn=>async(...args)=>{try{return await fn(...args)}catch(e){toast(e.message,true);$('#editorAiStage').textContent=e.message;}};
function editorAiSelection(model,range){
 if(!model||!range||range.isEmpty())return null;
 const text=model.getValue(),offset=p=>Array.from(text.slice(0,model.getOffsetAt(p)).replace(/\r\n/g,'\n')).length;return [offset(range.getStartPosition()),offset(range.getEndPosition())];
}
function editorAiCapture(){
 const model=models.get(active)?.model,range=editor?.getSelection();
 editorAiTarget={path:model?active:prefs.main,line:model?(range?.startLineNumber||1):1,selection:editorAiSelection(model,range),version:model?.getVersionId()};
 $('#editorAiContext').textContent=editorAiTarget.path+(editorAiTarget.selection?' · 行 '+range.startLineNumber+'–'+range.endLineNumber:' · 当前行 '+editorAiTarget.line);
 $('#editorAiContext').title=$('#editorAiContext').textContent;
}
function editorAiDock(tab){
 const ai=tab==='ai',issues=tab==='issues';$('#logPanel').hidden=false;$('#workspace').classList.add('with-log');$('#workspace').classList.toggle('editor-ai-open',ai);
 $('#editorAiPanel').hidden=!ai;$('#logOutput').hidden=ai||issues;$('#diagnosticList').hidden=ai||!issues;diagnosticsOnly=issues;
 $('#compileMeta').hidden=ai;$('#editorAiRepair').hidden=ai||state?.success!==false||!!state?.running;
 $('#editorAiTab').classList.toggle('active',ai);$('#diagnosticTab').classList.toggle('active',issues);$('#editorLogTab').classList.toggle('active',!ai&&!issues);$('#editorAiStatus').setAttribute('aria-expanded',String(ai));
 requestAnimationFrame(()=>{editor?.layout();editorAiDiffEditor?.layout();});
}
function editorAiExpand(){const on=$('#workspace').classList.toggle('editor-ai-expanded');$('#editorAiExpand').setAttribute('aria-expanded',String(on));$('#editorAiExpand').setAttribute('aria-label',on?'还原面板':'展开面板');requestAnimationFrame(()=>{editor?.layout();editorAiDiffEditor?.layout();});}
function editorAiMinimize(){
 $('#logPanel').hidden=true;$('#workspace').classList.remove('with-log','editor-ai-open');$('#editorAiStatus').setAttribute('aria-expanded','false');editor?.layout();
}
function editorAiOpen(mode){
 hubView('editor');editorAiCapture();if(mode)$('#editorAiMode').value=mode;editorAiMode();editorAiDock('ai');editorAiRefresh(true).catch(e=>toast(e.message,true));$('#editorAiPrompt').focus();
}
function editorAiMode(){const mode=$('#editorAiMode').value;$('#editorAiLimitLabel').hidden=mode!=='repair';$('#editorAiStart').textContent=({repair:'修复并验证',edit:'生成并验证',explain:'解释代码'})[mode];$('#editorAiPrompt').placeholder=mode==='edit'?'输入修改要求，例如调整段落间距':'补充说明（可选）';}
function editorAiDirty(){return [...models.values()].some(m=>m.dirty||m.saving);}
function editorAiDiscardDiff(){editorAiDiffEditor?.setModel(null);editorAiDiffModels.forEach(m=>m.dispose());editorAiDiffModels=[];editorAiDiffKey='';}
async function editorAiShowDiff(){
 const j=editorAiJob,path=$('#editorAiFiles').value;if(!j?.id||!path||!monacoApi)return;
 const project=state?.projectId,key=j.id+':'+path+':'+j.rounds.length+':'+j.running;
 if(editorAiDiffKey===key){editorAiDiffEditor?.layout();return;}
 const data=await api('editor-ai/diff?id='+j.id+'&path='+encodeURIComponent(path));if(editorAiJob?.id!==j.id||state?.projectId!==project||$('#editorAiFiles').value!==path)return;
 if(!editorAiDiffEditor){editorAiDiffEditor=monacoApi.editor.createDiffEditor($('#editorAiDiff'),{readOnly:true,originalEditable:false,automaticLayout:true,minimap:{enabled:false},fontFamily:'"Studio Digits", "Studio Source Han", Consolas, monospace',fontSize:14,ignoreTrimWhitespace:false,renderSideBySide:$('#editorAiDiff').clientWidth>650,scrollBeyondLastLine:false,wordWrap:'on'});editorAiDiffEditor.onDidUpdateDiff(()=>{const change=editorAiDiffEditor.getLineChanges()?.[0];if(change){editorAiDiffEditor.getModifiedEditor().revealLineInCenter(change.modifiedStartLineNumber||1);editorAiDiffEditor.getOriginalEditor().revealLineInCenter(change.originalStartLineNumber||1);}});}
 editorAiDiscardDiff();editorAiDiffModels=[monacoApi.editor.createModel(data.before,language(path)),monacoApi.editor.createModel(data.after,language(path))];editorAiDiffEditor.setModel({original:editorAiDiffModels[0],modified:editorAiDiffModels[1]});editorAiDiffKey=key;
}
function editorAiView(diff){editorAiEffectView=false;$('#editorAiEffect').hidden=true;$('#editorAiEffectTab').classList.remove('active');editorAiDiffView=diff;$('#editorAiResponse').hidden=diff;$('#editorAiDiff').hidden=!diff;$('#editorAiSummaryTab').classList.toggle('active',!diff);$('#editorAiDiffTab').classList.toggle('active',diff);if(diff)editorAiShowDiff().catch(e=>toast(e.message,true));}
function editorAiEffectImages(){
 const j=editorAiJob,meta=editorAiEffectMeta;if(!j||meta?.id!==j.id)return;const page=Number($('#editorAiEffectPage').value)||1,query='id='+j.id+'&project='+encodeURIComponent(state.projectId)+'&page='+page;
 $('#editorAiBefore').hidden=page>meta.beforePages;$('#editorAiBeforeEmpty').hidden=page<=meta.beforePages;
 if(page<=meta.beforePages)$('#editorAiBefore').src='/api/editor-ai/effect-image?'+query+'&which=before';
 $('#editorAiAfter').src='/api/editor-ai/effect-image?'+query+'&which=after';$('#editorAiEffectState').textContent='正在绘制…';
}
async function editorAiShowEffects(){
 const j=editorAiJob;if(!j?.verified||!j.changedPaths?.length||j.running)return;
 const ticket=++editorAiEffectTicket,project=state.projectId;editorAiView(false);editorAiEffectView=true;$('#editorAiResponse').hidden=true;$('#editorAiEffect').hidden=false;$('#editorAiSummaryTab').classList.remove('active');$('#editorAiEffectTab').classList.add('active');$('#editorAiEffectState').textContent='正在读取…';
 try{const meta=await api('editor-ai/effects?id='+j.id);if(ticket!==editorAiEffectTicket||state.projectId!==project||editorAiJob?.id!==j.id)return;editorAiEffectMeta=meta;$('#editorAiBeforeLabel').textContent=meta.beforeLabel;$('#editorAiAfterLabel').textContent=j.applied?'修改后 · 已应用':meta.afterLabel;$('#editorAiEffectPage').innerHTML=Array.from({length:meta.afterPages},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('');editorAiEffectImages();}catch(e){$('#editorAiEffectState').textContent=e.message;throw e;}
}
function editorAiRender(){
 const j=editorAiJob,busy=!!j?.running,changed=!!j?.changedPaths?.length,dirty=editorAiDirty();
 $('#editorAiAfterLabel').textContent=j?.applied?'修改后 · 已应用':'候选修改 · 未应用';
 if(j?.mode==='repair'&&j.line&&$('#editorAiMode').value==='repair')$('#editorAiContext').textContent=j.path+' · 报错行 '+j.line;
 $('#editorAiStart').hidden=busy;$('#editorAiStop').hidden=!busy;$('#editorAiStart').disabled=busy||!!state?.running||!!state?.aiBusy;
 $('#editorAiMode').disabled=busy;$('#editorAiCapture').disabled=busy;$('#editorAiDiffTab').disabled=!changed;
 const explain=j?.mode==='explain'||$('#editorAiMode').value==='explain',ready=!!j?.verified&&changed&&!busy;
 $('#editorAiPreview').hidden=explain;$('#editorAiPreview').disabled=!ready;$('#editorAiEffectTab').disabled=!ready;
 $('#editorAiApply').hidden=explain||!!j?.applied||!!j?.undone;$('#editorAiApply').disabled=!ready||!!j?.stale||dirty;
 $('#editorAiApply').title=ready?(j?.stale?'源码已变化，请重新分析':dirty?'请先保存代码':'应用已通过编译的修改'):busy?'等待候选修改通过编译':'尚未生成可应用的修改';$('#editorAiPreview').title=ready?'并排预览修改前后效果':'生成修改并通过编译后可预览';
 if(j?.compilerLocation)$('#editorAiContext').title='编译器报告 '+j.compilerLocation.path+':'+j.compilerLocation.line+'；源码位置 '+j.path+':'+j.line;
 $('#editorAiUndo').hidden=!j?.applied;$('#editorAiUndo').disabled=!j?.canUndo||dirty||busy;
 $('#editorAiContinue').hidden=!j?.canContinue;$('#editorAiContinue').disabled=dirty||!!state?.running||busy;
 $('#editorAiPackages').hidden=!j?.manual;$('#editorAiStage').textContent=j?(dirty&&changed?'有未保存改动 · 请先保存':j.stale?'源码已变化 · 请重新分析':j.undone?'已撤销':j.applied?'已应用':j.stage||j.error||'准备就绪'):'准备就绪';
 $('#editorAiBadge').hidden=!j;$('#editorAiBadge').textContent=busy?'进行中':j?.undone?'已撤销':j?.applied?'已应用':j?.verified&&changed?'待确认':j?.error?'未完成':'完成';
 const paths=j?.changedPaths||[],current=$('#editorAiFiles').value;$('#editorAiFiles').hidden=paths.length<2;
 if(JSON.stringify(paths)!==$('#editorAiFiles').dataset.paths){$('#editorAiFiles').innerHTML=paths.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');if(paths.includes(current))$('#editorAiFiles').value=current;$('#editorAiFiles').dataset.paths=JSON.stringify(paths);}
 if(j){
  $('#editorAiResponse').innerHTML=`${j.summary?'<h3>'+esc(j.summary)+'</h3>':''}${j.answer?'<p>'+esc(j.answer)+'</p>':''}${j.running?'<p><span class="spinner"></span> '+esc(j.stage)+'</p>':''}${j.error?'<div class="editor-ai-error">'+esc(j.error)+'</div>':''}${j.stale?'<p class="editor-ai-error">原文件已变化，当前建议仅供审阅，请重新分析。</p>':''}<div class="editor-ai-rounds">${(j.rounds||[]).map(r=>`<details class="editor-ai-round ${r.status}"><summary>第 ${r.number} 轮 · ${esc(r.path)} · ${r.status==='passed'?'编译通过':r.status==='failed'?'仍有报错':'验证中'}</summary><pre>${esc(r.log||r.summary)}</pre></details>`).join('')}</div>`;
 }else $('#editorAiResponse').innerHTML='<div class="editor-ai-empty"><strong>✦ 在代码旁完成修改</strong><span>选择代码，或从编译报错开始。</span></div>';
 if((!changed||!ready)&&editorAiEffectView)editorAiView(false);if(!changed&&editorAiDiffView)editorAiView(false);else if(changed&&editorAiDiffView)editorAiShowDiff().catch(()=>{});
}
async function editorAiRefresh(force=false){
 if(!state?.projectId||editorAiPending)return;const now=Date.now();if(!force&&(!editorAiJob?.running||now-editorAiLastPoll<850))return;
 editorAiPending=true;editorAiLastPoll=now;const project=state.projectId,seq=editorAiSequence;
 try{const j=await api('editor-ai/job'+(editorAiJob?.id?'?id='+editorAiJob.id:''));if(state?.projectId!==project||seq!==editorAiSequence)return;editorAiJob=j.id?j:null;editorAiRender();if(j.resourceRecovered&&j.success&&!j.running&&!j.changedPaths?.length&&editorAiRecoveredJob!==j.id){editorAiRecoveredJob=j.id;await compile();}}finally{editorAiPending=false;}
}
async function editorAiStart(resume=false){
 if(!state?.projectId||editorAiJob?.running)return;
 const project=state.projectId;await saveAll();if(state?.projectId!==project)throw new Error('项目已切换，请重新选择代码');
 const target=resume===true?{path:editorAiJob.path,line:editorAiJob.line||1,selection:null}:editorAiTarget||{path:active||prefs.main,line:1,selection:null},mode=resume===true?'repair':$('#editorAiMode').value;
 if(mode!=='repair'&&target.version&&models.get(target.path)?.model?.getVersionId()!==target.version)throw new Error('目标代码已变化，请点击“选取代码”重新选择');
 const job=await api('editor-ai/start',{main:prefs.main,mode,path:target.path,selection:mode==='repair'?null:target.selection,line:target.line,question:$('#editorAiPrompt').value,limit:Number($('#editorAiLimit').value),resume:resume===true?editorAiJob?.id:undefined});
 if(resume===true){$('#editorAiMode').value='repair';editorAiMode();}
 if(state?.projectId!==project)return;editorAiSequence++;editorAiEffectTicket++;editorAiEffectMeta=null;editorAiClearPdf();editorAiJob=job;editorAiDiscardDiff();editorAiView(false);editorAiRender();
}
function editorAiClearPdf(){editorAiPreview=null;$('#editorAiReturnPdf').hidden=true;}
function editorAiHoldPdf(next){
 if(editorAiPreview&&(editorAiPreview.project!==next.projectId||editorAiPreview.version!==next.pdfVersion)){editorAiClearPdf();return false;}
 return !!editorAiPreview;
}
async function editorAiShowPdf(){
 const j=editorAiJob;if(!j?.verified||j.running)return;
 editorAiPreview={project:state.projectId,version:state.pdfVersion,id:j.id};$('#editorAiReturnPdf').hidden=false;
 await setPdf('editor-ai-'+j.id,true,false,null,'/api/editor-ai/preview.pdf?id='+j.id);$('#noPdf').hidden=true;
}
async function editorAiRestorePdf(){editorAiClearPdf();if(state?.hasPdf)await setPdf(state.pdfVersion,true);else{$('#pdfFrame').src='about:blank';$('#noPdf').hidden=false;$('#previewMessage').hidden=true;previewStatus('idle','等待编译');}}
function editorAiDownloadCandidate(){if(!editorAiPreview)return false;const a=document.createElement('a');a.href='/api/editor-ai/preview.pdf?id='+editorAiPreview.id+'&project='+encodeURIComponent(editorAiPreview.project);a.download=prefs.main.replace(/.*\//,'').replace(/\.tex$/,'-候选.pdf');a.click();return true;}
async function editorAiApply(undo=false){
 const j=editorAiJob;if(!j||editorAiDirty())throw new Error('请先保存代码，再应用或撤销');const project=state.projectId;
 if(!undo&&(!j.verified||!j.changedPaths?.length||j.stale||j.running))throw new Error('请先生成并验证修改，再确认应用');
 const result=await api('editor-ai/'+(undo?'undo':'apply'),{id:j.id});if(project!==state?.projectId)return;editorAiJob=result.job;editorAiClearPdf();
 for(const path of result.files){const info=models.get(path);if(!info?.model)continue;const data=await api('file?path='+encodeURIComponent(path));info.model.setValue(data.content);info.revision=data.revision;info.dirty=false;}
 renderTabs();renderOutline();setSaveStatus(undo?'已撤销 AI 修改':'AI 修改已应用');editorAiRender();await poll();await compile();
}
$('#diagnosticTab').removeAttribute('data-action');$('#editorDockClose').removeAttribute('data-action');$('#editorDockClose').setAttribute('aria-label','收起面板');
$('#editorLogTab').onclick=()=>editorAiDock('log');$('#diagnosticTab').onclick=()=>editorAiDock('issues');$('#editorAiTab').onclick=()=>editorAiOpen();$('#editorDockClose').onclick=editorAiMinimize;
$('#editorAiStatus').onclick=()=>$('#workspace').classList.contains('editor-ai-open')&&!$('#logPanel').hidden?editorAiMinimize():editorAiOpen();$('#editorAiRepair').onclick=()=>editorAiOpen('repair');
$('#editorAiCapture').onclick=editorAiCapture;$('#editorAiContext').onclick=editorAiWatch(()=>$('#editorAiMode').value==='repair'&&editorAiJob?.line?openFile(editorAiJob.path,editorAiJob.line):openFile(editorAiTarget?.path||prefs.main,editorAiTarget?.line||1));$('#editorAiMode').onchange=editorAiMode;
$('#editorAiStart').onclick=editorAiWatch(()=>editorAiStart());$('#editorAiContinue').onclick=editorAiWatch(()=>editorAiStart(true));$('#editorAiStop').onclick=editorAiWatch(async()=>{if(editorAiJob?.id){editorAiJob=await api('editor-ai/cancel',{id:editorAiJob.id});editorAiRender();}});
$('#editorAiConfig').onclick=editorAiWatch(()=>aiSettings());$('#editorAiFull').onclick=()=>run('ai');$('#editorAiPackages').onclick=()=>run('packages');
$('#editorAiSummaryTab').onclick=()=>editorAiView(false);$('#editorAiDiffTab').onclick=()=>editorAiView(true);$('#editorAiFiles').onchange=()=>editorAiShowDiff().catch(e=>toast(e.message,true));
$('#editorAiApply').onclick=editorAiWatch(()=>editorAiApply());$('#editorAiUndo').onclick=editorAiWatch(()=>editorAiApply(true));$('#editorAiPreview').onclick=editorAiWatch(editorAiShowEffects);$('#editorAiEffectTab').onclick=editorAiWatch(editorAiShowEffects);$('#editorAiOpenPdf').onclick=editorAiWatch(editorAiShowPdf);$('#editorAiReturnPdf').onclick=editorAiWatch(editorAiRestorePdf);$('#editorAiEffectPage').onchange=editorAiEffectImages;$('#editorAiExpand').onclick=editorAiExpand;
$('#editorAiAfter').onload=()=>{$('#editorAiEffectState').textContent='编译通过';};for(const id of ['editorAiBefore','editorAiAfter'])$('#'+id).onerror=()=>{$('#editorAiEffectState').textContent='页面绘制失败，可在右侧打开 PDF';};
toggleLogs=uiPatchRegistry.wrap('toggleLogs',toggleLogs,'editor-ai.js',previous=>function(force){if(force===true||($('#workspace').classList.contains('editor-ai-open')&&force===undefined)){editorAiDock('log');return;}previous(force);});
let editorAiActionsInstalled=false;
hubNotifyState=uiPatchRegistry.wrap('hubNotifyState',hubNotifyState,'editor-ai.js',previous=>function(next){
 previous(next);$('#editorAiRepair').hidden=next.success!==false||next.running||(!$('#editorAiPanel').hidden&&!$('#logPanel').hidden);
 if(editorAiProject!==next.projectId){editorAiProject=next.projectId;editorAiSequence++;editorAiEffectTicket++;editorAiEffectMeta=null;editorAiJob=null;editorAiTarget=null;editorAiView(false);editorAiDiscardDiff();editorAiClearPdf();editorAiRefresh(true).catch(()=>{});}
 else editorAiRefresh().catch(()=>{});editorAiRender();
 if(editor&&!editorAiActionsInstalled){editorAiActionsInstalled=true;editor.addAction({id:'studio.editorAi',label:'编辑器 AI：解释或修改选区',keybindings:[monacoApi.KeyMod.CtrlCmd|monacoApi.KeyMod.Alt|monacoApi.KeyCode.KeyA],contextMenuGroupId:'9_ai',contextMenuOrder:1,run:()=>editorAiOpen('edit')});editor.addAction({id:'studio.repairAi',label:'AI 修复编译报错',contextMenuGroupId:'9_ai',contextMenuOrder:2,run:()=>editorAiOpen('repair')});}
});
document.addEventListener('studio-source-change',()=>{if(editorAiJob)editorAiRender();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#modal').open&&!$('#editorAiPanel').hidden&&!$('#logPanel').hidden){editorAiMinimize();e.preventDefault();}});
commands.push(['编辑器 AI','editorAi','Ctrl+Alt+A']);editorAiMode();
