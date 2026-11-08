'use strict';
// Source snapshots belong to one project and one file. Never apply to a changed buffer.
let aiTask='check',aiConfig=null,aiContext=null,aiJob=null,aiTimer=null,aiPolling=false,aiResult=null,aiApplied=new Set(),aiChosen=new Set(),aiDiffEditor=null,aiDiffModels=[];
const aiNames={check:'检查诊断',correct:'智能纠错',format:'源码排版',polish:'学术润色',translate:'正文翻译',dictionary:'有道词典',workflow:'审稿工作流'};
commands.push(['AI 助手','ai',''],['AI 处理当前选区或文件','aiSelection',''],['AI 服务配置','aiSettings','']);

function aiNotice(message){$('#aiError').textContent=message;$('#aiError').hidden=!message;}
function aiCount(){const n=Array.from($('#aiInput').value).length;$('#aiCharCount').textContent=n.toLocaleString()+' 字符';$('#aiStart').disabled=!!aiJob?.running||!n;$('#aiStartTop').disabled=$('#aiStart').disabled;}
function aiStep(index){$$('#aiSteps li').forEach((el,i)=>{el.classList.toggle('current',i===index);el.classList.toggle('done',i<index);});}
function aiScopeLabel(){return {selection:'编辑器选区',file:'当前文件',text:'粘贴文本'}[$('#aiScope').value];}
function aiModelText(model){return model.getValue().replace(/\r\n/g,'\n');}
function aiControls(){
 const provider=$('#aiProvider').value;const busy=!!aiJob?.running;
 $$('#aiTasks button').forEach(b=>{const on=b.dataset.aiTask===aiTask;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));b.disabled=busy;});
 $('#aiWorkflow').classList.toggle('selected',aiTask==='workflow');$('#aiWorkflow').setAttribute('aria-pressed',String(aiTask==='workflow'));$('#aiWorkflow').disabled=busy;
 $('#aiLanguageField').hidden=aiTask!=='translate';$('#aiProvider').disabled=busy;$('#aiScope').disabled=busy;$('#aiCapture').disabled=busy;$('#aiInput').disabled=busy;$('#aiInput').readOnly=$('#aiScope').value!=='text';$('#aiNotes').disabled=busy;
 $('#aiStart').innerHTML='<span>✦</span>'+(aiTask==='workflow'?'运行工作流':aiTask==='dictionary'?'查询词典':'开始'+({check:'检查',correct:'纠错',format:'排版',polish:'润色',translate:'翻译'}[aiTask]||'处理'));
 $('#aiStartTop').textContent=$('#aiStart').textContent+' ↗';
 $('#aiCancel').hidden=!busy;$('#aiProgress').hidden=!busy;
 const target={local:'本地检查在你的电脑上运行。',deepseek:'点击开始后，仅将上方内容和补充要求发送到 DeepSeek。',youdao:'点击开始后，仅将上方文本发送到有道智云。'}[provider];
 $('#aiSendHint').textContent=target+(aiTask==='workflow'?' 此工作流包含两次 AI 请求。':'')+(provider==='youdao'&&aiTask==='translate'?' 请选择纯文本段落；含 LaTeX 的内容可用 DeepSeek。':'');
 $('#aiNotes').disabled=busy||provider!=='deepseek';aiCount();$('#aiStartTop').disabled=$('#aiStart').disabled;
}
function aiChooseTask(task){
 aiTask=task;
 if(task==='dictionary')$('#aiProvider').value='youdao';
 else if(task!=='check'&&($('#aiProvider').value==='local'||(task!=='translate'&&$('#aiProvider').value==='youdao')))$('#aiProvider').value='deepseek';
 aiControls();
}
async function aiLoadConfig(){aiConfig=await api('ai/config');$('#aiConnection').classList.toggle('connected',aiConfig.deepseek.configured||aiConfig.youdao.configured);return aiConfig;}

