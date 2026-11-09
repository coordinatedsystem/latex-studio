'use strict';
showHistory=async function(){
 if(!active||!models.get(active)?.model)return;
 const path=active,project=state.projectId,info=models.get(path);let versionId=info.model.getVersionId(),current=info.model.getValue().replace(/\r\n/g,'\n'),versions=[],chosen=null,chosenId='';
 const guard=()=>{if(state.projectId!==project||active!==path||models.get(path)?.model!==info.model)throw new Error('项目或文件已切换，请重新打开历史');};
 const date=v=>v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8)+' '+v.slice(9,11)+':'+v.slice(11,13)+':'+v.slice(13,15);
 const load=async()=>{const result=await api('history?path='+encodeURIComponent(path)+'&details=1');guard();versions=result.map(v=>typeof v==='string'?{id:v,reason:'历史保存'}:v);};
 await load();workflowDisposeHistory();
 modal('版本历史 · '+path,`<div class="history-actions"><span id="historyCount"></span><button type="button" id="workflowCheckpoint" class="primary">保存当前版本</button><button type="button" id="workflowRestore" class="secondary" disabled>恢复到编辑区</button></div><div class="history-workspace"><nav id="historyRecent" aria-label="最近修改记录"></nav><section><div class="workflow-history-labels"><span>所选历史版本</span><span>当前编辑内容</span></div><div id="workflowHistoryDiff" class="workflow-history-diff"></div></section></div><select id="workflowVersion" aria-label="选择历史版本" hidden></select><div id="workflowHistoryStatus" class="workflow-note" role="status"></div>`);
 const paint=()=>{$('#historyCount').textContent='最近 '+versions.length+' 个版本';$('#workflowVersion').innerHTML=versions.map(v=>`<option value="${v.id}">${date(v.id)}</option>`).join('');$('#workflowVersion').value=chosenId;$('#historyRecent').innerHTML=versions.map(v=>`<button type="button" data-history-version="${v.id}" class="${v.id===chosenId?'active':''}" aria-pressed="${v.id===chosenId}"><strong>${date(v.id)}</strong><span>${esc(v.reason)}</span></button>`).join('')||'<p>修改并保存后自动记录，也可保存当前版本。</p>';};
 const select=async id=>{
  const ticket=++workflowHistoryTicket;chosenId=id;chosen=null;$('#workflowRestore').disabled=true;paint();if(!id){$('#workflowHistoryStatus').textContent='还没有历史记录';return;}
  const old=await api('history-content?path='+encodeURIComponent(path)+'&version='+encodeURIComponent(id));if(ticket!==workflowHistoryTicket||!$('#modal').open||state.projectId!==project)return;
  workflowHistoryEditor?.dispose();workflowHistoryModels.forEach(m=>m.dispose());workflowHistoryModels=[monacoApi.editor.createModel(old.content,language(path)),monacoApi.editor.createModel(current,language(path))];
  workflowHistoryEditor=monacoApi.editor.createDiffEditor($('#workflowHistoryDiff'),{readOnly:true,originalEditable:false,automaticLayout:true,minimap:{enabled:false},fontSize:14,fontFamily:'"Studio Digits", "Studio Source Han", Consolas, monospace',renderSideBySide:innerWidth>900,ignoreTrimWhitespace:false,scrollBeyondLastLine:false});workflowHistoryEditor.setModel({original:workflowHistoryModels[0],modified:workflowHistoryModels[1]});chosen=old.content.replace(/\r\n/g,'\n');$('#workflowRestore').disabled=chosen===current;$('#workflowHistoryStatus').textContent=chosen===current?'与当前内容一致':'恢复到编辑区后可撤销，保存后写入文件';
 };
 $('#historyRecent').onclick=e=>{const b=e.target.closest('[data-history-version]');if(b)select(b.dataset.historyVersion).catch(e=>toast(e.message,true));};$('#workflowVersion').onchange=()=>select($('#workflowVersion').value).catch(e=>toast(e.message,true));
 $('#workflowRestore').onclick=()=>{try{guard();if(chosen===null)return;if(info.model.getVersionId()!==versionId)throw new Error('编辑内容已变化，请重新打开历史');editor.executeEdits('history-restore',[{range:info.model.getFullModelRange(),text:chosen}]);closeModal();toast('已恢复到编辑区，可撤销');}catch(e){toast(e.message,true);}};
 $('#workflowCheckpoint').onclick=async()=>{const button=$('#workflowCheckpoint');button.disabled=true;try{guard();const captured=info.model.getVersionId();await saveFile(path);guard();if(info.model.getVersionId()!==captured||info.dirty)throw new Error('编辑仍在变化，请停止输入后保存版本');await api('history-checkpoint',{path,revision:info.revision});current=info.model.getValue().replace(/\r\n/g,'\n');versionId=info.model.getVersionId();await load();await select(versions[0]?.id||'');toast('当前版本已保存');}catch(e){toast(e.message,true);}finally{button.disabled=false;}};
 await select(versions[0]?.id||'');
};
async function editorAiHistory(){
 const project=state.projectId,items=await api('editor-ai/history');if(project!==state.projectId)return;
 modal('AI 修改记录',`<div id="editorAiHistoryList" class="ai-history-list">${items.map(item=>`<button type="button" data-editor-job="${item.id}"><span><strong>${esc(item.summary||item.question||({repair:'修复报错',edit:'修改代码',explain:'解释代码'})[item.mode])}</strong><small>${esc(item.path)} · ${new Date((item.updated||item.created)*1000).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'})}</small></span><b>${item.running?'处理中':item.undone?'已撤销':item.applied?'已应用':esc(item.stage||'已保存')}</b></button>`).join('')||'<p>AI 任务完成后会自动保留最近记录。</p>'}</div>`);
 $('#editorAiHistoryList').onclick=editorAiWatch(async e=>{const b=e.target.closest('[data-editor-job]');if(!b)return;if(editorAiJob?.running)throw new Error('请先停止当前任务');const job=await api('editor-ai/job?id='+b.dataset.editorJob);if(state.projectId!==project)return;editorAiSequence++;editorAiEffectTicket++;editorAiEffectMeta=null;editorAiDiscardDiff();editorAiView(false);editorAiClearPdf();editorAiJob=job;$('#editorAiMode').value=job.mode;$('#editorAiPrompt').value=job.question||'';editorAiMode();closeModal();editorAiDock('ai');editorAiRender();});
}
function qualityMarkup(q){if(!q)return '';return `<strong>${q.warnings?.length?'需要复核':'约束检查已完成'}</strong>${q.warnings?.length?'<ul>'+[...new Set(q.warnings)].map(w=>`<li>${esc(w)}</li>`).join('')+'</ul>':'<span>请结合原意与 PDF 效果确认</span>'}`;}
(()=>{
 const button=document.createElement('button');button.type='button';button.id='editorAiHistory';button.className='secondary';button.textContent='历史';$('#editorAiClear').before(button);button.onclick=editorAiWatch(editorAiHistory);
 $('#editorAiResponse').insertAdjacentHTML('beforebegin','<aside id="editorAiQuality" class="ai-quality-report" hidden></aside>');
 const render=editorAiRender;editorAiRender=function(){render();const q=editorAiJob?.quality,el=$('#editorAiQuality');el.hidden=!q;el.innerHTML=qualityMarkup(q);button.disabled=!!editorAiJob?.running;};
 $('.writing-compare-toolbar').insertAdjacentHTML('afterend','<aside id="writingQuality" class="ai-quality-report" hidden></aside>');
 const controls=writingControls;writingControls=function(){controls();const q=writing.preview?.quality||writing.result?.quality,el=$('#writingQuality');el.hidden=!q;el.innerHTML=qualityMarkup(q);};
 const helpButton=$('#modal header [data-feature-help]');
 if(helpButton){const sync=()=>{const title=$('#modalTitle').textContent,topic=/修改记录/.test(title)?'editorAi':/版本与更新/.test(title)?'updates':/服务/.test(title)?'service':/历史/.test(title)?'history':/设置/.test(title)?'settings':null;helpButton.hidden=!topic;if(topic){helpButton.dataset.featureHelp=topic;helpButton.onclick=()=>{helpButton.dataset.featureHelp=topic;};}};new MutationObserver(sync).observe($('#modalTitle'),{childList:true,subtree:true,characterData:true});sync();}
 studioHelp.history[1]=['文件保存、AI 应用和撤销都会自动保留前后版本，最近 30 个版本可逐项比较。','点击“保存当前版本”立即记录；选中历史后可恢复到编辑区，再保存写入文件。'];
 studioHelp.editorAi[1].push('“历史”可查看最近 20 次任务。约束检查不保证语义正确，仍需对照预览确认。');
})();
