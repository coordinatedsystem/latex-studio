'use strict';
let reviewTool='assistant',layoutReport=null,layoutSelection=new Set(),layoutCurrent=1,referenceReport=null;
let glossaryData=null,glossaryProject='',glossaryDirty=false,glossaryRemoved=[],reviewRemote=null,reviewRemoteTimer=null,reviewRemotePolling=false,reviewRemoteStarting=false;
function reviewError(message=''){$('#reviewError').hidden=!message;$('#reviewError').textContent=message;}
function reviewGuard(project){if(project!==state?.projectId)throw new Error('项目已切换，请重新载入检查结果。');}
function reviewWatch(fn){return async(...args)=>{try{reviewError();await fn(...args);}catch(e){reviewError(e.message);}};}
function reviewShow(tool){
 if(['layout','pageedit'].includes(tool))tool='assistant';
 if(['references','glossary','tests'].includes(tool)&&typeof editorToolOpen==='function'){reviewWatch(()=>editorToolOpen(tool))();return;}
 reviewTool=tool;$('#aiPage').dataset.tool=tool;$('.ai-layout').hidden=true;$('#reviewWorkbench').hidden=tool==='assistant';if($('#writingWorkbench'))$('#writingWorkbench').hidden=tool!=='assistant';
 $$('.review-tabs button').forEach(b=>{const on=b.dataset.reviewTool===tool;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
 $$('.review-tool').forEach(el=>el.hidden=el.id!=='review-'+tool);reviewError();
 if(tool==='glossary')reviewWatch(reviewLoadGlossary)();
 if(tool==='tests')reviewWatch(reviewHealth)();
 if(tool==='layout'&&layoutReport&&layoutReport.projectId!==state?.projectId){layoutReport=null;layoutSelection.clear();$('#layoutPageList').textContent='项目已切换，请重新检查 PDF。';$('#layoutPreview').replaceChildren();$('#layoutIssues').replaceChildren();$('#visionResults').replaceChildren();}
 if(tool==='references'&&referenceReport&&referenceReport.projectId!==state?.projectId){referenceReport=null;$('#referenceIssues').textContent='项目已切换，请重新检查引用。';}
}
function reviewStat(value,label){return `<div><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;}
async function layoutScan(){
 const button=$('#layoutScan'),project=state?.projectId;button.disabled=true;button.textContent='正在本地解析…';
 try{const result=await api('review/layout',{pages:$('#layoutPages').value.trim()||'all'});reviewGuard(project);layoutReport=result;layoutSelection=new Set([result.pages[0].page]);layoutCurrent=result.pages[0].page;
 $('#layoutStats').innerHTML=reviewStat(result.scannedPages+'/'+result.totalPages,'已检查页面')+reviewStat(result.issues.filter(i=>i.severity==='warning').length,'需确认')+reviewStat(result.issues.filter(i=>i.severity==='info').length,'信息线索')+reviewStat('本地','未发送文档');
 $('#layoutVersion').textContent='当前编译结果';$('#layoutNote').textContent=result.note+(result.truncated?' 本次仅扫描前 200 页。':'');$('#visionResults').replaceChildren();layoutRenderPages();layoutShowPage(layoutCurrent);
 }finally{button.disabled=false;button.textContent='检查当前 PDF';}
}
function layoutRenderPages(){
 $('#layoutPageList').innerHTML=layoutReport.pages.map(p=>`<div class="layout-page ${p.page===layoutCurrent?'active':''}"><label><input type="checkbox" data-layout-select="${p.page}" ${layoutSelection.has(p.page)?'checked':''} aria-label="选择 PDF 第 ${p.page} 页进行视觉审阅"></label><button data-layout-page="${p.page}"><span class="layout-page-number">${p.page}</span><div><strong>第 ${p.page} 页</strong><small>${p.issues.length?p.issues.length+' 条线索':'未发现规则提示'} · ${p.characters} 字符</small></div><span class="layout-page-dot ${p.issues.some(i=>i.severity==='warning')?'warning':''}"></span></button></div>`).join('');
 $('#visionSelection').textContent='已选择 '+layoutSelection.size+' / 3 页'+(layoutSelection.size?'：'+[...layoutSelection].sort((a,b)=>a-b).join('、'):'');
}
function layoutShowPage(page){
 reviewGuard(layoutReport.projectId);layoutCurrent=page;layoutRenderPages();$('#layoutPreviewTitle').textContent='第 '+page+' 页';
 const url='/api/review/page?page='+page+'&version='+encodeURIComponent(layoutReport.pdfVersion)+'&project='+encodeURIComponent(layoutReport.projectId);
 $('#layoutPreview').innerHTML=`<img src="${url}" alt="PDF 第 ${page} 页的实际渲染预览"><div id="layoutBox" class="layout-box" hidden></div>`;
 $('#layoutPreview img').onerror=()=>reviewError('页面预览未能载入；PDF 可能已更新，请重新检查。');
 const issues=layoutReport.pages.find(p=>p.page===page).issues;
 $('#layoutIssues').innerHTML=issues.length?issues.map((i,n)=>`<button data-layout-issue="${n}" class="review-issue ${esc(i.severity)}"><span class="review-severity">${i.severity==='warning'?'!':'i'}</span><div><strong>第 ${page} 页</strong><p>${esc(i.message)}</p></div></button>`).join(''):'<p class="review-clear">此页未触发本地检查规则。可继续人工查看，或进行 AI 视觉审阅。</p>';
}
async function reviewOpenPdf(){if(!layoutReport)return;reviewGuard(layoutReport.projectId);hubView('editor');await setPdf(state.pdfVersion,true,false,layoutCurrent);}
async function referencesScan(){
 const button=$('#referencesScan'),project=state?.projectId;button.disabled=true;button.textContent='正在追踪文件…';
 try{const sources={};for(const [path,info] of models)if(info.model&&/\.(tex|bib)$/i.test(path))sources[path]=info.model.getValue();
 referenceReport=await api('review/references',{sources});reviewGuard(project);
 $('#referenceStats').innerHTML=reviewStat(referenceReport.files.length,'追踪文件')+reviewStat(referenceReport.labels,'标签定义')+reviewStat(referenceReport.references,'交叉引用')+reviewStat(referenceReport.bibliography,'文献条目');
 $('#referenceNote').textContent=referenceReport.note;$('#referencesCopy').disabled=false;$('#referenceFiles').hidden=false;$('#referenceFiles>div').innerHTML=referenceReport.files.map(f=>`<button data-reference-file="${esc(f)}">${icon('file')} ${esc(f)}</button>`).join('');referencesRender();
 }finally{button.disabled=false;button.textContent='检查当前项目';}
}
function referencesRender(){
 if(!referenceReport)return;const severity=$('#referenceSeverity').value,query=$('#referenceQuery').value.toLocaleLowerCase();
 const issues=referenceReport.issues.filter(i=>(severity==='all'||i.severity===severity)&&[i.file,i.message].join(' ').toLocaleLowerCase().includes(query));
 $('#referenceIssues').innerHTML=issues.length?issues.map(i=>`<button class="review-issue ${esc(i.severity)}" data-reference-file="${esc(i.file)}" data-reference-line="${i.line}"><span class="review-severity">${i.severity==='error'?'!':i.severity==='warning'?'?':'i'}</span><div><strong>${esc(i.file)}:${i.line}</strong><p>${esc(i.message)}</p></div><span>↗</span></button>`).join(''):`<div class="review-success-mark">✓</div><p class="review-clear">${referenceReport.issues.length?'当前筛选条件下没有提示。':'没有发现可静态识别的引用问题。'}</p>`;
}
async function reviewLoadGlossary(force=false){
 if(glossaryData&&glossaryProject===state?.projectId&&!force)return;
 if(glossaryDirty){if(glossaryProject!==state?.projectId)throw new Error('上一个项目的术语改动尚未保存；请先复制 TSV 保留，或切回原项目保存。');if(!await confirmDialog('重新载入术语表','未保存的术语改动将被磁盘版本替换。','重新载入'))return;}
 const project=state?.projectId,result=await api('review/glossary');reviewGuard(project);glossaryData=result;glossaryProject=project;glossaryDirty=false;glossaryRemoved=[];glossaryRender();
}
function glossaryRender(){
 const query=$('#glossaryQuery').value.toLocaleLowerCase();
 $('#glossaryRows').innerHTML=(glossaryData?.terms||[]).map((t,i)=>({t,i})).filter(({t})=>Object.values(t).join(' ').toLocaleLowerCase().includes(query)).map(({t,i})=>`<tr data-term-row="${i}">${['source','target','note'].map((key,j)=>`<td><input data-term-index="${i}" data-term-field="${key}" aria-label="术语 ${i+1} 的${['原词','译词','备注'][j]}" value="${esc(t[key])}" maxlength="${[120,160,300][j]}" placeholder="${['例如：反向传播','backpropagation','可选说明'][j]}"></td>`).join('')}<td><button class="tiny" data-term-remove="${i}" aria-label="移除术语 ${i+1}" title="移除术语，可撤销">${icon('close')}</button></td></tr>`).join('')||'<tr><td colspan="4" class="review-placeholder">暂无匹配术语。点击「添加术语」开始。</td></tr>';
 glossaryStatus();
}
function glossaryStatus(){$('#glossaryStatus').textContent=(glossaryData?.terms.length||0)+' / 200 条'+(glossaryDirty?' · 尚未保存':' · 已载入');$('#glossaryUndo').disabled=!glossaryRemoved.length;}
async function glossarySave(){reviewGuard(glossaryProject);const b=$('#glossarySave');b.disabled=true;try{glossaryData=await api('review/glossary',glossaryData);glossaryDirty=false;glossaryRender();$('#glossaryStatus').textContent=glossaryData.terms.length+' 条 · 已保存';toast('项目术语表已保存');}finally{b.disabled=false;}}
async function glossaryExport(){if(!glossaryData)await reviewLoadGlossary();const tsv=['原词\t译词\t备注',...glossaryData.terms.map(t=>[t.source,t.target,t.note].join('\t'))].join('\n');await navigator.clipboard.writeText(tsv);toast('术语表 TSV 已复制');}
function parseGlossaryTsv(text){const lines=text.trim().split(/\r?\n/);if(/^(原词|source)\t/i.test(lines[0]||''))lines.shift();return lines.filter(l=>l.trim()).map((line,i)=>{const parts=line.split('\t');if(parts.length<2||!parts[0].trim()||!parts[1].trim())throw new Error('第 '+(i+1)+' 行缺少原词或译词，请使用制表符分隔');return {source:parts[0].trim(),target:parts[1].trim(),note:(parts[2]||'').trim()};});}
function glossaryImport(){
 modal('导入术语 TSV','<p>每行一个术语，原词、译词、备注之间用制表符分隔；最多 200 条。</p><textarea id="glossaryImportText" class="glossary-import-text" rows="9" aria-label="TSV 术语文本" placeholder="反向传播&#9;backpropagation&#9;神经网络"></textarea><label class="glossary-import-mode">遇到相同原词<select id="glossaryImportMode"><option value="keep">保留已有术语</option><option value="replace">替换为导入内容</option></select></label><p id="glossaryImportError" class="review-error" hidden></p><div class="dialog-actions"><button type="button" id="glossaryImportApply" class="primary">合并到当前术语表</button></div>');
 $('#glossaryImportApply').onclick=()=>{try{reviewGuard(glossaryProject);const incoming=parseGlossaryTsv($('#glossaryImportText').value),merged=new Map(glossaryData.terms.map(t=>[t.source.toLocaleLowerCase(),t]));for(const t of incoming)if(!merged.has(t.source.toLocaleLowerCase())||$('#glossaryImportMode').value==='replace')merged.set(t.source.toLocaleLowerCase(),t);if(merged.size>200)throw new Error('合并后超过 200 条，请减少导入数量');glossaryData.terms=[...merged.values()];glossaryDirty=true;$('#modal').close();glossaryRender();toast('已合并 '+incoming.length+' 行，请保存术语表');}catch(e){$('#glossaryImportError').hidden=false;$('#glossaryImportError').textContent=e.message;}};
}
async function reviewHealth(){
 const health=await api('review/health');
 $('#reviewHealth').innerHTML=[['本地文档检查',health.pdfAnalysis&&health.pageRendering,'PDF 解析与页面渲染',null],['DeepSeek',health.providers.deepseek.configured,'纠错与视觉审阅使用当前模型配置','deepseek'],['有道翻译',health.providers.youdao.configured,'词典另需服务权限','youdao']].map(([name,ready,desc,provider])=>`<article class="review-card"><span class="review-test-symbol ${ready?'ready':''}">${provider?'✦':'✓'}</span><h3>${name}</h3><span class="state-badge ${ready?'success':'warning'}">${ready?(provider?'密钥已配置':'环境就绪'):(provider?'未配置密钥':'环境不完整')}</span><p>${desc}</p>${provider?`<button data-probe-provider="${provider}" class="secondary" ${!ready?'disabled':''}>使用独立示例测试</button>`:'<p class="review-muted">本地自检与线上测试分别记录</p>'}</article>`).join('');
}
async function reviewSelftest(){const b=$('#reviewSelftest');b.disabled=true;try{const r=await api('review/selftest',{});$('#selftestResults').innerHTML=`<p class="review-test-summary">${r.passed} / ${r.total} 项通过 <span>${esc(r.time)}</span></p><div class="selftest-grid">${r.checks.map(c=>`<div class="${c.passed?'passed':'failed'}"><span>${c.passed?'✓':'!'}</span>${esc(c.name)}</div>`).join('')}</div><p class="review-footnote">${esc(r.note)}</p>`;}finally{b.disabled=false;}}
async function reviewStartRemote(kind,provider){
 if(reviewRemote?.running||reviewRemoteStarting)throw new Error('已有线上测试或视觉审阅正在运行');
 let payload={task:'probe',provider};let snapshot={projectId:state?.projectId,kind};
 if(kind==='vision'){
  if(!layoutReport||!layoutSelection.size)throw new Error('请先检查 PDF，并选择 1～3 页');reviewGuard(layoutReport.projectId);
  payload={task:'layout',provider:'deepseek',pdfVersion:layoutReport.pdfVersion,pages:[...layoutSelection].sort((a,b)=>a-b).join(',')};snapshot.pdfVersion=layoutReport.pdfVersion;
 }
 const target=kind==='vision'?'#visionStatus':'#probeResults';$(target).textContent=kind==='vision'?'正在准备所选页面…':'正在测试独立示例…';
 $('#visionStart').disabled=true;$$('[data-probe-provider]').forEach(b=>b.disabled=true);
 reviewRemoteStarting=true;
 try{const job=await api('ai/start',payload);reviewRemote={...snapshot,...job};clearInterval(reviewRemoteTimer);reviewRemoteTimer=setInterval(reviewRemotePoll,650);await reviewRemotePoll();}
 catch(e){$(target).textContent=e.message;throw e;}
 finally{reviewRemoteStarting=false;if(!reviewRemote?.running){$('#visionStart').disabled=false;await reviewHealth();}}
}
async function reviewRemotePoll(){
 if(reviewRemotePolling||!reviewRemote?.id)return;reviewRemotePolling=true;
 try{reviewGuard(reviewRemote.projectId);const job=await api('ai/job?id='+encodeURIComponent(reviewRemote.id));if(!job.id){reviewRemote.running=false;throw new Error('任务已失效，请重新测试');}reviewError();reviewRemote={...reviewRemote,...job};
 const vision=reviewRemote.kind==='vision';$('#visionStop').hidden=!vision||!job.running;$('#probeStop').hidden=vision||!job.running;
 if(job.running){$(vision?'#visionStatus':'#probeResults').textContent=job.stage+' · '+Math.max(0,Math.floor(Date.now()/1000-job.started))+'s';return;}
 clearInterval(reviewRemoteTimer);$('#visionStart').disabled=false;$('#visionStop').hidden=true;$('#probeStop').hidden=true;
 if(!job.success)throw new Error(job.error||'线上请求未完成');
 if(vision){$('#visionStatus').textContent='视觉审阅完成 · '+job.duration+'s';const result=job.result;$('#visionResults').innerHTML=`<p class="review-vision-summary">${esc(result.summary)}</p>`+(result.issues.map(i=>`<button class="review-issue ${esc(i.severity)}" data-vision-page="${i.page}"><span class="review-severity">✦</span><div><strong>第 ${i.page} 页</strong><p>${esc(i.message)}</p>${i.evidence?`<small>依据：${esc(i.evidence)}</small>`:''}${i.suggestion?`<small>建议：${esc(i.suggestion)}</small>`:''}</div><span>↗</span></button>`).join('')||'<p class="review-clear">本次 AI 未提出具体问题，请继续人工确认。</p>')+(typeof pageEditLinks==='function'?pageEditLinks(result):'');}
 else{$('#probeResults').innerHTML=`<div class="review-probe-success"><span>✓</span><div><h3>${esc(job.provider==='deepseek'?'DeepSeek':'有道翻译')} · 接口与响应格式正常</h3><p>${job.duration}s${job.result.usage?.total_tokens?' · '+job.result.usage.total_tokens+' tokens':''}</p><pre>${esc(job.result.sampleOutput||'')}</pre>${job.provider==='deepseek'?`<p>预设错字修复：${job.result.sampleCorrected?'已识别并修复':'未修复，请检查模型输出'}</p>`:''}<p class="review-footnote">测试使用内置示例；不代表所有任务质量，也未测试有道词典权限。</p></div></div>`;}
 await reviewHealth();
 }catch(e){reviewError(e.message);if(reviewRemote?.running&&reviewRemote.projectId===state?.projectId){$(reviewRemote.kind==='vision'?'#visionStatus':'#probeResults').textContent='状态读取失败，正在重试；可以点击停止。';}else{clearInterval(reviewRemoteTimer);if(reviewRemote)reviewRemote.running=false;$('#visionStart').disabled=false;$('#visionStop').hidden=true;$('#probeStop').hidden=true;await reviewHealth().catch(()=>{});}}
 finally{reviewRemotePolling=false;}
}
async function reviewStopRemote(){if(reviewRemote?.id){await api('ai/cancel',{id:reviewRemote.id});$('#visionStatus').textContent='正在停止；本次响应将丢弃。';}}
$$('[data-review-tool]').forEach(b=>b.onclick=()=>reviewShow(b.dataset.reviewTool));
$('#layoutScan').onclick=reviewWatch(layoutScan);$('#layoutOpenPdf').onclick=reviewWatch(reviewOpenPdf);
$('#layoutPageList').onclick=reviewWatch(async e=>{const b=e.target.closest('[data-layout-page]');if(b)layoutShowPage(Number(b.dataset.layoutPage));});
$('#layoutPageList').onchange=reviewWatch(async e=>{const input=e.target.closest('[data-layout-select]');if(!input)return;reviewGuard(layoutReport.projectId);const n=Number(input.dataset.layoutSelect);if(input.checked){if(layoutSelection.size>=3){input.checked=false;throw new Error('视觉审阅一次最多选择 3 页');}layoutSelection.add(n);}else layoutSelection.delete(n);layoutRenderPages();});
$('#layoutIssues').onclick=reviewWatch(async e=>{const b=e.target.closest('[data-layout-issue]');if(!b)return;const issue=layoutReport.pages.find(p=>p.page===layoutCurrent).issues[Number(b.dataset.layoutIssue)];const box=$('#layoutBox');box.hidden=!issue.bbox;if(issue.bbox){const [a,t,c,d]=issue.bbox;box.style.left=Math.max(0,a)*100+'%';box.style.top=Math.max(0,t)*100+'%';box.style.width=Math.max(.01,Math.min(1,c)-Math.max(0,a))*100+'%';box.style.height=Math.max(.01,Math.min(1,d)-Math.max(0,t))*100+'%';}});
$('#visionStart').onclick=reviewWatch(()=>reviewStartRemote('vision','deepseek'));$('#visionStop').onclick=reviewWatch(reviewStopRemote);$('#probeStop').onclick=reviewWatch(reviewStopRemote);
$('#visionResults').onclick=reviewWatch(async e=>{const modify=e.target.closest('[data-page-modify]');if(modify){const page=Number(modify.dataset.pageModify),notes=(reviewRemote?.result?.issues||[]).filter(i=>i.page===page).map(i=>i.message+'；'+i.suggestion).join('\n').slice(0,1600);await pageEditOpen(page,notes);return;}const b=e.target.closest('[data-vision-page]');if(b&&reviewRemote.pdfVersion===layoutReport.pdfVersion)layoutShowPage(Number(b.dataset.visionPage));});
$('#referencesScan').onclick=reviewWatch(referencesScan);$('#referenceSeverity').onchange=referencesRender;$('#referenceQuery').oninput=referencesRender;
async function referenceOpen(e){const b=e.target.closest('[data-reference-file]');if(b){reviewGuard(referenceReport.projectId);await openFile(b.dataset.referenceFile,Number(b.dataset.referenceLine||1));hubView('editor');}}
$('#referenceIssues').onclick=reviewWatch(referenceOpen);$('#referenceFiles').onclick=reviewWatch(referenceOpen);$('#referencesCopy').onclick=reviewWatch(async()=>{reviewGuard(referenceReport.projectId);await navigator.clipboard.writeText(JSON.stringify(referenceReport,null,2));toast('引用检查结果已复制');});
$('#glossaryQuery').oninput=glossaryRender;$('#glossarySave').onclick=reviewWatch(glossarySave);$('#glossaryReload').onclick=reviewWatch(()=>reviewLoadGlossary(true));$('#glossaryExport').onclick=reviewWatch(glossaryExport);$('#glossaryImport').onclick=glossaryImport;
$('#glossaryAdd').onclick=reviewWatch(async()=>{reviewGuard(glossaryProject);if(glossaryData.terms.length>=200)throw new Error('已达到 200 条上限');$('#glossaryQuery').value='';glossaryData.terms.push({source:'',target:'',note:''});glossaryDirty=true;glossaryRender();$('#glossaryRows tr:last-child input')?.focus();});
$('#glossaryRows').oninput=e=>{const input=e.target.closest('[data-term-field]');if(input){glossaryData.terms[Number(input.dataset.termIndex)][input.dataset.termField]=input.value;glossaryDirty=true;glossaryStatus();}};
$('#glossaryRows').onclick=e=>{const b=e.target.closest('[data-term-remove]');if(b){const index=Number(b.dataset.termRemove),term=glossaryData.terms.splice(index,1)[0];glossaryRemoved.push({index,term});glossaryDirty=true;glossaryRender();}};
$('#glossaryUndo').onclick=()=>{const item=glossaryRemoved.pop();if(item){glossaryData.terms.splice(item.index,0,item.term);glossaryDirty=true;glossaryRender();}};
$('#reviewSelftest').onclick=reviewWatch(reviewSelftest);$('#reviewHealthRefresh').onclick=reviewWatch(reviewHealth);$('#reviewHealth').onclick=reviewWatch(async e=>{const b=e.target.closest('[data-probe-provider]');if(b)await reviewStartRemote('probe',b.dataset.probeProvider);});
window.addEventListener('beforeunload',e=>{if(glossaryDirty){e.preventDefault();e.returnValue='';}});