async function aiCapture(auto=false){
 if(aiJob?.running)return;
 if(!editor||!monacoApi)throw new Error('编辑器正在加载，请稍后重试');
 if(!models.get(active)?.model){await openFile(state.main);}
 const model=models.get(active)?.model;if(!model)throw new Error('请先打开一个文本文件');
 let scope=$('#aiScope').value,selection=editor.getSelection();
 if(auto){scope=selection&&!selection.isEmpty()?'selection':'file';$('#aiScope').value=scope;}
 if(scope==='text'){aiContext=null;$('#aiInput').readOnly=false;$('#aiSourceInfo').textContent='粘贴文本 · 结果可复制，不会自动写入文件';aiControls();return;}
 if(scope==='selection'&&(!selection||selection.isEmpty()))throw new Error('当前没有选区。请在编辑器中选中文本，或改用「当前文件」。');
 const raw=model.getValue(),rawStart=scope==='selection'?model.getOffsetAt(selection.getStartPosition()):0,rawEnd=scope==='selection'?model.getOffsetAt(selection.getEndPosition()):raw.length;
 const full=raw.replace(/\r\n/g,'\n'),start=raw.slice(0,rawStart).replace(/\r\n/g,'\n').length,end=raw.slice(0,rawEnd).replace(/\r\n/g,'\n').length;
 const text=full.slice(start,end);
 aiContext={projectId:state.projectId,path:active,full,start,end,text,scope,line:model.getPositionAt(rawStart).lineNumber};
 $('#aiInput').value=text;$('#aiSourceInfo').textContent=active+' · '+(scope==='selection'?'第 '+model.getPositionAt(rawStart).lineNumber+'–'+model.getPositionAt(rawEnd).lineNumber+' 行':'完整文件');
 aiResult=null;aiApplied.clear();$('#aiResults').hidden=true;$('#aiReviewActions').hidden=true;$('#aiEmpty').hidden=false;$('#aiCopy').disabled=true;aiNotice('');aiStep(0);aiControls();
}

async function aiSettings(){
 await aiLoadConfig();
 const body=modal('AI 服务配置',`<div class="ai-settings-intro">密钥使用 Windows 账户加密保存在本机。留空保留已有密钥。</div><div class="ai-settings-block"><div class="ai-provider-heading"><strong>DeepSeek</strong><span class="state-badge ${aiConfig.deepseek.configured?'success':'warning'}">${aiConfig.deepseek.configured?'已配置':'待配置'}</span></div><label>模型名称<input id="aiModelConfig" value="${esc(aiConfig.deepseek.model)}" autocomplete="off"></label><label>API Key<input id="aiKeyConfig" type="password" autocomplete="new-password" placeholder="${aiConfig.deepseek.configured?'已有密钥；输入新密钥以替换':'输入 DeepSeek API Key'}"></label><label class="ai-clear-key"><input id="aiClearDeepseek" type="checkbox">移除已存密钥</label><a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">获取 DeepSeek 密钥 ↗</a></div><div class="ai-settings-block"><div class="ai-provider-heading"><strong>有道智云</strong><span class="state-badge ${aiConfig.youdao.configured?'success':'warning'}">${aiConfig.youdao.configured?'已配置':'待配置'}</span></div><label>应用 ID<input id="aiYoudaoId" value="${esc(aiConfig.youdao.appId)}" autocomplete="off"></label><label>应用密钥<input id="aiYoudaoSecret" type="password" autocomplete="new-password" placeholder="${aiConfig.youdao.configured?'已有密钥；输入新密钥以替换':'输入有道应用密钥'}"></label><label class="ai-clear-key"><input id="aiClearYoudao" type="checkbox">移除已存密钥</label><a href="https://ai.youdao.com/console/" target="_blank" rel="noreferrer">打开有道控制台 ↗</a><p>翻译与词典分别需要开通对应服务。保存配置不发送文档；任务结果会显示鉴权及权限错误。</p></div><p id="aiSettingsError" class="ai-error" hidden></p><div class="dialog-actions"><button type="button" id="aiSettingsSave" class="primary">保存配置</button></div>`);
 $('#aiSettingsSave').onclick=async()=>{const button=$('#aiSettingsSave');button.disabled=true;try{
  aiConfig=await api('ai/config',{model:$('#aiModelConfig').value,deepseekKey:$('#aiKeyConfig').value,youdaoId:$('#aiYoudaoId').value,youdaoSecret:$('#aiYoudaoSecret').value,cleardeepseekKey:$('#aiClearDeepseek').checked,clearyoudaoSecret:$('#aiClearYoudao').checked});
  $('#aiKeyConfig').value='';$('#aiYoudaoSecret').value='';$('#modal').close();body.replaceChildren();await aiLoadConfig();toast('服务配置已加密保存');
 }catch(e){$('#aiSettingsError').hidden=false;$('#aiSettingsError').textContent=e.message;}finally{button.disabled=false;}};
}

