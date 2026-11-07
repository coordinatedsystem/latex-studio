'use strict';
let pageEditContext=null,pageEditJob=null,pageEditResult=null,pageEditSelected=new Set(),pageEditPreviewState=null,pageEditTimer=null,pageEditPolling=false,pageEditApplied=false;
function pageEditCleanBuffers(){if([...models.values()].some(i=>i.model&&i.dirty))throw new Error('编辑器有未保存修改。请先保存并编译，再关联本页源码。');}
function pageEditGuard(){if(!pageEditContext||pageEditContext.projectId!==state?.projectId)throw new Error('请先关联当前项目的单页源码');}
function pageEditControls(){
 const busy=!!pageEditJob?.running||!!pageEditPreviewState?.running;
 $('#pageEditPrepare').disabled=busy;$('#pageEditMap').disabled=busy;$('#pageEditPage').disabled=busy;$('#pageEditFile').disabled=busy;
 $('#pageEditGenerate').disabled=busy||!pageEditContext||pageEditContext.projectId!==state?.projectId||pageEditApplied;
 $('#pageEditStop').hidden=!pageEditJob?.running;$('#pageEditNotes').disabled=busy;
 const ready=pageEditContext?.projectId===state?.projectId;
 $('#pageEditPreview').disabled=busy||!ready||!pageEditSelected.size||pageEditApplied;
 const same=pageEditPreviewState?.success&&JSON.stringify(pageEditPreviewState.selected)===JSON.stringify([...pageEditSelected].sort((a,b)=>a-b));
 $('#pageEditApply').disabled=busy||!ready||!same||pageEditApplied;$('#pageEditUndo').hidden=!pageEditApplied;$('#pageEditUndo').disabled=busy;
 $('#pageEditSelectionInfo').textContent=pageEditSelected.size+' 项已选择';
}
async function pageEditPrepare(path=null){
 pageEditCleanBuffers();const project=state?.projectId;$('#pageEditStatus').textContent='正在定位本页源码…';
 const context=await api('ai/page-prepare',{page:Number($('#pageEditPage').value),...(path?{path}: {})});reviewGuard(project);
 pageEditContext=context;pageEditResult=null;pageEditJob=null;pageEditPreviewState=null;pageEditSelected.clear();pageEditApplied=false;
 $('#pageEditSource').value=context.source;$('#pageEditFile').innerHTML=context.candidates.map(f=>`<option value="${esc(f)}">${esc(f)}</option>`).join('');$('#pageEditFile').value=context.path;$('#pageEditFileLabel').hidden=context.candidates.length<2;
 $('#pageEditContextInfo').textContent=context.path+' · 第 '+context.startLine+'–'+context.endLine+' 行 · 仅第 '+context.page+' 页';
 $('#pageEditResult').hidden=true;$('#pageEditComparison').hidden=true;$('#pageEditStatus').textContent='本页源码已关联。点击生成时仅发送这一个页面及上方源码片段。';pageEditControls();
}
async function pageEditGenerate(){
 pageEditGuard();pageEditCleanBuffers();if(pageEditJob?.running)return;
 $('#pageEditStatus').textContent='正在发送当前单页与关联源码…';$('#pageEditGenerate').disabled=true;
 try{const job=await api('ai/start',{task:'page_edit',provider:'deepseek',pageContext:pageEditContext.id,instruction:$('#pageEditNotes').value});
  pageEditJob=job;pageEditResult=null;pageEditPreviewState=null;$('#pageEditComparison').hidden=true;$('#pageEditResult').hidden=true;
  clearInterval(pageEditTimer);pageEditTimer=setInterval(pageEditPoll,700);await pageEditPoll();
 }finally{pageEditControls();}
}
async function pageEditPoll(){
 if(pageEditPolling)return;pageEditPolling=true;
 try{pageEditGuard();
  if(pageEditJob?.running){const job=await api('ai/job?id='+encodeURIComponent(pageEditJob.id));if(!job.id)throw new Error('AI 任务已失效，请重新关联源码');pageEditJob=job;$('#pageEditStatus').textContent=job.stage;
   if(!job.running){clearInterval(pageEditTimer);if(!job.success)throw new Error(job.error||'没有生成修改');
    pageEditResult=job.result;pageEditSelected=new Set(pageEditResult.edits.map((_,i)=>i));pageEditRender();}
  }else if(pageEditPreviewState?.running){const result=await api('ai/page-preview?id='+encodeURIComponent(pageEditContext.id));pageEditPreviewState=result;$('#pageEditStatus').textContent=result.stage;
   if(!result.running){clearInterval(pageEditTimer);if(!result.success)throw new Error(result.error||'比较预览编译失败');
    const base='/api/ai/page-image?id='+encodeURIComponent(pageEditContext.id)+'&project='+encodeURIComponent(pageEditContext.projectId)+'&v='+result.id;
    $('#pageEditBefore').src=base+'&which=before';$('#pageEditAfter').src=base+'&which=after';$('#pageEditComparison').hidden=false;
    $('#pageEditPreviewMeta').textContent='编译通过 · 第 '+pageEditContext.page+' 页 · '+(result.changed?'已检测到可见变化':'未检测到可见像素变化')+' · 修改后共 '+result.totalPages+' 页';
    $('#pageEditStatus').textContent='候选副本已编译，可查看前后效果；原文件尚未修改。';}
  }
 }catch(e){reviewError(e.message);if(pageEditJob&&!pageEditJob.running||pageEditPreviewState&&!pageEditPreviewState.running||pageEditContext?.projectId!==state?.projectId){clearInterval(pageEditTimer);}else $('#pageEditStatus').textContent='状态读取中断，正在重试；AI 不会自动重发。';}
 finally{pageEditPolling=false;pageEditControls();}
}
function pageEditRender(){
 $('#pageEditResult').hidden=false;$('#pageEditSummary').textContent=pageEditResult.summary;
 const rejected=pageEditResult.rejected||[];$('#pageEditRejected').hidden=!rejected.length;$('#pageEditRejected').textContent='已拦截 '+rejected.length+' 项无法安全定位的修改：'+rejected.map(r=>r.reason).join('；');
 if(!pageEditResult.edits.length){$('#pageEditEdits').textContent=pageEditResult.manualReason||'本次模型只返回建议，没有可定位的源码修改。没有自动再次调用 API。';$('#pageEditStatus').textContent='没有可应用修改；可补充具体要求后手动再次生成。';}
 else{$('#pageEditStatus').textContent='已生成 '+pageEditResult.edits.length+' 项源码修改。先生成效果预览，再应用。';$('#pageEditEdits').innerHTML=pageEditResult.edits.map((e,i)=>`<article class="ai-edit"><label class="ai-edit-title"><input type="checkbox" data-page-edit="${i}" ${pageEditSelected.has(i)?'checked':''}><strong>${esc(e.reason)}</strong><span>修改 ${i+1}</span></label><div class="ai-edit-code"><div class="before"><small>原文</small><pre>${esc(e.before)}</pre></div><div class="after"><small>建议</small><pre>${esc(e.after)}</pre></div></div></article>`).join('');}
 pageEditControls();
}
async function pageEditPreview(){
 pageEditGuard();pageEditCleanBuffers();if(!pageEditSelected.size)throw new Error('请至少选择一项修改');
 pageEditPreviewState=await api('ai/page-preview',{id:pageEditContext.id,selected:[...pageEditSelected]});$('#pageEditComparison').hidden=true;
 clearInterval(pageEditTimer);pageEditTimer=setInterval(pageEditPoll,700);pageEditControls();await pageEditPoll();
}
async function pageEditApply(undo=false){
 pageEditGuard();pageEditCleanBuffers();
 const data=await api(undo?'ai/page-undo':'ai/page-apply',{id:pageEditContext.id,previewId:pageEditPreviewState?.id,selected:[...pageEditSelected]});
 pageEditApplied=!undo;await openFile(data.path);await reloadCurrent();
 if(undo){pageEditContext=null;pageEditPreviewState=null;$('#pageEditResult').hidden=true;$('#pageEditComparison').hidden=true;$('#pageEditContextInfo').textContent='已撤销本次应用，编译后请重新关联本页源码';}
 pageEditControls();
 $('#pageEditStatus').textContent=undo?'本次修改已撤销，正在更新 PDF。':'修改已应用，正在更新 PDF。';
 await run('compile');toast(undo?'已撤销本次应用并编译':'已应用通过预览的修改并编译');
}
function pageEditSourceDiff(){
 if(!pageEditContext||!pageEditResult?.edits.length)return;let target=pageEditContext.source;const points=Array.from(target);
 for(const edit of pageEditResult.edits.filter((_,i)=>pageEditSelected.has(i)).sort((a,b)=>b.start-a.start)){
  const start=points.slice(0,edit.start).join('').length,end=points.slice(0,edit.end).join('').length;target=target.slice(0,start)+edit.after+target.slice(end);}
 aiDisposeDiff();modal('本页源码差异 · '+pageEditContext.path,'<div class="ai-diff-legend"><span>原文</span><span>所选修改</span></div><div id="aiDiffEditor" class="ai-diff-editor"></div>');$('#modal').classList.add('ai-diff-modal');
 aiDiffModels=[monacoApi.editor.createModel(pageEditContext.source,'latex'),monacoApi.editor.createModel(target,'latex')];aiDiffEditor=monacoApi.editor.createDiffEditor($('#aiDiffEditor'),{fontFamily:'"Studio Digits", "Studio Source Han", Consolas, monospace',readOnly:true,automaticLayout:true,renderSideBySide:innerWidth>800,ignoreTrimWhitespace:false,minimap:{enabled:false},theme:'vs',fontSize:13});aiDiffEditor.setModel({original:aiDiffModels[0],modified:aiDiffModels[1]});
}
function pageEditLinks(result){return [...new Set(result.issues.map(i=>i.page))].map(p=>`<button class="secondary" data-page-modify="${p}">将第 ${p} 页建议转为源码修改 ↗</button>`).join('');}
async function pageEditResume(){
 const job=await api('ai/job');if(job.task!=='page_edit'||!job.result?.pageContext||job.running)throw new Error('没有可恢复的已完成单页任务');
 const c=await api('ai/page-context?id='+encodeURIComponent(job.result.pageContext));reviewGuard(c.projectId);
 if(c.undone){pageEditContext=null;pageEditPreviewState=null;pageEditApplied=false;$('#pageEditResult').hidden=true;$('#pageEditComparison').hidden=true;pageEditControls();throw new Error('最近任务已撤销，请编译后重新关联本页源码');}
 pageEditContext=c;pageEditJob=job;pageEditResult=c.result||job.result;pageEditApplied=c.applied;
 pageEditPreviewState=c.preview?.id?{...c.preview,running:false}:null;pageEditSelected=new Set(c.preview?.selected||pageEditResult.edits.map((_,i)=>i));
 $('#pageEditPage').value=c.page;$('#pageEditSource').value=c.source;$('#pageEditFile').innerHTML=c.candidates.map(f=>`<option value="${esc(f)}">${esc(f)}</option>`).join('');$('#pageEditFile').value=c.path;$('#pageEditFileLabel').hidden=c.candidates.length<2;
 $('#pageEditContextInfo').textContent=c.path+' · 第 '+c.startLine+'–'+c.endLine+' 行 · 仅第 '+c.page+' 页';pageEditRender();
 if(c.preview?.success){const base='/api/ai/page-image?id='+encodeURIComponent(c.id)+'&project='+c.projectId+'&v='+c.preview.id;$('#pageEditBefore').src=base+'&which=before';$('#pageEditAfter').src=base+'&which=after';$('#pageEditComparison').hidden=false;$('#pageEditPreviewMeta').textContent='已恢复编译通过的前后对比 · 第 '+c.page+' 页';}
 pageEditControls();
}
async function pageEditOpen(page,notes=''){
 reviewShow('pageedit');$('#pageEditPage').value=page;if(notes)$('#pageEditNotes').value=notes;await pageEditPrepare();
}
$('#pageEditPrepare').onclick=reviewWatch(()=>pageEditPrepare());$('#pageEditFile').onchange=reviewWatch(()=>pageEditPrepare($('#pageEditFile').value));
$('#pageEditPage').oninput=()=>{pageEditContext=null;pageEditResult=null;pageEditPreviewState=null;$('#pageEditResult').hidden=true;$('#pageEditComparison').hidden=true;$('#pageEditContextInfo').textContent='页码已变化，请重新关联源码';pageEditControls();};
$('#pageEditMap').onclick=reviewWatch(async()=>{await run('compile');toast('编译完成后返回“单页修改”，再关联页面源码');});
$('#pageEditGenerate').onclick=reviewWatch(pageEditGenerate);$('#pageEditPreview').onclick=reviewWatch(pageEditPreview);$('#pageEditApply').onclick=reviewWatch(()=>pageEditApply(false));$('#pageEditUndo').onclick=reviewWatch(()=>pageEditApply(true));
$('#pageEditStop').onclick=reviewWatch(async()=>{if(pageEditJob?.id)await api('ai/cancel',{id:pageEditJob.id});});
$('#pageEditEdits').onchange=e=>{const input=e.target.closest('[data-page-edit]');if(input){const i=Number(input.dataset.pageEdit);input.checked?pageEditSelected.add(i):pageEditSelected.delete(i);if(pageEditPreviewState?.success)$('#pageEditPreviewMeta').textContent='修改选择已变化，当前图片为上次预览；请重新生成效果对比';pageEditControls();}};
$('#pageEditAll').onchange=e=>{pageEditSelected=new Set(e.target.checked?pageEditResult.edits.map((_,i)=>i):[]);pageEditRender();};
$('#pageEditSourceDiff').onclick=pageEditSourceDiff;pageEditControls();
$('#pageEditResume').onclick=reviewWatch(pageEditResume);
