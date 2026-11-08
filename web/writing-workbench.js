'use strict';
// One explicit suggestion -> temporary preview -> apply transaction for both inputs.
const writing={mode:'pdf',view:'content',page:1,pages:new Set([1]),selectionMode:'single',comparePage:null,doc:null,project:null,context:null,result:null,selected:new Set(),preview:null,job:null,busy:false,applied:false,stale:false,step:0,ticket:0,file:null,full:'',range:null,localIssues:[],polling:false};
let writingEditor=null,writingModel=null,writingDecorations=[],writingDiffEditor=null,writingDiffModels=[],writingTimer=null,writingOpening=false,writingDocumentBusy=false,writingStateVersion=null;
function writingError(message=''){$('#writingError').hidden=!message;$('#writingError').textContent=message;}
function writingStatus(text){$('#writingStatus').textContent=text;}
function writingWatch(fn){return async(...args)=>{try{writingError();await fn(...args);}catch(e){writingError(e.message);writingControls();}};}
function writingClean(){if([...models.values()].some(i=>i.model&&i.dirty))throw new Error('请先保存并编译，再获取建议或应用修改。');}
function writingGuard(){if(!writing.context||writing.context.projectId!==state?.projectId||writing.stale)throw new Error('内容已更新，请重新选择并获取建议。');}
function writingSamePreview(){return !!writing.preview?.success&&JSON.stringify(writing.preview.selected)===JSON.stringify([...writing.selected].sort((a,b)=>a-b));}
function writingStep(step){writing.step=step;$$('[data-writing-step]').forEach(el=>{const n=Number(el.dataset.writingStep);el.classList.toggle('current',n===step);el.classList.toggle('done',n<step);el.setAttribute('aria-current',n===step?'step':'false');});}
function writingControls(){
 const locked=writing.busy||!!state?.running||!!state?.packageBusy;
 $$('[data-writing-mode]').forEach(b=>{b.disabled=locked;b.classList.toggle('active',b.dataset.writingMode===writing.mode);b.setAttribute('aria-pressed',String(b.dataset.writingMode===writing.mode));});
 for(const id of ['writingTask','writingProvider','writingInstruction','writingLanguage','writingFile','writingReadSource','writingSelectFile','writingPage','writingLocalCheck','writingRestore','writingThumbnailsToggle','writingLineStart','writingLineEnd','writingChooseLines','writingSelectionMode','writingPageRange','writingChoosePages','writingClearPages'])$('#'+id).disabled=locked;
 $$('[data-writing-page-select]').forEach(el=>el.disabled=locked);
 $('#writingCompile').disabled=locked;$('#writingEmptyCompile').disabled=locked;
 $('#writingPrevious').disabled=locked||writing.page<=1;$('#writingNext').disabled=locked||writing.page>=(writing.doc?.totalPages||0);
 $('#writingSuggest').disabled=locked||writing.applied||!(writing.mode==='pdf'?writing.doc?.totalPages&&writing.pages.size:writing.range?.end>writing.range?.start);
 $('#writingSuggest').textContent=writing.busy?'正在处理…':$('#writingTask').value==='check'?'检查所选内容':'✦ 获取修改建议'+(writing.mode==='pdf'&&writing.pages.size>1?' · '+writing.pages.size+' 页':'');
 $('#writingStop').hidden=!writing.job?.running;
 $('#writingPreview').disabled=locked||!writing.context||writing.stale||!writing.selected.size||writing.applied;
 $('#writingApply').disabled=locked||!writing.context||writing.stale||!writingSamePreview()||writing.applied;
 $('#writingPreview').hidden=writing.applied;$('#writingApply').hidden=writing.applied;$('#writingContinue').hidden=!writing.applied;$('#writingContinue').disabled=locked;
 $('#writingUndo').hidden=!writing.applied;$('#writingUndo').disabled=locked;
 $('#writingSelectAll').disabled=locked||writing.applied||writing.stale;
 $('#writingSelectAllLabel').hidden=!writing.result?.edits?.length;
 $('#writingSelectAll').checked=!!writing.result?.edits?.length&&writing.selected.size===writing.result.edits.length;
 $('#writingSelectAll').indeterminate=writing.selected.size>0&&writing.selected.size<writing.result?.edits?.length;
 $$('[data-writing-edit]').forEach(e=>e.disabled=locked||writing.applied||writing.stale);
 $$('[data-writing-view]').forEach(b=>{b.disabled=b.dataset.writingView==='comparison'?!writing.preview?.success:b.dataset.writingView==='diff'?!writing.result?.edits?.length:false;b.classList.toggle('active',b.dataset.writingView===writing.view);b.setAttribute('aria-pressed',String(b.dataset.writingView===writing.view));});
 $$('[data-writing-step]').forEach(el=>{el.classList.toggle('locked',Number(el.dataset.writingStep)>writing.step);});
 $('#writingPreview').textContent=writing.preview?.running?'正在编译预览…':'预览所选修改';
 $('#writingApply').textContent=writing.applied?'已应用':'确认应用';
 writingEditor?.updateOptions({readOnly:true});
 if(typeof writingUXControls==='function')writingUXControls();
}
function writingReset(){
 if(typeof writingRemember==='function')writingRemember();
 if(typeof writingClearFocus==='function')writingClearFocus();
 ++writing.ticket;clearInterval(writingTimer);writing.context=null;writing.result=null;writing.preview=null;writing.comparePage=null;writing.job=null;writing.selected.clear();writing.applied=false;writing.stale=false;writing.localIssues=[];
 $('#writingSuggestionCount').textContent='0';$('#writingResults').innerHTML='<div class="writing-result-empty"><span>✦</span><strong>先选择内容，再获取建议</strong></div>';
 writingDisposeDiff();$('.writing-request').classList.remove('compact');$('#writingRequestToggle').hidden=true;$('#writingPdfHighlight').hidden=true;writingError();writingStep(0);writingSetView('content');writingStatus('准备就绪');
}
function writingTaskControls(changed='task'){
 let task=$('#writingTask').value,provider=$('#writingProvider').value;
 if(changed==='provider'){
  if(provider==='local')task='check';else if(provider==='youdao'&&!['translate','dictionary'].includes(task))task='translate';else if(provider==='deepseek'&&['check','dictionary'].includes(task))task='correct';
 }else provider=task==='check'?'local':task==='dictionary'?'youdao':provider==='local'?'deepseek':provider==='youdao'&&task!=='translate'?'deepseek':provider;
 if(writing.mode==='pdf'&&['dictionary','workflow'].includes(task)){task='format';provider='deepseek';}
 if(writing.mode==='pdf'&&provider==='youdao'){provider='deepseek';if(task==='check')task='correct';}
 $('#writingTask').value=task;$('#writingProvider').value=provider;
 for(const option of $('#writingTask').options)option.disabled=writing.mode==='pdf'&&['dictionary','workflow'].includes(option.value);
 $('#writingProvider option[value="youdao"]').disabled=writing.mode==='pdf';
 $('#writingLanguageField').hidden=task!=='translate';
 $('#writingSuggest').title=task==='check'?'本地检查，不调用 AI':writing.mode==='pdf'?'按页处理，所选 '+writing.pages.size+' 页将发起 '+writing.pages.size+' 次 AI 请求':task==='workflow'?'两次 AI 请求；结果仍需预览后确认应用':'发送当前选择，获取建议；不会直接修改文件';
 writingControls();
}
async function writingOpen(useSelection=false){
 if(writingOpening)return;writingOpening=true;
 try{
  if(!state?.projectId){await poll();if(!state?.projectId)throw new Error('项目正在载入，请稍后打开工作区。');}
  if(writing.project!==state?.projectId){writingReset();writing.project=state?.projectId;writing.doc=null;writing.file=null;writing.full='';writing.range=null;writing.pages=new Set([1]);}
  writingPopulateFiles();await writingLoadDocument();
  if(useSelection){await writingSetMode('source');await writingReadSource(true);}else if(writing.mode==='source'&&!writingModel)await writingReadSource();
  writingTaskControls();requestAnimationFrame(()=>{writingEditor?.layout();writingDiffEditor?.layout();});
  if(typeof writingOpened==='function')await writingOpened(useSelection);
 }finally{writingOpening=false;}
}
function writingPopulateFiles(){
 const files=(state?.files||[]).filter(f=>/\.tex$/i.test(f.path));
 const value=writing.file||(files.some(f=>f.path===active)?active:state?.main);
 $('#writingFile').innerHTML=files.map(f=>`<option value="${esc(f.path)}">${esc(f.path)}</option>`).join('');$('#writingFile').value=value||'';
}
async function writingLoadDocument(){
 if(writingDocumentBusy)return;writingDocumentBusy=true;writingStateVersion=String(state?.pdfVersion);
 try{
 const project=state?.projectId,ticket=writing.ticket;
 const info=await api('review/document');if(project!==state?.projectId||ticket!==writing.ticket)return;
 const changed=writing.doc&&writing.doc.pdfVersion!==info.pdfVersion;writing.doc=info;writing.project=info.projectId;
 writing.page=Math.max(1,Math.min(writing.page,info.totalPages||1));$('#writingTotalPages').textContent=info.totalPages||'—';$('#writingPage').max=info.totalPages||1;
 if(info.totalPages)writing.pages=new Set([...writing.pages].filter(p=>p<=info.totalPages));
 $('#writingPdfEmpty').hidden=!!info.totalPages;$('#writingPdfSheet').hidden=!info.totalPages;
 if(info.totalPages){writingShowPage(writing.page);writingRenderThumbnails();}else $('#writingContentState').textContent='尚未编译';
 if(changed&&writing.context&&!writing.applied){writing.stale=true;writingStatus('PDF 已更新，请重新获取建议。');}
 writingControls();
 }finally{writingDocumentBusy=false;}
}
function writingPageUrl(page){return '/api/review/page?page='+page+'&version='+encodeURIComponent(writing.doc.pdfVersion)+'&project='+encodeURIComponent(writing.doc.projectId);}
function writingShowPage(page){
 if(typeof writingClearFocus==='function')writingClearFocus();
 if(!writing.doc?.totalPages)return;writing.page=Math.max(1,Math.min(Number(page)||1,writing.doc.totalPages));$('#writingPage').value=writing.page;
 $('#writingPdfImage').src=writingPageUrl(writing.page);const selected=writing.pages.has(writing.page);$('#writingPdfSheet').classList.toggle('selected',selected);
 $('#writingPdfCaption').textContent=(selected?'已选':'未选')+' · 第 '+writing.page+' 页';$('#writingPdfSelected').textContent=writing.selectionMode==='multiple'?'已选 '+writing.pages.size+' 页':'第 '+writing.page+' 页已选';
 $('#writingPageRange').value=[...writing.pages].sort((a,b)=>a-b).join(',');$('#writingPdfHighlight').hidden=true;
 $$('[data-writing-page]').forEach(b=>{b.classList.toggle('selected',writing.pages.has(Number(b.dataset.writingPage)));b.classList.toggle('current',Number(b.dataset.writingPage)===writing.page);b.setAttribute('aria-pressed',String(writing.pages.has(Number(b.dataset.writingPage))));});
 $$('[data-writing-page-select]').forEach(el=>el.checked=writing.pages.has(Number(el.dataset.writingPageSelect)));
 if(writing.mode==='pdf')$('#writingTargetLabel').textContent='PDF · 已选 '+[...writing.pages].sort((a,b)=>a-b).join('、')+' 页';writingTaskControls();
 if(typeof writingWorkspaceSave==='function')writingWorkspaceSave();
}
function writingRenderThumbnails(){
 $('#writingThumbnails').innerHTML=Array.from({length:Math.min(writing.doc?.totalPages||0,200)},(_,i)=>`<div class="writing-page-tile"><input type="checkbox" data-writing-page-select="${i+1}" aria-label="勾选 PDF 第 ${i+1} 页" ${writing.pages.has(i+1)?'checked':''}><button data-writing-page="${i+1}" class="${writing.pages.has(i+1)?'selected':''} ${writing.page===i+1?'current':''}" aria-label="查看 PDF 第 ${i+1} 页" aria-pressed="${writing.pages.has(i+1)}"><img loading="lazy" src="${writingPageUrl(i+1)}" alt=""><span>${i+1}</span></button></div>`).join('');
}
async function writingChoosePage(page){
 if(writing.busy)return;const n=Math.max(1,Math.min(Number(page)||1,writing.doc?.totalPages||1));
 if(writing.view==='comparison'){if(writing.preview?.pages?.some(p=>p.page===n)){writingRenderComparison(n);return;}writingSetView('content');}writingShowPage(n);
}
function writingParsePages(value,total){const pages=new Set();for(const token of value.replace(/，/g,',').split(',').filter(t=>t.trim())){const match=/^\s*(\d+)(?:\s*-\s*(\d+))?\s*$/.exec(token);if(!match)throw new Error('请输入页次，例如 1,3-5');const a=Number(match[1]),b=Number(match[2]||a);if(a<1||b<a||b>total||b-a>=80)throw new Error('页次超出范围或一次选择超过 80 页');for(let p=a;p<=b;p++)pages.add(p);if(pages.size>80)throw new Error('一次最多选择 80 页');}if(!pages.size)throw new Error('请至少选择一页');return [...pages].sort((a,b)=>a-b);}
function writingTogglePage(page){if(writing.busy)return;if(writing.selectionMode==='single'){const wasSelected=writing.pages.has(page);writingReset();writing.pages=wasSelected?new Set():new Set([page]);writingShowPage(page);return;}if(!writing.pages.has(page)&&writing.pages.size>=80)throw new Error('一次最多选择 80 页');writingReset();writing.pages.has(page)?writing.pages.delete(page):writing.pages.add(page);writingShowPage(page);}
async function writingSetMode(mode){
 if(writing.busy)return;
 if(writing.mode!==mode){writingReset();writing.mode=mode;}
 $('#writingPdfToolbar').hidden=mode!=='pdf';$('#writingSourceToolbar').hidden=mode!=='source';$('#writingPdfScroll').hidden=mode!=='pdf';$('#writingSourceEditor').hidden=mode!=='source';$('#writingThumbnails').hidden=mode!=='pdf'||$('#writingThumbnailsToggle').getAttribute('aria-expanded')!=='true';
 $('#writingPageSelectionToolbar').hidden=mode!=='pdf'||writing.selectionMode!=='multiple';
 if(mode==='source')await writingReadSource();else if(writing.doc?.totalPages)writingShowPage(writing.page);
 writingTaskControls();writingControls();
}
async function writingEnsureEditor(){
 if(writingEditor)return;
 if(!monacoApi)throw new Error('编辑器正在载入，请稍后重试。');
 writingEditor=monacoApi.editor.create($('#writingSourceEditor'),{value:'',language:'latex',readOnly:true,automaticLayout:true,fontFamily:'"Studio Digits", "Studio Source Han", Consolas, monospace',fontSize:14,lineHeight:24,theme:'vs',minimap:{enabled:false},scrollBeyondLastLine:false,wordWrap:'on',renderLineHighlight:'none',overviewRulerLanes:0,padding:{top:14},selectionHighlight:true,contextmenu:true});
 writingEditor.onDidChangeCursorSelection(e=>{
  if(writing.mode!=='source'||writing.busy||!writingModel||e.selection.isEmpty())return;
  const start=writingModel.getOffsetAt(e.selection.getStartPosition()),end=writingModel.getOffsetAt(e.selection.getEndPosition());
  if(writing.range?.start!==start||writing.range?.end!==end){if(writing.context)writingReset();writing.range={start,end};writingHighlightSource();writingControls();}
 });
}
async function writingReadSource(useSelection=false,preserve=false){
 await writingEnsureEditor();const path=useSelection&&models.get(active)?.model&&/\.tex$/i.test(active)?active:$('#writingFile').value||state.main;
 const project=state.projectId;let text=models.get(path)?.model?.getValue();if(text===undefined){const data=await api('file?path='+encodeURIComponent(path));reviewGuard(project);text=data.content;}
 text=text.replace(/\r\n/g,'\n');
 if(writing.file!==path||writing.full!==text){if(writing.context&&!preserve)writingReset();writing.file=path;writing.full=text;writing.range={start:0,end:text.length};writingModel?.dispose();writingModel=monacoApi.editor.createModel(text,'latex');writingEditor.setModel(writingModel);writingDecorations=[];}
 if(useSelection&&path===active){const s=editor.getSelection(),main=models.get(path).model;if(s&&!s.isEmpty()){
  const raw=main.getValue();writing.range={start:raw.slice(0,main.getOffsetAt(s.getStartPosition())).replace(/\r\n/g,'\n').length,end:raw.slice(0,main.getOffsetAt(s.getEndPosition())).replace(/\r\n/g,'\n').length};
 }}
 $('#writingFile').value=path;writingHighlightSource();requestAnimationFrame(()=>writingEditor.layout());writingControls();
}
function writingHighlightSource(){
 if(!writingModel||!writing.range)return;const a=writingModel.getPositionAt(writing.range.start),b=writingModel.getPositionAt(writing.range.end);
 writingDecorations=writingEditor.deltaDecorations(writingDecorations,[{range:new monacoApi.Range(a.lineNumber,a.column,b.lineNumber,b.column),options:{className:'writing-source-selected',inlineClassName:'writing-source-selected-text',isWholeLine:false}}]);
 $('#writingSourceSelection').textContent=writing.range.start===0&&writing.range.end===writing.full.length?'完整文件':'第 '+a.lineNumber+'–'+b.lineNumber+' 行';
 $('#writingLineStart').value=a.lineNumber;$('#writingLineEnd').value=b.lineNumber;$('#writingLineStart').max=writingModel.getLineCount();$('#writingLineEnd').max=writingModel.getLineCount();
 $('#writingTargetLabel').textContent=writing.file+' · '+$('#writingSourceSelection').textContent;$('#writingContentState').textContent=Array.from(writing.full.slice(writing.range.start,writing.range.end)).length.toLocaleString()+' 字符已选';
}
async function writingCompile(){
 if(writing.busy)return;writingStatus('正在保存并编译…');await compile();
 writingControls();
}
async function writingStart(){
 if(writing.busy)return;if(typeof writingRemember==='function')writingRemember();writing.busy=true;writingError();writingControls();
 try{
  if(typeof writingPrepareBeforeAI==='function')await writingPrepareBeforeAI();else writingClean();
  if(!writing.doc?.totalPages)throw new Error('请先保存并编译文档。');
  if($('#writingTask').value==='check'&&writing.mode==='pdf'){await writingLocalScan();return;}
  const mode=writing.mode,project=state.projectId,task=$('#writingTask').value;
  writingStatus('正在关联所选内容…');let context;
  if(mode==='pdf'){const pages=[...writing.pages].sort((a,b)=>a-b);context=pages.length>1||writingContinuous.fullDocument?await api('ai/pages-prepare',{pages,wholeDocument:writingContinuous.fullDocument}):await api('ai/page-prepare',{page:pages[0]});}
  else{
   const live=models.get(writing.file)?.model;
   if(!writing.range||live&&writing.full!==live.getValue().replace(/\r\n/g,'\n'))throw new Error('源码已变化，请重新读取并编译。');
   const start=Array.from(writing.full.slice(0,writing.range.start)).length,end=Array.from(writing.full.slice(0,writing.range.end)).length;
   context=await api('ai/source-prepare',{path:writing.file,start,end});
  }
  reviewGuard(project);writingDisposeDiff();writing.context=context;writing.result=null;writing.preview=null;writing.selected.clear();writing.applied=false;writing.stale=false;
  $('#writingResults').innerHTML='<div class="writing-result-empty"><span class="spinner"></span><strong>正在生成建议</strong></div>';writingStep(1);writingSetView('content');
  const instruction=$('#writingInstruction').value;
  const purpose={audit:'综合检查结构、前后衔接、术语一致性、表达、引用与页面排版，修正明确问题，保留事实与数值。',format:'优化页面排版、段落间距和层次。',correct:'检查并修复文字与源码错误。',polish:'改善学术表达，精简冗余。',translate:'将所选正文翻译为'+$('#writingLanguage option:checked').textContent+'，保留公式与引用。'}[task]||'';
  const payload=mode==='pdf'?{task:context.mode==='pages'?'pages_edit':'page_edit',provider:'deepseek',pageContext:context.id,instruction:(purpose+'\n'+instruction).slice(0,1600)}:{task:task==='audit'?'correct':task,provider:$('#writingProvider').value,sourceContext:context.id,instruction:task==='audit'?(purpose+'\n'+instruction).slice(0,1600):instruction,target:$('#writingLanguage').value};
  writing.context.request={task:payload.task,provider:payload.provider,instruction:payload.instruction,target:payload.target};
  writing.job=await api('ai/start',payload);if(typeof writingRemember==='function')writingRemember();
  if(writing.stopRequested&&writing.job.running)await api('ai/cancel',{id:writing.job.id});
  writingStatus(writing.job.stage||'正在生成建议…');clearInterval(writingTimer);writingTimer=setInterval(writingPoll,700);await writingPoll();
 }catch(e){writing.busy=false;throw e;}finally{writing.preparing=false;writingControls();}
}
async function writingPoll(){
 if(writing.polling)return;writing.polling=true;
 try{
  writingGuard();
  if(writing.job?.running){
   const job=await api('ai/job?id='+encodeURIComponent(writing.job.id));if(!job.id)throw new Error('任务已失效，请恢复最近任务。');writing.job=job;writingStatus(job.stage);
   if(job.result&&typeof writingAcceptResult==='function')writingAcceptResult(job.result);
   if(!job.running){clearInterval(writingTimer);writing.busy=false;if(!job.success&&!(job.result?.edits?.length))throw new Error(job.error||'未能生成建议');
    if(typeof writingAcceptResult!=='function'){writing.result=job.result;writing.selected=new Set((job.result.edits||[]).map((_,i)=>i));writingStep(1);writingRenderResult();}
    writingStatus(!job.success?'任务已停止，已完成的建议已保留。':writing.selected.size?'建议已生成，请选择修改后预览。':'检查完成，没有可应用修改。');if(typeof writingRemember==='function')writingRemember();}
  }else if(writing.preview?.running){
   const preview=await api('ai/page-preview?id='+encodeURIComponent(writing.context.id));writing.preview=preview;writingStatus(preview.stage);
   if(!preview.running){clearInterval(writingTimer);writing.busy=false;if(!preview.success)throw new Error(preview.error||'候选修改编译失败');writingRenderComparison();writingStep(2);writingSetView('comparison');writingStatus(preview.changed?'预览已更新，确认后应用。':'编译通过；所选页未检测到可见变化。');if(typeof writingRemember==='function')writingRemember();}
  }
 }catch(e){
  const running=writing.job?.running||writing.preview?.running;
  if(running&&writing.context?.projectId===state?.projectId&&!writing.stale){writingStatus('状态读取中断，正在重连；不会重发 AI 请求。');writingError(e.message);}
  else{clearInterval(writingTimer);writing.busy=false;writingError(e.message);}
 }finally{writing.polling=false;writingControls();}
}
function writingRenderResult(){
 $('.writing-request').classList.add('compact');$('#writingRequestToggle').hidden=false;$('#writingRequestToggle').textContent='调整要求';
 const result=writing.result||{},edits=result.edits||[];$('#writingSuggestionCount').textContent=edits.length||result.issues?.length||0;
 const summaryText=result.rebased?'原建议已关联到最新源码。':result.summary;
 const summary=summaryText?`<p class="writing-summary">${esc(summaryText)}</p>`:'';
 const issues=(result.issues||[]).map((issue,i)=>`<button class="writing-issue ${esc(issue.severity||'info')}" data-writing-issue="${i}"><span>${issue.severity==='error'?'!':'·'}</span><div>${issue.page?`<strong>第 ${Number(issue.page)} 页</strong>`:issue.line?`<strong>第 ${Number(issue.line)+(writing.context?.startLine||1)-1} 行</strong>`:''}<p>${esc(issue.message)}</p></div></button>`).join('');
 const rejected=(result.rejected||[]).length?`<details class="writing-rejected"><summary>${result.rejected.length} 项未能安全定位</summary>${result.rejected.map(r=>`<p>${esc(r.reason)}</p>`).join('')}</details>`:'';
 const cards=edits.map((e,i)=>`<article class="writing-edit ${writing.selected.has(i)?'chosen':''}" data-writing-card="${i}"><label><input type="checkbox" data-writing-edit="${i}" ${writing.selected.has(i)?'checked':''}><strong>${esc(e.reason||'建议修改 '+(i+1))}</strong><span>${e.page?'第 '+Number(e.page)+' 页':i+1}</span></label><button class="writing-edit-diff" data-writing-focus="${i}" title="定位修改"><del>${esc(e.before||'（插入）')}</del><ins>${esc(e.after||'（删除）')}</ins></button></article>`).join('');
 const empty=!edits.length&&!issues&&!result.dictionary?`<div class="writing-result-empty"><strong>${esc(writing.job?.running?'当前页处理中，已完成的建议会逐步显示':result.manualReason||'没有可定位的源码修改')}</strong></div>`:'';
 $('#writingResults').innerHTML=(typeof writingPageStates==='function'?writingPageStates(result):'')+summary+issues+rejected+cards+(result.dictionary?`<pre class="writing-dictionary">${esc(result.dictionary)}</pre>`:'')+empty;writingControls();
}
function writingSelectionChanged(){
 const same=writingSamePreview();
 if(writing.preview?.success){if(same){writingRenderComparison();writingStatus('已恢复与预览相同的选择，可确认应用。');}else{writingStatus('选择已变化，请重新预览后应用。');$('#writingCompareMeta').textContent='选择已变化 · 上次预览';}}
 writingStep(same?2:1);writingDisposeDiff();
 if(writing.view==='diff')writingShowDiff();writingControls();
 if(typeof writingRemember==='function')writingRemember();
}
function writingCompose(){
 let text=writing.context.source;
 for(const edit of writing.result.edits.filter((_,i)=>writing.selected.has(i)).sort((a,b)=>b.start-a.start)){const points=Array.from(text),a=points.slice(0,edit.start).join('').length,b=points.slice(0,edit.end).join('').length;text=text.slice(0,a)+edit.after+text.slice(b);}
 return text;
}
function writingSetView(view){
 writing.view=view;$('#writingContent').hidden=view!=='content';$('#writingComparison').hidden=view!=='comparison';$('#writingDiff').hidden=view!=='diff';
 if(view==='diff')writingShowDiff();if(view==='content')requestAnimationFrame(()=>writingEditor?.layout());writingControls();
 if(typeof writingWorkspaceSave==='function')writingWorkspaceSave();
}
function writingShowDiff(){
 if(!writing.context||!writing.result?.edits?.length||!monacoApi)return;
 if(writingDiffEditor){writingDiffEditor.layout();return;}
 writingDiffModels=[monacoApi.editor.createModel(writing.context.source,'latex'),monacoApi.editor.createModel(writingCompose(),'latex')];
 writingDiffEditor=monacoApi.editor.createDiffEditor($('#writingDiff'),{readOnly:true,originalEditable:false,automaticLayout:true,renderSideBySide:innerWidth>1050,ignoreTrimWhitespace:false,fontFamily:'"Studio Digits", "Studio Source Han", Consolas, monospace',fontSize:14,lineHeight:24,minimap:{enabled:false},scrollBeyondLastLine:false,theme:'vs'});
 writingDiffEditor.setModel({original:writingDiffModels[0],modified:writingDiffModels[1]});
}
function writingDisposeDiff(){writingDiffEditor?.dispose();writingDiffEditor=null;writingDiffModels.forEach(m=>m.dispose());writingDiffModels=[];}
async function writingPreview(){
 if(writing.busy)return;writingGuard();writingClean();if(!writing.selected.size)throw new Error('请至少选择一项修改。');
 writing.busy=true;writingControls();try{writing.preview=await api('ai/page-preview',{id:writing.context.id,selected:[...writing.selected]});writingStatus('正在临时副本中编译…');clearInterval(writingTimer);writingTimer=setInterval(writingPoll,700);await writingPoll();}catch(e){writing.busy=false;writingControls();throw e;}
}
function writingRenderComparison(page=null){
 const pages=writing.preview.pages||[{page:writing.context.page,shownPage:writing.context.page,changed:writing.preview.changed}];
 const current=pages.find(p=>p.page===Number(page||writing.comparePage))||pages[0];writing.comparePage=current.page;
 if(writing.mode==='pdf'&&writing.page!==current.page)writingShowPage(current.page);
 $('#writingComparePage').hidden=pages.length<2;$('#writingComparePage').innerHTML=pages.map(p=>`<option value="${p.page}">第 ${p.page} 页</option>`).join('');$('#writingComparePage').value=current.page;
 const base='/api/ai/page-image?id='+encodeURIComponent(writing.context.id)+'&project='+encodeURIComponent(writing.context.projectId)+'&v='+writing.preview.id+'&page='+current.page;
 for(const id of ['writingBefore','writingOverlayBefore'])$('#'+id).src=base+'&which=before';for(const id of ['writingAfter','writingOverlayAfter'])$('#'+id).src=base+'&which=after';
 $('#writingCompareMeta').textContent='第 '+current.page+' 页'+(current.shownPage!==current.page?' → 第 '+current.shownPage+' 页':'')+' · '+(current.changed?'有可见变化':'无可见变化')+' · 修改后 '+writing.preview.totalPages+' 页';writingControls();
}
async function writingApply(undo=false){
 if(writing.busy)return;writingGuard();writingClean();if(!undo&&!writingSamePreview())throw new Error('请先预览当前所选修改。');
 writing.busy=true;writingControls();
 try{
  const result=await api(undo?'ai/page-undo':'ai/page-apply',{id:writing.context.id,previewId:writing.preview?.id,selected:[...writing.selected]});
  // Keep the workbench visible; reload the original editor model before compiling.
  for(const path of result.files||[result.path]){const model=models.get(path)?.model;
   if(model){const file=await api('file?path='+encodeURIComponent(path));model.pushStackElement();model.pushEditOperations([],[{range:model.getFullModelRange(),text:file.content}],()=>null);model.pushStackElement();const info=models.get(path);info.revision=file.revision;info.dirty=false;}}
  renderTabs();
  writing.applied=!undo;
  writing.appliedCount=writing.selected.size;writing.canUndo=!undo;
  if(writing.mode==='source')await writingReadSource(false,true);
  if(undo){writingReset();writingStatus('已撤销，正在更新 PDF…');}else{writingStep(3);writingStatus('已应用，正在更新 PDF…');writingRenderResult();}
  await compile();
 }finally{writing.busy=false;writingControls();}
}
async function writingLocalScan(){
 const project=state.projectId;writingStatus('正在检查当前页…');
 try{
  if(!writing.pages.size)throw new Error('请至少选择一页');
  const report=await api('review/layout',{pages:[...writing.pages].sort((a,b)=>a-b).join(',')});reviewGuard(project);writing.localIssues=report.issues;writing.context=null;writing.result={summary:'本地检查完成',edits:[],issues:report.issues};writing.selected.clear();writing.preview=null;writingRenderResult();writingStep(1);writingStatus(report.issues.length?report.issues.length+' 条检查提示':'所选页面未触发检查规则。');
 }finally{writing.busy=false;writingControls();}
}
function writingFocusIssue(index){
 const issue=writing.result?.issues?.[index];if(!issue)return;
 writingSetView('content');if(writing.mode==='pdf'&&issue.page)writingShowPage(Number(issue.page));if(writing.mode==='pdf'&&issue.bbox){const [a,b,c,d]=issue.bbox,el=$('#writingPdfHighlight');el.style.left=Math.max(0,a)*100+'%';el.style.top=Math.max(0,b)*100+'%';el.style.width=Math.max(.01,Math.min(1,c)-Math.max(0,a))*100+'%';el.style.height=Math.max(.01,Math.min(1,d)-Math.max(0,b))*100+'%';el.hidden=false;}
 else if(writing.mode==='source'&&issue.line){const line=Number(issue.line)+(writing.context?.startLine||1)-1;writingEditor.revealLineInCenter(line);writingEditor.setPosition({lineNumber:line,column:1});}
}
function writingFocusEdit(index){
 const edit=writing.result?.edits?.[index];if(!edit)return;
 if(writing.mode==='source'&&writingModel){
  writingSetView('content');const offset=(writing.context.start??Array.from(writing.full.slice(0,writing.range.start)).length)+edit.start;
  const a=Array.from(writing.full).slice(0,offset).join('').length,b=a+edit.before.length;
  const start=writingModel.getPositionAt(a),end=writingModel.getPositionAt(b);writingEditor.revealRangeInCenter(new monacoApi.Range(start.lineNumber,start.column,end.lineNumber,end.column));
  writingDecorations=writingEditor.deltaDecorations(writingDecorations,[{range:new monacoApi.Range(start.lineNumber,start.column,end.lineNumber,end.column),options:{className:'writing-source-focus',isWholeLine:false}}]);
 }else{writingSetView('diff');}
 $$('[data-writing-card]').forEach(el=>el.classList.toggle('focused',Number(el.dataset.writingCard)===index));
}
async function writingRestore(){
 if(typeof writingRestoreTask==='function'){const tasks=await api('ai/tasks');if(!tasks.length)throw new Error('暂无可恢复任务');return writingRestoreTask(tasks[0].id);}
 if(writing.busy)return;writingClean();const job=await api('ai/job');if(job.running)throw new Error('任务仍在运行，请等待完成。');
 if(!job.result?.pageContext)throw new Error('没有可恢复的修改任务。');
 const context=await api('ai/page-context?id='+encodeURIComponent(job.result.pageContext));reviewGuard(context.projectId);if(context.undone)throw new Error('该任务已撤销，请重新选择内容。');
 writingReset();writing.project=context.projectId;writing.mode=context.mode==='source'?'source':'pdf';writing.pages=new Set(context.pages||[context.page]);writing.selectionMode=writing.pages.size>1?'multiple':'single';$('#writingSelectionMode').value=writing.selectionMode;
 writing.page=context.page;
 if(writing.mode==='source'){writing.file=context.path;writingPopulateFiles();await writingReadSource();if(Number.isInteger(context.start))writing.range={start:Array.from(writing.full).slice(0,context.start).join('').length,end:Array.from(writing.full).slice(0,context.end).join('').length};writingHighlightSource();}
 writing.context=context;writing.job=job;writing.result=context.result||job.result;writing.applied=context.applied;writing.preview=context.preview?.id?context.preview:null;writing.selected=new Set(context.preview?.selected||writing.result.edits.map((_,i)=>i));writing.stale=!writing.applied&&writing.doc?.pdfVersion!==context.pdfVersion;
 $('#writingPdfToolbar').hidden=writing.mode!=='pdf';$('#writingSourceToolbar').hidden=writing.mode!=='source';$('#writingPdfScroll').hidden=writing.mode!=='pdf';$('#writingSourceEditor').hidden=writing.mode!=='source';
 $('#writingPageSelectionToolbar').hidden=writing.mode!=='pdf'||writing.selectionMode!=='multiple';writingRenderThumbnails();
 $('#writingThumbnails').hidden=writing.mode!=='pdf'||$('#writingThumbnailsToggle').getAttribute('aria-expanded')!=='true';
 writingShowPage(context.page);writingRenderResult();writingTaskControls();
 if(writing.preview?.success){writingRenderComparison();writingStep(writing.applied?3:2);writingSetView('comparison');}else writingStep(1);
 writingStatus('任务已恢复');
}
function writingOnState(next){
 if(document.body.dataset.view!=='ai'||reviewTool!=='assistant')return;
 if(writingOpening){writingControls();return;}
 if(writing.project&&writing.project!==next.projectId&&!writing.busy){writingReset();writing.project=null;writingWatch(()=>writingOpen())();return;}
 if(!writing.preparing&&!next.running&&(!writing.doc||String(next.pdfVersion)!==writingStateVersion)&&next.hasPdf){writingWatch(writingLoadDocument)();if(writing.applied)writingStatus('已应用 '+(writing.appliedCount||writing.selected.size)+' 处修改 · PDF 已更新');else if(writing.step===0)writingStatus('编译完成，可选择内容。');}
 writingControls();
}
const writingPreviousNotify=hubNotifyState;hubNotifyState=function(next){writingPreviousNotify(next);writingOnState(next);};
$$('[data-review-tool="assistant"]').forEach(b=>b.onclick=writingWatch(async()=>{reviewShow('assistant');await writingOpen();}));
$$('[data-writing-mode]').forEach(b=>b.onclick=writingWatch(()=>writingSetMode(b.dataset.writingMode)));
$$('[data-writing-view]').forEach(b=>b.onclick=()=>writingSetView(b.dataset.writingView));
$('#writingTask').onchange=()=>writingTaskControls();$('#writingProvider').onchange=()=>writingTaskControls('provider');
$('#writingRequestToggle').onclick=()=>{const compact=$('.writing-request').classList.toggle('compact');$('#writingRequestToggle').textContent=compact?'调整要求':'收起';};
$('#writingSuggest').onclick=writingWatch(writingStart);$('#writingPreview').onclick=writingWatch(writingPreview);$('#writingApply').onclick=writingWatch(()=>writingApply());$('#writingUndo').onclick=writingWatch(()=>writingApply(true));
$('#writingStop').onclick=writingWatch(async()=>{if(writing.job?.running)await api('ai/cancel',{id:writing.job.id});});
$('#writingCompile').onclick=writingWatch(writingCompile);$('#writingEmptyCompile').onclick=writingWatch(writingCompile);$('#writingRestore').onclick=writingWatch(writingRestore);
$('#writingContinue').onclick=writingWatch(async()=>{writingReset();await writingLoadDocument();if(writing.mode==='source')await writingReadSource();});
$('#writingPage').onchange=writingWatch(()=>writingChoosePage($('#writingPage').value));$('#writingPrevious').onclick=writingWatch(()=>writingChoosePage(writing.page-1));$('#writingNext').onclick=writingWatch(()=>writingChoosePage(writing.page+1));
$('#writingThumbnailsToggle').onclick=()=>{const open=$('#writingThumbnails').hidden;$('#writingThumbnails').hidden=!open;$('#writingThumbnailsToggle').setAttribute('aria-expanded',String(open));};
$('#writingThumbnails').onclick=writingWatch(async e=>{const b=e.target.closest('[data-writing-page]');if(b)await writingChoosePage(Number(b.dataset.writingPage));});
$('#writingSelectionMode').onchange=writingWatch(async e=>{if(writing.busy)return;writingReset();writing.selectionMode=e.target.value;writing.pages=new Set([writing.page]);$('#writingPageSelectionToolbar').hidden=writing.selectionMode!=='multiple';writingRenderThumbnails();writingShowPage(writing.page);});
$('#writingChoosePages').onclick=writingWatch(async()=>{if(writing.busy)return;const pages=writingParsePages($('#writingPageRange').value,writing.doc?.totalPages||0);writingReset();writing.pages=new Set(pages);writingShowPage(pages[0]);});
$('#writingClearPages').onclick=()=>{if(writing.busy)return;writingReset();writing.pages.clear();writingShowPage(writing.page);};
$('#writingThumbnails').onchange=writingWatch(async e=>{const el=e.target.closest('[data-writing-page-select]');if(el){try{writingTogglePage(Number(el.dataset.writingPageSelect));}finally{writingShowPage(writing.page);}}});
// Reading a PDF page never changes the task scope. Use explicit page controls.
$('#writingPdfImage').onload=()=>{if(writing.mode==='pdf')$('#writingContentState').textContent='当前编译结果';if($('#writingError').textContent.startsWith('页面载入失败'))writingError();};$('#writingPdfImage').onerror=()=>{writingError('页面载入失败，请重新编译后重试。');};
$('#writingFile').onchange=writingWatch(()=>writingReadSource());$('#writingReadSource').onclick=writingWatch(()=>writingReadSource());
$('#writingSelectFile').onclick=()=>{if(writing.busy)return;if(writing.context)writingReset();writing.range={start:0,end:writing.full.length};writingHighlightSource();writingControls();};
$('#writingChooseLines').onclick=writingWatch(async()=>{if(writing.busy||!writingModel)return;const first=Number($('#writingLineStart').value),last=Number($('#writingLineEnd').value);if(!Number.isInteger(first)||!Number.isInteger(last)||first<1||last<first||last>writingModel.getLineCount())throw new Error('请输入有效的源码行号范围。');if(writing.context)writingReset();writing.range={start:writingModel.getOffsetAt({lineNumber:first,column:1}),end:writingModel.getOffsetAt({lineNumber:last,column:writingModel.getLineMaxColumn(last)})};writingHighlightSource();writingEditor.revealLineInCenter(first);writingControls();});
$('#writingLocalCheck').onclick=writingWatch(async()=>{if(writing.busy)return;writingReset();writing.busy=true;writingControls();try{if(typeof writingPrepareBeforeAI==='function')await writingPrepareBeforeAI(true);await writingLocalScan();}finally{writing.busy=false;writingControls();}});
$('#writingResults').onchange=e=>{const el=e.target.closest('[data-writing-edit]');if(!el)return;const i=Number(el.dataset.writingEdit);el.checked?writing.selected.add(i):writing.selected.delete(i);el.closest('.writing-edit').classList.toggle('chosen',el.checked);writingSelectionChanged();};
$('#writingResults').onclick=e=>{const focus=e.target.closest('[data-writing-focus]'),issue=e.target.closest('[data-writing-issue]');if(focus)writingFocusEdit(Number(focus.dataset.writingFocus));if(issue)writingFocusIssue(Number(issue.dataset.writingIssue));};
$('#writingSelectAll').onchange=e=>{writing.selected=new Set(e.target.checked?writing.result.edits.map((_,i)=>i):[]);writingRenderResult();writingSelectionChanged();};
$$('[data-writing-compare]').forEach(b=>b.onclick=()=>{const overlay=b.dataset.writingCompare==='overlay';$('#writingCompareImages').hidden=overlay;$('#writingOverlay').hidden=!overlay;$('#writingSliderLabel').hidden=!overlay;$$('[data-writing-compare]').forEach(el=>el.classList.toggle('active',el===b));});
$('#writingSlider').oninput=e=>$('#writingOverlay').style.setProperty('--split',e.target.value+'%');
$('#writingZoom').onchange=e=>{const zoom=e.target.value;$('#writingCompareScroll').classList.toggle('actual-size',zoom!=='fit');$('#writingCompareScroll').style.setProperty('--page-width',zoom==='125'?'1035px':'828px');};
$('#writingComparePage').onchange=e=>writingRenderComparison(Number(e.target.value));
window.addEventListener('resize',()=>{writingEditor?.layout();writingDiffEditor?.layout();});
writingControls();