async function aiStart(){
 if(aiJob?.running)return;
 aiNotice('');
 const text=$('#aiInput').value,scope=$('#aiScope').value,provider=$('#aiProvider').value;
 if(!text.trim())throw new Error('请先读取或粘贴待处理内容');
 if(scope!=='text'&&(!aiContext||aiContext.projectId!==state?.projectId||aiContext.scope!==scope))throw new Error('处理范围已变化，请重新读取编辑器内容');
 if(scope!=='text'&&aiContext&&(!models.get(aiContext.path)?.model||aiModelText(models.get(aiContext.path).model)!==aiContext.full))throw new Error('源码已修改，请重新读取内容后开始');
 const context=scope==='text'?{text,scope,projectId:state.projectId,path:null,full:text,start:0,end:text.length,line:1}:{...aiContext};
 const job=await api('ai/start',{task:aiTask,provider,text,scope,target:$('#aiLanguage').value,instruction:$('#aiNotes').value});
 aiContext=context;aiJob=job;aiResult=null;aiApplied.clear();aiChosen.clear();$('#aiResults').hidden=true;$('#aiReviewActions').hidden=true;$('#aiEmpty').hidden=true;$('#aiCopy').disabled=true;$('#aiCancel').textContent='停止';
 aiStep(1);aiControls();clearInterval(aiTimer);aiTimer=setInterval(aiPoll,650);await aiPoll();
}
async function aiPoll(){
 if(aiPolling||!aiJob?.id)return;aiPolling=true;
 try{
  if(aiContext?.projectId!==state?.projectId){clearInterval(aiTimer);aiJob=null;aiNotice('当前项目已切换，请回到原项目重新读取内容。');aiControls();return;}
  const job=await api('ai/job?id='+encodeURIComponent(aiJob.id));
  if(!job.id){clearInterval(aiTimer);aiJob=null;aiNotice('任务已失效，请重新运行。');aiControls();return;}
  aiJob=job;$('#aiStage').textContent=job.stage;$('#aiElapsed').textContent=Math.max(0,Math.floor(Date.now()/1000-job.started))+'s';
  if(!job.running){clearInterval(aiTimer);if(job.success){aiResult=job.result;
   // Python uses code-point offsets; Monaco and JS strings use UTF-16 offsets.
   const points=Array.from(aiContext.text);aiResult.edits=(aiResult.edits||[]).map(e=>({...e,start:points.slice(0,e.start).join('').length,end:points.slice(0,e.end).join('').length}));
   aiChosen=new Set(aiResult.edits.map((_,i)=>i));aiStep(2);aiRenderResults();
  }else{aiNotice(job.error||'任务未完成，请重试');$('#aiEmpty').hidden=false;}}
  aiControls();
 }catch(e){clearInterval(aiTimer);aiNotice(e.message+'。可点击「恢复任务状态」继续查看。');$('#aiStage').textContent='连接中断';$('#aiCancel').hidden=false;$('#aiCancel').textContent='恢复任务状态';}
 finally{aiPolling=false;}
}

