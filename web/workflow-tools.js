'use strict';
let workflowHistoryEditor=null,workflowHistoryModels=[],workflowHistoryTicket=0;
function workflowDisposeHistory(){workflowHistoryTicket++;workflowHistoryEditor?.dispose();workflowHistoryEditor=null;workflowHistoryModels.forEach(m=>m.dispose());workflowHistoryModels=[];}
$('#modal').addEventListener('close',workflowDisposeHistory);
showHistory=async function(){
 if(!active||!models.get(active)?.model)return;
 const path=active,project=state.projectId,info=models.get(path),versionId=info.model.getVersionId(),current=info.model.getValue();
 const versions=await api('history?path='+encodeURIComponent(path));if(state.projectId!==project||active!==path)return;
 workflowDisposeHistory();
 const date=v=>v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8)+' '+v.slice(9,11)+':'+v.slice(11,13)+':'+v.slice(13,15);
 modal('版本历史 · '+path,`<div class="workflow-history-toolbar"><select id="workflowVersion" aria-label="选择历史版本">${versions.map(v=>`<option value="${esc(v)}">${date(v)}</option>`).join('')}</select><button type="button" id="workflowCheckpoint" class="secondary">保存版本</button><button type="button" id="workflowRestore" class="primary" disabled>恢复到编辑区</button></div><div class="workflow-history-labels"><span>历史版本</span><span>当前编辑内容</span></div><div id="workflowHistoryDiff" class="workflow-history-diff"></div><div id="workflowHistoryStatus" class="workflow-note" role="status">${versions.length?'正在比较…':'尚无历史版本，保存版本后可在这里比较。'}</div>`);
 let chosen=null;
 const select=async()=>{
  const token=++workflowHistoryTicket,v=$('#workflowVersion').value;if(!v)return;
  $('#workflowRestore').disabled=true;chosen=null;
  const old=await api('history-content?path='+encodeURIComponent(path)+'&version='+encodeURIComponent(v));
  if(token!==workflowHistoryTicket||!$('#modal').open||state.projectId!==project)return;
  workflowHistoryEditor?.dispose();workflowHistoryModels.forEach(m=>m.dispose());
  workflowHistoryModels=[monacoApi.editor.createModel(old.content,language(path)),monacoApi.editor.createModel(current,language(path))];
  workflowHistoryEditor=monacoApi.editor.createDiffEditor($('#workflowHistoryDiff'),{readOnly:true,originalEditable:false,automaticLayout:true,minimap:{enabled:false},fontSize:14,renderSideBySide:innerWidth>800,ignoreTrimWhitespace:false,scrollBeyondLastLine:false});
  workflowHistoryEditor.setModel({original:workflowHistoryModels[0],modified:workflowHistoryModels[1]});
  chosen=old.content;$('#workflowRestore').disabled=chosen===current;$('#workflowHistoryStatus').textContent=chosen===current?'与当前内容相同':'恢复后可撤销；保存后写入文件。';
 };
 $('#workflowVersion').onchange=()=>select().catch(e=>toast(e.message,true));
 $('#workflowRestore').onclick=()=>{
  if(chosen===null)return;
  if(state.projectId!==project||active!==path||models.get(path)?.model!==info.model||info.model.getVersionId()!==versionId){toast('编辑内容已变化，请重新打开历史比较',true);return;}
  editor.executeEdits('history-restore',[{range:info.model.getFullModelRange(),text:chosen}]);closeModal();toast('已恢复到编辑区，可撤销');
 };
 $('#workflowCheckpoint').onclick=async()=>{try{if(state.projectId!==project||active!==path)throw new Error('项目或文件已切换');await saveFile(path);await api('history-checkpoint',{path,revision:models.get(path).revision});closeModal();await showHistory();toast('版本已保存');}catch(e){toast(e.message,true)}};
 if(versions.length)await select();
};
async function workflowUsage(){
 const value=await api('ai/usage');
 modal('AI 用量',`<div class="workflow-usage-stats"><div><strong>${value.requests}</strong><span>今日请求</span></div><div><strong>${value.tokens.toLocaleString()}</strong><span>已记录 tokens</span></div><div><strong>${value.failures}</strong><span>失败请求</span></div></div><label class="workflow-budget">每日请求上限 <input id="workflowDailyLimit" type="number" min="0" max="10000" value="${value.limit}"></label><div class="workflow-note">0 表示不限。失败请求也计次；tokens 以服务返回为准。按本机日期重置。</div><button type="button" id="workflowSaveBudget" class="primary">保存上限</button>`);
 $('#workflowSaveBudget').onclick=async()=>{try{const v=await api('ai/usage',{limit:Number($('#workflowDailyLimit').value)});closeModal();toast('每日上限已保存');workflowBudget=v;workflowEstimate();}catch(e){toast(e.message,true)}};
}
let workflowBudget=null,workflowBudgetAt=0,workflowBudgetJobKey='';
async function workflowRefreshBudget(){if(Date.now()-workflowBudgetAt<3000)return;workflowBudgetAt=Date.now();workflowBudget=await api('ai/usage');workflowEstimate();}
function workflowEstimate(){
 const target=editorAiTarget,model=models.get(target?.path||active)?.model;
 const selected=target?.selection?target.selection[1]-target.selection[0]:null;
 const chars=selected??Math.min(model?.getValueLength?.()||0,14000),rounds=$('#editorAiMode').value==='repair'?Number($('#editorAiLimit').value)||1:1;
 $('#workflowEstimate').textContent=(selected?'选区 '+chars+' 字符':'当前文件相关片段')+' · 最多 '+rounds+' 次请求'+(chars?' · 输入约 '+Math.ceil(chars*.8+1800).toLocaleString()+' tokens/次':'')+(workflowBudget?' · 今日 '+workflowBudget.requests+'/'+(workflowBudget.limit||'不限'):'');
 $('#workflowEstimate').title='发送范围会随错误定位调整；用量为粗略估计，不含模型输出。';
}
const workflowOldAiRender=editorAiRender;
editorAiRender=function(){
 workflowOldAiRender();workflowEstimate();
 const j=editorAiJob,steps=$('#workflowRepairSteps');steps.hidden=!j||j.mode==='explain';
 if(!j)return;
 const budgetKey=j.id+':'+j.requestCount+':'+j.running;
 if(budgetKey!==workflowBudgetJobKey){workflowBudgetJobKey=budgetKey;workflowBudgetAt=0;workflowRefreshBudget().catch(()=>{});}
 let current=j.applied?4:j.verified?3:j.changedPaths?.length?2:j.requestCount?1:0;
 const labels=['定位问题','生成修改','编译验证','确认应用'];
 steps.innerHTML=labels.map((label,i)=>`<li class="${i<current?'done':i===current?'current':''}"${i===current?' aria-current="step"':''}><span>${i<current?'✓':i+1}</span>${label}</li>`).join('');
 if(j.error&&!j.running&&!j.verified){const li=steps.children[Math.min(current,3)];li?.classList.add('failed');}
};
const workflowOldAiOpen=editorAiOpen;editorAiOpen=function(mode){workflowOldAiOpen(mode);workflowRefreshBudget().catch(()=>{});};
$('#editorAiLimit').addEventListener('change',workflowEstimate);$('#editorAiMode').addEventListener('change',workflowEstimate);$('#editorAiCapture').addEventListener('click',workflowEstimate);
async function workflowLocate(){
 if(editorAiDirty())throw new Error('请先保存并编译，再定位 PDF');
 if(editorAiPreview)throw new Error('请先返回原 PDF，再定位源码');
 const path=active,line=editor?.getPosition()?.lineNumber||1,project=state.projectId,pdfVersion=state.pdfVersion;
 const point=await api('sync-point?direction=forward&path='+encodeURIComponent(path)+'&line='+line);
 if(project!==state.projectId||pdfVersion!==state.pdfVersion)return;
 if(editorAiDirty())throw new Error('源码已变化，请保存并编译后定位');
 const app=$('#pdfFrame').contentWindow?.PDFViewerApplication;if(!app?.pdfDocument)throw new Error('请使用内置 PDF 预览后定位');
 const page=await app.pdfDocument.getPage(point.page);
 if(project!==state.projectId||pdfVersion!==state.pdfVersion||editorAiDirty()||editorAiPreview||app!==$('#pdfFrame').contentWindow?.PDFViewerApplication)return;
 const box=page.view;
 app.pdfViewer.scrollPageIntoView({pageNumber:point.page,destArray:[null,{name:'XYZ'},box[0]+point.x*(box[2]-box[0]),box[1]+(1-point.y)*(box[3]-box[1]),null]});
 toast('已定位至第 '+point.page+' 页附近');
}
$('#pdfFrame').addEventListener('load',()=>{
 const frame=$('#pdfFrame');let doc;try{doc=frame.contentDocument}catch{return;}if(!doc)return;
 doc.addEventListener('dblclick',async e=>{
  const sheet=e.target.closest?.('.page');if(!sheet||!e.ctrlKey)return;
  try{
   if(editorAiDirty())throw new Error('请先保存并编译，再定位源码');
   if(editorAiPreview)throw new Error('请先返回原 PDF，再定位源码');
   const rect=sheet.getBoundingClientRect(),project=state.projectId,pdfVersion=state.pdfVersion;
   const point=await api('sync-point?direction=inverse&page='+sheet.dataset.pageNumber+'&x='+((e.clientX-rect.left)/rect.width)+'&y='+((e.clientY-rect.top)/rect.height));
   if(state.projectId!==project||state.pdfVersion!==pdfVersion||editorAiDirty()||editorAiPreview)return;await openFile(point.path,point.line);toast('已定位至 '+point.path+' 第 '+point.line+' 行附近');
  }catch(err){toast(err.message,true)}
 });
});
$('#workflowHistory').onclick=()=>{ $('#editorToolsMenu').open=false;showHistory().catch(e=>toast(e.message,true));};
$('#workflowLocate').onclick=()=>{ $('#editorToolsMenu').open=false;workflowLocate().catch(e=>toast(e.message,true));};
$('#workflowUsage').onclick=()=>{ $('#editorToolsMenu').open=false;workflowUsage().catch(e=>toast(e.message,true));};
commands.push(['定位到 PDF（反向：Ctrl＋双击 PDF）','workflowLocate','']);commands.push(['AI 用量与每日上限','workflowUsage','']);
const workflowOldRun=run;run=async function(action){if(action==='workflowLocate')return workflowLocate();if(action==='workflowUsage')return workflowUsage();return workflowOldRun(action);};

$('#workflowWritingUsage').onclick=()=>workflowUsage().catch(e=>toast(e.message,true));
