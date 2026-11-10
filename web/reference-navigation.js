'use strict';
const referenceBrowser={category:'bibliography',selected:null,limit:60,locations:[],project:null};
const sourceNavigation={pick:false,last:null,decorations:[],timer:null};
const referenceCategories={files:'追踪文件',labels:'标签定义',references:'交叉引用',bibliography:'文献条目'};
function referenceLocationButton(loc,label='源码',pdf=false){const index=referenceBrowser.locations.push(loc)-1;return `<button type="button" class="${pdf?'reference-pdf-button':'secondary'}" data-reference-location="${index}" data-reference-destination="${pdf?'pdf':'source'}">${esc(label)}</button>`;}
function referenceBody(entry){
 const fields=entry.fields||{},definitions=entry.definitions||[],usages=entry.usages||[];let detail='';
 if(entry.kind==='bibliography'){
  detail=`<p class="reference-entry-text">${esc(entry.title)}</p>`;
  const labels={author:'作者',year:'年份',journal:'期刊',booktitle:'收录',publisher:'出版社',doi:'DOI',url:'链接'};
  detail+='<dl class="reference-metadata">'+Object.entries(labels).filter(([key])=>fields[key]).map(([key,label])=>`<dt>${label}</dt><dd>${esc(fields[key])}</dd>`).join('')+'</dl>';
  const doi=fields.doi?.replace(/^https?:\/\/(?:dx\.)?doi\.org\//,'');const url=doi?'https://doi.org/'+doi:fields.url;
  if(url&&/^https?:\/\//i.test(url))detail+=`<a class="reference-external" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${doi?'打开 DOI':'打开原链接'} ↗</a>`;
 }else if(entry.kind==='files')detail=`<p>${entry.lines} 行 · ${entry.labels} 个标签 · ${entry.references} 处交叉引用</p>`;
 else detail=`<pre class="reference-context">${esc(entry.context||entry.raw)}</pre>`;
 detail+=`<div class="reference-entry-actions">${referenceLocationButton(entry,entry.kind==='files'?'打开文件':'定位源码')}${entry.kind==='files'?'':referenceLocationButton(entry,'定位 PDF →',true)}</div>`;
 if(definitions.length&&['references','citations'].includes(entry.kind))detail+='<h4>定义位置</h4>'+definitions.map(loc=>`<div class="reference-location-row"><span>${esc(loc.file)}:${loc.line}</span><div>${referenceLocationButton(loc,'源码')}${referenceLocationButton(loc,'PDF',true)}</div></div>`).join('');
 if(usages.length)detail+=`<h4>引用位置 · ${usages.length}</h4>`+usages.slice(0,100).map(loc=>`<div class="reference-location-row"><span>${esc(loc.file)}:${loc.line}<code>${esc(loc.match||'')}</code></span><div>${referenceLocationButton(loc,'源码')}${referenceLocationButton(loc,'PDF',true)}</div></div>`).join('');
 if(entry.kind==='bibliography'&&!usages.length)detail+='<p class="reference-inline-state">当前主文档未显式引用此条目。</p>';
 return detail+`<details class="reference-raw"><summary>${entry.kind==='files'?'查看文件开头':'查看条目原文'}</summary><pre>${esc(entry.raw)}</pre></details>`;
}
function referenceRenderBrowser(){
 const report=referenceReport,catalog=report?.catalog;referenceBrowser.locations=[];
 $('#referenceCatalog').hidden=!catalog;if(!catalog)return;
 const query=$('#referenceQuery').value.trim().toLocaleLowerCase(),category=referenceBrowser.category;
 $('#referenceStats').innerHTML=Object.entries(referenceCategories).map(([kind,label])=>`<button type="button" data-reference-category="${kind}" aria-pressed="${category===kind}" title="查看${label}"><strong>${kind==='files'?report.files.length:kind==='bibliography'?report.bibliography:report[kind]}</strong><span>${label} <b aria-hidden="true">›</b></span></button>`).join('');
 const entries=(catalog[category]||[]).filter(entry=>[entry.key,entry.title,entry.file,entry.context,...Object.values(entry.fields||{})].join(' ').toLocaleLowerCase().includes(query));
 $('#referenceCatalogTitle').textContent=referenceCategories[category]+' · '+entries.length;
 $('#referenceCatalogList').innerHTML=entries.slice(0,referenceBrowser.limit).map(entry=>`<article class="reference-entry ${entry.id===referenceBrowser.selected?'expanded':''}"><button type="button" class="reference-entry-heading" data-reference-entry="${entry.id}" aria-expanded="${entry.id===referenceBrowser.selected}"><span><strong>${esc(entry.kind==='bibliography'?entry.key:entry.title)}</strong><span>${esc(entry.kind==='bibliography'?entry.title:entry.file+':'+entry.line)}</span></span><span aria-hidden="true">${entry.id===referenceBrowser.selected?'⌃':'⌄'}</span></button>${entry.id===referenceBrowser.selected?'<div class="reference-entry-body">'+referenceBody(entry)+'</div>':''}</article>`).join('')||'<p class="reference-empty">没有匹配的条目</p>';
 $('#referenceCatalogMore').hidden=entries.length<=referenceBrowser.limit;
 $('#referenceProblemsSummary').textContent='检查提示 · '+report.issues.length;
 $('#referenceFiles').hidden=true;$('#referenceCatalogLimit').hidden=!catalog.truncated;
}
const referenceOriginalRender=referencesRender;
referencesRender=function(){referenceOriginalRender();referenceRenderBrowser();};
const referenceOriginalScan=referencesScan;
referencesScan=async function(){await referenceOriginalScan();referenceBrowser.project=state.projectId;if(!referenceReport.catalog?.[referenceBrowser.category]?.length)referenceBrowser.category=referenceReport.bibliography?'bibliography':'labels';referenceBrowser.selected=null;referenceBrowser.limit=60;$('#referenceStale').hidden=true;referencesRender();$('#referenceProblems').open=referenceReport.issues.some(i=>i.severity==='error');};
function referenceInstallBrowser(){
 $('#referenceIssues').insertAdjacentHTML('beforebegin','<div id="referenceStale" class="reference-inline-state" hidden>源码已修改，请重新检查以更新条目。</div><section id="referenceCatalog" hidden><div class="reference-catalog-title"><h3 id="referenceCatalogTitle">条目</h3><span id="referenceCatalogLimit" hidden>条目过多，已限制显示数量</span></div><div id="referenceCatalogList"></div><button id="referenceCatalogMore" class="secondary" hidden>显示更多条目</button></section><details id="referenceProblems"><summary id="referenceProblemsSummary">检查提示</summary><div id="referenceProblemHost"></div></details>');
 $('#referenceProblemHost').append($('#referenceIssues'));
 $('#referenceStats').onclick=e=>{const button=e.target.closest('[data-reference-category]');if(button){referenceBrowser.category=button.dataset.referenceCategory;referenceBrowser.selected=null;referenceBrowser.limit=60;referenceRenderBrowser();}};
 $('#referenceCatalogList').onclick=reviewWatch(async e=>{const item=e.target.closest('[data-reference-entry]');if(item){referenceBrowser.selected=referenceBrowser.selected===item.dataset.referenceEntry?null:item.dataset.referenceEntry;referenceRenderBrowser();return;}const button=e.target.closest('[data-reference-location]');if(button){reviewGuard(referenceReport.projectId);sourceNavigation.returnTool='references';$('#referenceReturn').textContent='↩ 引用条目';const loc=referenceBrowser.locations[Number(button.dataset.referenceLocation)];if(button.dataset.referenceDestination==='pdf'){await studioLocatePdf(loc);$('#referenceReturn').hidden=false;}else{await studioLocateSource(loc);$('#referenceReturn').hidden=false;}}});
 $('#referenceCatalogMore').onclick=()=>{referenceBrowser.limit+=60;referenceRenderBrowser();};
 $('#referencesScan').onclick=reviewWatch(referencesScan);$('#referenceQuery').oninput=()=>{referenceBrowser.limit=60;referencesRender();};$('#referenceSeverity').onchange=()=>{referencesRender();$('#referenceProblems').open=true;};
 const open=editorToolOpen;editorToolOpen=async function(tool){await open(tool);if(tool==='references'){if(!referenceReport){$('#referenceCatalog').hidden=true;$('#referenceStats').innerHTML='<p class="reference-empty">检查后点击统计卡片查看条目</p>';}else referencesRender();}};
 document.addEventListener('studio-source-change',()=>{if(referenceReport?.projectId===state?.projectId)$('#referenceStale').hidden=false;});
}
function studioSourceOverlays(){const result={};for(const [path,info] of models)if(info.model&&/\.(tex|bib|py|csv|json)$/i.test(path))result[path]=info.model.getValue();return result;}
async function studioLocateSource(loc){
 studioClearSourceHighlight();const path=loc.file||loc.path;if(!path)throw new Error('没有可打开的源码位置');
 hubView('editor');await openFile(path,loc.line||1);const model=models.get(path)?.model;if(!model)return;
 const line=Math.max(1,Math.min(model.getLineCount(),Number(loc.line)||1)),column=Math.min(model.getLineMaxColumn(line),Math.max(1,Number(loc.column)||1));let start=model.getOffsetAt({lineNumber:line,column}),needle=loc.raw||loc.match||'';
 const text=model.getValue();if(needle&&text.slice(start,start+needle.length)!==needle){const found=text.indexOf(needle);if(found>=0&&text.indexOf(needle,found+1)<0)start=found;else needle=loc.match||'';}
 if(needle&&text.slice(start,start+needle.length)!==needle){const lineStart=model.getOffsetAt({lineNumber:line,column:1}),found=text.indexOf(needle,lineStart);if(found>=lineStart&&found<lineStart+model.getLineLength(line))start=found;else needle='';}
 const a=model.getPositionAt(start),b=model.getPositionAt(start+(needle.length||model.getLineMaxColumn(a.lineNumber)-a.column)),range=new monacoApi.Range(a.lineNumber,a.column,b.lineNumber,b.column);
 editor.setPosition(a);editor.revealRangeInCenter(range);sourceNavigation.highlightModel=model;sourceNavigation.decorations=model.deltaDecorations([],[{range,options:{className:'reference-source-highlight',isWholeLine:!needle.length}}]);sourceNavigation.highlightTimer=setTimeout(studioClearSourceHighlight,2500);studioBindSourceHighlight();editor.focus();
 return {path,line:a.lineNumber};
}
async function studioPdfApplication(){
 if(editorAiPreview)throw new Error('请先返回原 PDF，再定位');
 const current=()=>{try{return $('#pdfFrame').contentWindow?.PDFViewerApplication;}catch{return null;}};
 let app=current();
 if((typeof pdfPhase!=='undefined'&&pdfPhase==='native')||!app?.pdfDocument){if(!state?.hasPdf)throw new Error('请先保存并编译文档');await setPdf(state.pdfVersion,true,false);app=current();}
 if(!app?.pdfDocument)throw new Error('请使用内置 PDF 预览后定位');return app;
}
async function studioHighlightPdf(point){
 const app=await studioPdfApplication(),page=app.pdfViewer.getPageView(point.page-1);if(!page)throw new Error('PDF 页次已变化，请重新编译');
 const bbox=point.bbox||[point.x,point.y,Math.min(1,point.x+.08),Math.min(1,point.y+.025)],vp=page.viewport,pos=vp.convertToPdfPoint(bbox[0]*vp.width,Math.max(0,bbox[1]-.08)*vp.height);
 app.pdfViewer.scrollPageIntoView({pageNumber:point.page,destArray:[null,{name:'XYZ'},pos[0],pos[1],null]});
 const doc=$('#pdfFrame').contentDocument;doc.querySelectorAll('.studio-location-highlight').forEach(e=>e.remove());const marker=doc.createElement('div');marker.className='studio-location-highlight';Object.assign(marker.style,{position:'absolute',left:bbox[0]*100+'%',top:bbox[1]*100+'%',width:Math.max(.008,bbox[2]-bbox[0])*100+'%',height:Math.max(.008,bbox[3]-bbox[1])*100+'%',border:'2px solid #0f62fe',background:'#0f62fe12',borderRadius:'3px',pointerEvents:'none',zIndex:'9',boxSizing:'border-box'});page.div.append(marker);clearTimeout(sourceNavigation.timer);sourceNavigation.timer=setTimeout(()=>marker.remove(),7000);
 toast('已定位 PDF 第 '+point.page+' 页'+(point.key?' · '+point.key:'')+(point.approximate?'（按源码行）':''));
}
async function studioLocatePdf(loc=null){
 if(editorAiDirty())throw new Error('源码有修改，请先保存并编译，再定位 PDF');if(editorAiPreview)throw new Error('请先返回原 PDF，再定位');
 loc=loc||{file:active,line:editor?.getPosition()?.lineNumber||1,column:editor?.getPosition()?.column||1};
 const query=new URLSearchParams({direction:'forward',path:loc.file||loc.path,line:loc.line||1,column:loc.column||1});if(['labels','bibliography','references','citations'].includes(loc.kind)&&loc.key){query.set('kind',loc.kind);query.set('key',loc.key);}
 if(loc.pdfText)query.set('text',String(loc.pdfText).slice(0,160));const project=state.projectId,version=state.pdfVersion;const point=await api('sync-point?'+query);if(project!==state.projectId||version!==state.pdfVersion||editorAiDirty())throw new Error('内容已变化，请重新编译后定位');await studioHighlightPdf(point);return point;
}
function studioPickMode(enabled){sourceNavigation.pick=!!enabled;$('#syncPickHint').hidden=!enabled;$('#syncInverse').classList.toggle('active',!!enabled);$('#syncInverse').setAttribute('aria-pressed',String(!!enabled));$('#syncInverse').textContent=enabled?'取消点选':'← 定位源码';try{$('#pdfFrame').contentDocument.documentElement.classList.toggle('studio-pick-source',!!enabled);}catch{}}
async function studioInverseAt(point){
 if(editorAiDirty())throw new Error('源码有修改，请先保存并编译，再定位源码');if(editorAiPreview)throw new Error('请先返回原 PDF，再定位');
 const project=state.projectId,version=state.pdfVersion;const result=await api('sync-point?'+new URLSearchParams({direction:'inverse',page:point.page,x:point.x,y:point.y}));if(project!==state.projectId||version!==state.pdfVersion||editorAiDirty())return;
 studioPickMode(false);await studioLocateSource(result);await studioHighlightPdf(result);if(result.key&&referenceReport?.projectId===project){const category=['citations','references'].includes(result.kind)?(result.kind==='citations'?'bibliography':'labels'):result.kind;const entry=referenceReport.catalog?.[category]?.find(e=>e.key===result.key);if(entry){sourceNavigation.returnTool='references';$('#referenceReturn').textContent='↩ 引用条目';referenceBrowser.category=category;referenceBrowser.selected=entry.id;$('#referenceReturn').hidden=false;}}
 toast('已定位源码 · '+(result.key?result.key+' · ':'')+result.path+':'+result.line+(result.approximate?'（按源码行）':''));
}
function studioBindPdfNavigation(){
 const frame=$('#pdfFrame');let doc;try{doc=frame.contentDocument;}catch{return;}if(!doc||doc.documentElement.dataset.studioNavigation)return;doc.documentElement.dataset.studioNavigation='true';
 const position=e=>{const page=e.target.closest?.('.page');if(!page)return null;const rect=page.getBoundingClientRect();return {page:Number(page.dataset.pageNumber),x:Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height)),project:state?.projectId,pdfVersion:state?.pdfVersion};};
 doc.addEventListener('pointerdown',e=>{const point=position(e);if(point)sourceNavigation.last=point;},true);
 doc.addEventListener('click',e=>{if(!sourceNavigation.pick)return;const point=position(e);if(!point)return;e.preventDefault();e.stopImmediatePropagation();studioInverseAt(point).catch(err=>toast(err.message,true));},true);
 doc.addEventListener('dblclick',e=>{const point=position(e);if(!point)return;e.preventDefault();e.stopImmediatePropagation();studioInverseAt(point).catch(err=>toast(err.message,true));},true);
 doc.addEventListener('keydown',e=>{if(e.key==='Escape')studioPickMode(false);});
 const style=doc.createElement('style');style.textContent='.studio-pick-source .page,.studio-pick-source .page *{cursor:crosshair!important}';doc.head.append(style);
}
function referenceInstallNavigation(){
 $('.editor-subbar>div:last-child').insertAdjacentHTML('afterbegin','<button type="button" id="referenceReturn" class="text-button" hidden>↩ 引用条目</button><button type="button" id="syncForward" class="sync-locate" title="将当前源码行或所选条目定位到 PDF">定位 PDF →</button>');
 $('.preview-heading>div:last-child').insertAdjacentHTML('afterbegin','<button type="button" id="syncInverse" class="sync-locate" aria-pressed="false" title="点选 PDF 中的文字或条目，定位到对应源码；也可直接双击 PDF">← 定位源码</button>');
 $('.pdf-frame-wrap').insertAdjacentHTML('beforeend','<div id="syncPickHint" class="sync-pick-hint" hidden><span>点选 PDF 中的文字或条目以定位源码</span><button type="button" id="syncPickCancel" aria-label="取消点选定位">×</button></div>');
 $('#syncForward').onclick=()=>studioLocatePdf().catch(e=>toast(e.message,true));$('#workflowLocate').textContent='定位当前源码 → PDF';$('#workflowLocate').onclick=()=>{ $('#editorToolsMenu').open=false;studioLocatePdf().catch(e=>toast(e.message,true));};workflowLocate=()=>studioLocatePdf();
 $('#syncInverse').onclick=async()=>{try{await studioPdfApplication();studioPickMode(!sourceNavigation.pick);}catch(e){toast(e.message,true);}};
 $('#syncPickCancel').onclick=()=>studioPickMode(false);document.addEventListener('keydown',e=>{if(e.key==='Escape')studioPickMode(false);});$('#pdfFrame').addEventListener('load',()=>{sourceNavigation.last=null;studioPickMode(false);studioBindPdfNavigation();});studioBindPdfNavigation();
 $('#referenceReturn').onclick=()=>editorToolOpen('references');
}
referenceInstallBrowser();referenceInstallNavigation();