function aiCompose(indices){let text=aiContext.text;const edits=aiResult.edits.filter((_,i)=>indices.has(i)).sort((a,b)=>b.start-a.start);for(const e of edits)text=text.slice(0,e.start)+e.after+text.slice(e.end);return text;}
function aiExpected(indices){const value=aiCompose(indices);return aiContext.full.slice(0,aiContext.start)+value+aiContext.full.slice(aiContext.end);}
function aiRenderResults(){
 $('#aiResults').hidden=false;$('#aiEmpty').hidden=true;$('#aiCopy').disabled=false;$('#aiSummary').textContent=aiResult.summary+((aiResult.rejected||[]).length?' 已拦截 '+aiResult.rejected.length+' 项无法安全应用的修改：'+aiResult.rejected.map(r=>r.reason).join('；'):'');
 if($('#aiTermsUsed')){$('#aiTermsUsed').hidden=!aiResult.terminology?.length;$('#aiTermsUsed').textContent=aiResult.terminology?.length?'已附术语：'+aiResult.terminology.map(t=>t.source+' → '+t.target).join('；'):'';}
 $('#aiResultMeta').textContent=aiNames[aiJob.task]+' · '+aiJob.duration+'s';
 $('#aiStepResults').innerHTML=(aiResult.steps||[]).map((s,i)=>`<p><span>${i+1}</span>${esc(s)}</p>`).join('');
 const issues=aiResult.issues||[];
 $('#aiIssues').innerHTML=issues.length?`<details open><summary>${issues.length} 条检查提示</summary>${issues.map((issue,i)=>`<button type="button" data-ai-issue="${i}" class="ai-issue ${esc(issue.severity||'warning')}"><span>${issue.severity==='error'?'!':'·'}</span><div><strong>第 ${Number(issue.line)+aiContext.line-1} 行</strong><p>${esc(issue.message)}</p></div><span>↗</span></button>`).join('')}</details>`:'';
 $('#aiDictionary').hidden=!aiResult.dictionary;$('#aiDictionary').textContent=aiResult.dictionary||'';
 const edits=aiResult.edits||[];$('#aiChangeToolbar').hidden=!edits.length;$('#aiReviewActions').hidden=!edits.length;
 $('#aiEdits').innerHTML=edits.length?edits.map((e,i)=>`<article class="ai-edit ${aiApplied.has(i)?'applied':''}"><label class="ai-edit-title"><input type="checkbox" data-ai-edit="${i}" ${aiChosen.has(i)?'checked':''} ${aiApplied.has(i)?'disabled':''}><strong>${esc(e.reason)}</strong><span>${aiApplied.has(i)?'已采纳':'建议 '+(i+1)}</span></label><div class="ai-edit-code"><div class="before"><small>原文</small><pre>${esc(e.before||'（插入位置）')}</pre></div><div class="after"><small>建议</small><pre>${esc(e.after||'（删除）')}</pre></div></div></article>`).join(''):(aiResult.dictionary?'':'<div class="ai-no-edits">本次未返回可定位修改。若只有版面建议，可到「单页修改」关联源码并生成可应用版本；不会自动重试 AI。</div>');
 if(!aiContext.path&&edits.length)$('#aiSummary').textContent+=' 粘贴文本的结果可复制使用。';
 aiUpdateSelected();
}
function aiUpdateSelected(){
 const available=(aiResult?.edits||[]).map((_,i)=>i).filter(i=>!aiApplied.has(i));
 $('#aiSelectedCount').textContent=aiChosen.size+' 项待采纳'+(aiApplied.size?' · 已采纳 '+aiApplied.size+' 项':'');
 $('#aiApply').disabled=!aiChosen.size||!aiContext?.path;$('#aiApplyCompile').disabled=!aiChosen.size||!aiContext?.path;
 $('#aiSelectAll').checked=available.length>0&&available.every(i=>aiChosen.has(i));$('#aiSelectAll').indeterminate=aiChosen.size>0&&aiChosen.size<available.length;
}
async function aiApply(compileAfter=false){
 if(!aiResult||!aiChosen.size||!aiContext.path)return;
 if(state?.projectId!==aiContext.projectId)throw new Error('项目已切换，未应用修改');
 const info=models.get(aiContext.path);if(!info?.model)throw new Error('原文件已关闭，请重新打开并运行任务');
 const current=aiExpected(aiApplied);
 if(aiModelText(info.model)!==current)throw new Error('原文件在任务后发生了变化，未覆盖你的修改。请重新读取并运行任务。');
 const combined=new Set([...aiApplied,...aiChosen]);const target=aiExpected(combined);
 info.model.pushStackElement();info.model.pushEditOperations([],[{range:info.model.getFullModelRange(),text:target}],()=>null);info.model.pushStackElement();
 aiApplied=combined;aiChosen.clear();aiRenderResults();toast('建议已采纳，可在编辑器中撤销');
 if(compileAfter){$('#modal').close();await openFile(aiContext.path);aiStep(3);await run('compile');}
}
function aiDisposeDiff(){aiDiffEditor?.dispose();aiDiffEditor=null;aiDiffModels.forEach(m=>m.dispose());aiDiffModels=[];$('#modal').classList.remove('ai-diff-modal');}
function aiShowDiff(){
 if(!aiResult?.edits?.length)return;aiDisposeDiff();
 modal('差异对比 · '+(aiContext.path||'粘贴文本'),'<div class="ai-diff-legend"><span>原始内容</span><span>已采纳 + 当前所选建议</span></div><div id="aiDiffEditor" class="ai-diff-editor"></div><p class="ai-diff-note">此处仅预览；关闭对比后可继续选择并采纳建议。</p>');$('#modal').classList.add('ai-diff-modal');
 aiDiffModels=[monacoApi.editor.createModel(aiContext.text,'latex'),monacoApi.editor.createModel(aiCompose(new Set([...aiApplied,...aiChosen])),'latex')];
 aiDiffEditor=monacoApi.editor.createDiffEditor($('#aiDiffEditor'),{fontFamily:'"Studio Digits", "Studio Source Han", Consolas, "Microsoft YaHei", monospace',readOnly:true,originalEditable:false,automaticLayout:true,renderSideBySide:innerWidth>800,ignoreTrimWhitespace:false,renderWhitespace:'all',minimap:{enabled:false},scrollBeyondLastLine:false,fontSize:13,theme:'vs',renderOverviewRuler:false});
 aiDiffEditor.setModel({original:aiDiffModels[0],modified:aiDiffModels[1]});
}
async function aiRun(action){
 if(action==='aiSettings'){await aiSettings();return;}
 if(typeof writingOpen==='function'){if(typeof writingCaptureEntry==='function')writingCaptureEntry(action);hubView('ai');await aiLoadConfig();reviewShow('assistant');await writingOpen(action==='aiSelection');return;}
 if(typeof reviewShow==='function')reviewShow('assistant');
 hubView('ai');await aiLoadConfig();
 if(action==='aiSelection'||!$('#aiInput').value||(aiContext&&aiContext.projectId!==state?.projectId))await aiCapture(true);
 aiControls();
}
$$('#aiTasks button').forEach(b=>b.onclick=()=>aiChooseTask(b.dataset.aiTask));$('#aiWorkflow').onclick=()=>aiChooseTask('workflow');
$('#aiProvider').onchange=()=>{const p=$('#aiProvider').value;if(p==='local')aiTask='check';if(p==='youdao'&&!['dictionary','translate'].includes(aiTask))aiTask='translate';aiControls();};
$('#aiScope').onchange=()=>{aiContext=null;aiResult=null;aiApplied.clear();aiChosen.clear();$('#aiInput').value='';$('#aiResults').hidden=true;$('#aiReviewActions').hidden=true;$('#aiEmpty').hidden=false;$('#aiCopy').disabled=true;aiStep(0);if($('#aiScope').value==='text'){$('#aiSourceInfo').textContent='粘贴文本 · 结果可复制';}else $('#aiSourceInfo').textContent='范围已更改，请重新读取内容';aiControls();};
$('#aiInput').oninput=aiCount;
$('#aiCapture').onclick=()=>aiCapture().catch(e=>aiNotice(e.message));$('#aiStart').onclick=()=>aiStart().catch(e=>aiNotice(e.message));
$('#aiStartTop').onclick=()=>aiStart().catch(e=>aiNotice(e.message));
$('#aiCancel').onclick=async()=>{try{if($('#aiCancel').textContent==='恢复任务状态'){$('#aiCancel').textContent='停止';clearInterval(aiTimer);aiTimer=setInterval(aiPoll,650);await aiPoll();}else if(aiJob?.id){await api('ai/cancel',{id:aiJob.id});$('#aiStage').textContent='正在停止；本次响应将丢弃';}}catch(e){aiNotice(e.message);}};
$('#aiSelectAll').onchange=e=>{aiChosen=new Set(aiResult.edits.map((_,i)=>i).filter(i=>e.target.checked&&!aiApplied.has(i)));aiRenderResults();};
$('#aiEdits').onchange=e=>{if(e.target.matches('[data-ai-edit]')){const i=Number(e.target.dataset.aiEdit);if(e.target.checked)aiChosen.add(i);else aiChosen.delete(i);aiUpdateSelected();}};
$('#aiIssues').onclick=async e=>{const b=e.target.closest('[data-ai-issue]');if(!b||!aiContext.path)return;try{if(aiContext.projectId!==state.projectId)throw new Error('项目已切换');await openFile(aiContext.path,Number(aiResult.issues[Number(b.dataset.aiIssue)].line)+aiContext.line-1);hubView('editor');}catch(err){toast(err.message,true);}};
$('#aiApply').onclick=()=>aiApply().catch(e=>aiNotice(e.message));$('#aiApplyCompile').onclick=()=>aiApply(true).catch(e=>aiNotice(e.message));$('#aiDiff').onclick=aiShowDiff;
$('#aiCopy').onclick=async()=>{try{await navigator.clipboard.writeText(aiResult.dictionary||aiCompose(new Set([...aiApplied,...aiChosen])));toast('结果已复制');}catch{aiNotice('无法访问剪贴板，请在差异对比中选中并复制。');}};
$('#modal').addEventListener('close',aiDisposeDiff);
aiControls();
