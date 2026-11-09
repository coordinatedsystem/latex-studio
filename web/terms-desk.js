'use strict';
const termsDesk={project:null,result:null,chosen:new Set(),plan:null,busy:false,job:null};
function termsControls(){
 const busy=termsDesk.busy||!!state?.running||!!state?.aiBusy;$('#termsExtract').disabled=busy;$('#termsExtract').textContent=termsDesk.busy&&termsDesk.action==='extract'?'正在检索…':'AI 提取全文术语';
 const selected=typeof glossarySelection==='undefined'?[]:[...glossarySelection].filter(t=>glossaryData?.terms.includes(t));
 $('#termsSearchSelected').disabled=busy||!selected.length;$('#termsSearchSelected').textContent='AI 检索所选术语'+(selected.length?'（'+selected.length+'）':'');
 for(const id of ['termsPreview','termsImport','termsSelectAll'])$('#'+id).disabled=busy||!termsDesk.result?.groups.length;
 $('#termsApply').disabled=busy||![...termsDesk.chosen].some(id=>termsDesk.result?.groups.find(g=>g.id===id)?.relation==='same')||!!termsDesk.result?.applied;
 $('#termsUndo').hidden=!termsDesk.result?.applied;$('#termsUndo').disabled=busy;
 $('#termsStop').hidden=!busy||!termsDesk.job?.running;
 $('#termsPreview').disabled||=!!termsDesk.result?.applied;
 $('#termsReport').querySelectorAll('input,select').forEach(el=>el.disabled=busy||(!!termsDesk.result?.applied&&el.hasAttribute('data-term-preferred')));
}
function termsMessage(text,error=false){$('#termsStatus').textContent=text;$('#termsStatus').classList.toggle('error',error);}
async function termsStop(){
 const job=termsDesk.job;if(!job?.running)return;
 $('#termsStop').disabled=true;termsMessage('正在停止提取，返回的结果不会应用…');
 try{await api('ai/cancel',{id:job.id});}finally{$('#termsStop').disabled=false;}
}
function termsGuard(){reviewGuard(termsDesk.project);if([...models.values()].some(i=>i.dirty))throw new Error('源码有未保存的改动。请先保存，再重新提取术语。');}
function termsWatch(fn){return async(...args)=>{try{await fn(...args);}catch(e){termsMessage(e.message,true);}finally{termsControls();}};}
function termsShow(report=true){for(const id of ['glossaryImport','glossaryExport','glossarySave','termsSearchSelected'])$('#'+id).hidden=report;$('#termsDesk').hidden=!report;$('#review-glossary>.review-card').hidden=report;$('#termsShow').textContent=report?'返回术语表':'查看提取结果';}
function termsRender(){
 const result=termsDesk.result;$('#termsReport').innerHTML=(result?.groups||[]).map(g=>{
 const total=g.variants.reduce((n,v)=>n+v.count,0),labels={same:'同义写法',abbreviation:'全称与缩写',related:'独立或相关术语'};
 return `<article class="term-group"><header><label><input type="checkbox" data-term-choice="${g.id}" ${termsDesk.chosen.has(g.id)?'checked':''}><strong>${esc(g.preferred)}</strong></label><span>${labels[g.relation]} · ${total} 处</span></header><div class="term-fields"><label>统一为<input data-term-preferred="${g.id}" value="${esc(g.preferred)}" maxlength="120" ${g.relation!=='same'?'readonly':''}></label><label>译词<input data-term-target="${g.id}" value="${esc(g.target)}" maxlength="160"></label></div><p>${esc(g.note)}</p><details><summary>原文写法与位置 · ${g.variants.length} 种</summary>${g.variants.map(v=>`<div class="term-variant"><strong>${esc(v.text)}</strong><span>${v.count} 处</span>${v.locations.slice(0,8).map((loc,i)=>`<button type="button" class="text-button" data-term-location="${g.id}:${g.variants.indexOf(v)}:${i}" title="${esc(loc.context)}">${esc(loc.file)}:${loc.line}</button>`).join('')}</div>`).join('')}</details>${g.relation!=='same'?'<p class="term-caution">可导入术语表；全称、缩写和相关概念保留各自写法。</p>':''}</article>`;
 }).join('')||'<p class="terms-empty">尚未提取术语。</p>';
 termsControls();
}
async function termsSearchSelected(){
 const targets=[...glossarySelection].filter(t=>glossaryData.terms.includes(t)).map(t=>({...t}));
 if(!targets.length)throw new Error('请先在术语表中勾选要检索的术语。');
 if(targets.length>100)throw new Error('每次最多检索 100 个术语，请分批选择。');
 await termsExtract(targets);
}
async function termsExtract(targets=null){
 const project=state.projectId;await saveAll();reviewGuard(project);await reviewLoadGlossary();reviewGuard(project);
 if(termsDesk.busy)return;termsDesk.project=project;termsDesk.busy=true;termsDesk.action='extract';termsDesk.job=null;termsShow();$('#termsReport').hidden=true;$('#termsPlan').hidden=true;termsMessage('正在阅读全文，提取重要术语…');termsControls();
 try{
  let job=await api('ai/start',{task:'terms',provider:'deepseek',...(targets?{termTargets:targets}:{})});termsDesk.job=job;termsControls();
  while(job.running){await new Promise(resolve=>setTimeout(resolve,500));reviewGuard(project);job=await api('ai/job?id='+encodeURIComponent(job.id));termsDesk.job=job;}
  reviewGuard(project);if(!job.success){if(job.stage==='已停止'){termsMessage('已停止提取，原有术语和文档未改动。');return;}throw new Error(job.error||'提取未完成');}
  termsDesk.result={...job.result,id:job.result.termContext,applied:false};termsDesk.chosen=new Set(targets?job.result.groups.filter(g=>g.relation==='same'&&g.variants.length).map(g=>g.id):[]);termsDesk.plan=null;$('#termsPlan').replaceChildren();$('#termsShow').hidden=false;termsRender();
  termsMessage(`${job.result.groups.length} 组术语 · 可修改“统一为”，勾选后直接点击“统一替换并编译”；也可先预览修改。`);
 }finally{termsDesk.busy=false;termsDesk.job=null;$('#termsReport').hidden=false;$('#termsPlan').hidden=false;termsControls();}
}
async function termsReplace(){
 if(termsDesk.busy)return;
 await termsPreview();if(termsDesk.plan?.count)await termsApply();
}
async function termsPreview(){
 termsGuard();const choices=[...termsDesk.chosen].filter(id=>termsDesk.result.groups[id].relation==='same').map(id=>({id,preferred:termsDesk.result.groups[id].preferred}));
 if(!choices.length)throw new Error('请勾选至少一组同义写法；缩写和相关概念不会自动合并。');
 termsDesk.busy=true;termsDesk.action='local';termsControls();
 try{const plan=await api('review/terms-plan',{id:termsDesk.result.id,choices});termsDesk.plan=plan;termsRenderPlan();termsMessage(plan.count?`${plan.count} 处修改，涉及 ${plan.changes.length} 个文件 · 审阅后应用。`:plan.skipped?.length?'只发现定义或别名说明，已保留原文，无需替换。':'所选术语已经统一，无需修改。');}
 finally{termsDesk.busy=false;termsControls();}
}
function termsRenderPlan(){
 $('#termsPlan').innerHTML=termsDesk.plan?.changes.map(c=>`<details class="term-plan-file" open><summary>${esc(c.path)} · ${c.edits.length} 处</summary>${c.edits.map(e=>`<div class="term-change"><del>${esc(e.before)}</del><span>→</span><ins>${esc(e.after)}</ins><button type="button" class="text-button" data-term-plan-location="${esc(c.path)}" data-term-plan-line="${c.before.slice(0,e.start).split('\n').length}">查看上下文</button></div>`).join('')}</details>`).join('')||'';
 if(termsDesk.plan?.skipped?.length)$('#termsPlan').insertAdjacentHTML('beforeend','<details class="term-plan-file"><summary>保留定义或别名说明 · '+termsDesk.plan.skipped.length+' 处</summary>'+termsDesk.plan.skipped.map(i=>'<p>'+esc(i.file)+':'+i.line+' · '+esc(i.before)+' — '+esc(i.reason)+'</p>').join('')+'</details>');
}
async function termsApply(undo=false){
 termsGuard();termsDesk.busy=true;termsDesk.action='local';termsControls();
 try{
  const project=state.projectId,res=await api('review/terms-'+(undo?'undo':'apply'),{id:termsDesk.result.id,plan:termsDesk.plan.id});reviewGuard(project);
  for(const path of res.files){const info=models.get(path);if(!info?.model)continue;const f=await api('file?path='+encodeURIComponent(path));info.model.pushEditOperations([],[{range:info.model.getFullModelRange(),text:f.content}],()=>null);info.revision=f.revision;info.dirty=false;}
  renderTabs();renderOutline();setSaveStatus('所有更改已保存');termsDesk.result.applied=!undo;
  termsMessage(undo?'已撤销术语统一，正在重新编译。':'已统一所选术语并保存，正在重新编译。');await compile();termsDesk.compiling={undo};if(res.warnings?.length)termsMessage(res.warnings.join('；'),true);
 }finally{termsDesk.busy=false;termsControls();}
}
async function termsImport(){
 reviewGuard(termsDesk.project);if(!termsDesk.chosen.size)throw new Error('请先勾选需要导入的术语。');
 const merged=new Map(glossaryData.terms.map(t=>[t.source.toLocaleLowerCase(),t]));let added=0,kept=0;
 for(const id of termsDesk.chosen){const g=termsDesk.result.groups[id];if(!g.target.trim())throw new Error('请填写“'+g.preferred+'”的译词后导入。');if(merged.has(g.preferred.toLocaleLowerCase())){kept++;continue;}merged.set(g.preferred.toLocaleLowerCase(),{source:g.preferred,target:g.target,note:g.note});added++;}
 if(merged.size>200)throw new Error('合并后超过 200 条，请减少选择。');
 termsDesk.busy=true;termsDesk.action='local';termsControls();
 try{const saved=await api('review/glossary',{terms:[...merged.values()],revision:glossaryData.revision});reviewGuard(termsDesk.project);glossaryData=saved;glossaryDirty=false;glossaryRender();termsMessage(`已导入并保存 ${added} 条，保留已有 ${kept} 条。`);toast('术语表已保存');}finally{termsDesk.busy=false;termsControls();}
}
function termsInstall(){
 $('#glossaryImport').insertAdjacentHTML('beforebegin','<button type="button" id="termsShow" class="secondary" hidden>查看提取结果</button>');
 $('#review-glossary>.review-card').insertAdjacentHTML('beforebegin','<section id="termsDesk" hidden><div class="terms-toolbar"><button id="termsSelectAll" class="secondary">全选条目</button><button id="termsPreview" class="secondary">预览统一修改</button><button id="termsImport" class="secondary">导入所选术语</button><button id="termsStop" class="secondary" hidden>停止</button></div><p id="termsStatus" class="terms-status" role="status">尚未提取</p><div id="termsPlan"></div><div id="termsReport"></div><footer class="terms-footer"><button id="termsApply" class="primary" disabled>应用修改并编译</button><button id="termsUndo" class="secondary" hidden>撤销统一</button></footer></section>');
 $('#termsApply').textContent='统一替换并编译';
 $('#termsExtract').onclick=termsWatch(()=>termsExtract());$('#termsSearchSelected').onclick=termsWatch(termsSearchSelected);$('#termsShow').onclick=()=>termsShow($('#termsDesk').hidden);
 $('#termsPreview').onclick=termsWatch(termsPreview);$('#termsApply').onclick=termsWatch(termsReplace);$('#termsUndo').onclick=termsWatch(()=>termsApply(true));$('#termsImport').onclick=termsWatch(termsImport);
 $('#termsStop').onclick=termsWatch(termsStop);
 $('#termsSelectAll').onclick=()=>{termsDesk.chosen=new Set(termsDesk.chosen.size===termsDesk.result.groups.length?[]:termsDesk.result.groups.map(g=>g.id));if(!termsDesk.result.applied){termsDesk.plan=null;$('#termsPlan').replaceChildren();}termsRender();};
 $('#termsReport').onchange=e=>{const check=e.target.closest('[data-term-choice]');if(check){const id=Number(check.dataset.termChoice);check.checked?termsDesk.chosen.add(id):termsDesk.chosen.delete(id);}if(!termsDesk.result?.applied){termsDesk.plan=null;$('#termsPlan').replaceChildren();}termsControls();};
 $('#termsReport').oninput=e=>{const field=e.target.closest('[data-term-preferred],[data-term-target]');if(!field)return;const id=Number(field.dataset.termPreferred??field.dataset.termTarget),key=field.hasAttribute('data-term-preferred')?'preferred':'target';termsDesk.result.groups[id][key]=field.value;if(key==='preferred'&&!termsDesk.result.applied){termsDesk.plan=null;$('#termsPlan').replaceChildren();}termsControls();};
 $('#termsDesk').onclick=termsWatch(async e=>{const loc=e.target.closest('[data-term-location]'),plan=e.target.closest('[data-term-plan-location]');if(loc){reviewGuard(termsDesk.project);const [g,v,i]=loc.dataset.termLocation.split(':').map(Number);await studioLocateSource(termsDesk.result.groups[g].variants[v].locations[i]);}if(plan)await studioLocateSource({file:plan.dataset.termPlanLocation,line:Number(plan.dataset.termPlanLine)});});
 const old=editorToolOpen;editorToolOpen=async function(tool){await old(tool);if(tool!=='glossary')return;if(termsDesk.project!==state.projectId){termsDesk.project=state.projectId;termsDesk.result=null;termsDesk.plan=null;termsDesk.chosen.clear();termsShow(false);$('#termsShow').hidden=true;const project=state.projectId,result=await api('review/terms');reviewGuard(project);if(result.id){termsDesk.result=result;termsDesk.plan=result.plan||null;$('#termsShow').hidden=false;termsRender();termsRenderPlan();termsMessage(result.applied?'上次统一已应用，可撤销或导入术语表。':'已恢复上次提取结果。');}}};
 // Existing buttons retain their original closure, so delegate glossary entry here.
 $$('[data-editor-tool="glossary"]').forEach(b=>b.onclick=reviewWatch(()=>editorToolOpen('glossary')));
 termsControls();
}
termsInstall();
const termsNotifyState=hubNotifyState;hubNotifyState=function(next){termsNotifyState(next);if(termsDesk.compiling&&!next.running){const undo=termsDesk.compiling.undo;termsDesk.compiling=null;termsMessage((undo?'已撤销术语统一':'已统一所选术语')+(next.success?' · 编译成功':' · 编译未通过，请查看编辑器日志'),!next.success);}termsControls();};
