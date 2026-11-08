'use strict';
// Continuous reading and comparison share one page coordinate system.
const writingContinuous={documentKey:'',previewKey:'',anchor:1,observers:[],loading:0,queue:[],fullDocument:false};
function writingCompactPages(pages){const sorted=[...pages].sort((a,b)=>a-b),runs=[];for(let i=0;i<sorted.length;i++){const start=sorted[i];while(sorted[i+1]===sorted[i]+1)i++;runs.push(start===sorted[i]?String(start):start+'–'+sorted[i]);}return runs.join(', ');}
function writingSelectedRange(page,shift=false){
 const total=writing.doc?.totalPages||0;if(!Number.isInteger(page)||page<1||page>total)return;
 const next=writing.selectionMode==='single'?new Set():new Set(writing.pages);
 if(shift&&writing.selectionMode==='multiple'){for(let p=Math.min(writingContinuous.anchor,page);p<=Math.max(writingContinuous.anchor,page);p++)next.add(p);}
 else if(!next.delete(page))next.add(page);
 if(next.size>80)throw new Error('一次最多选择 80 页，请按章节选择');
 writingReset();writingContinuous.fullDocument=false;writing.pages=next;writingContinuous.anchor=page;writingShowPage(page,false);
}
function writingPageSync(page){
 writing.page=page;$('#writingPage').value=page;$('#writingPageRange').value=writingCompactPages(writing.pages).replaceAll('–','-');
 $('#writingPdfSelected').textContent='已选 '+writing.pages.size+' 页';
 $('#writingTargetLabel').textContent=(writingContinuous.fullDocument?'全文审核':'PDF')+' · '+(writing.pages.size?'第 '+writingCompactPages(writing.pages)+' 页':'未选择');
 for(const el of $$('[data-continuous-page]')){const n=Number(el.dataset.continuousPage);el.classList.toggle('selected',writing.pages.has(n));el.classList.toggle('current',n===page);}
 for(const el of $$('[data-continuous-select]')){const n=Number(el.dataset.continuousSelect);el.checked=writing.pages.has(n);el.disabled=!!writing.busy;}
 for(const el of $$('[data-writing-page]')){el.classList.toggle('selected',writing.pages.has(Number(el.dataset.writingPage)));el.classList.toggle('current',Number(el.dataset.writingPage)===page);el.setAttribute('aria-pressed',String(writing.pages.has(Number(el.dataset.writingPage))));}
 writingTaskControls();writingWorkspaceSave();
}
function writingLoadQueued(){
 while(writingContinuous.loading<2&&writingContinuous.queue.length){const img=writingContinuous.queue.shift();if(!img.isConnected||!img.dataset.src)continue;
  writingContinuous.loading++;img.dataset.queuedLoad='1';const done=()=>{img.onload=null;img.onerror=null;delete img.dataset.queuedLoad;writingContinuous.loading--;img.classList.remove('loading');if(img.naturalWidth){img.parentElement.style.aspectRatio=String(img.naturalWidth/img.naturalHeight);if(writing.view==='content'&&writing.mode==='pdf')$('#writingContentState').textContent='当前编译结果';}img.closest('.continuous-paper')?.classList.toggle('load-error',!img.naturalWidth);writingLoadQueued();};
  img.onload=done;img.onerror=done;img.src=img.dataset.src;delete img.dataset.src;
 }
}
function writingObserveImages(root,scroll){
 const observer=new IntersectionObserver(entries=>{for(const item of entries)if(item.isIntersecting){const img=item.target;observer.unobserve(img);if(img.dataset.src){writingContinuous.queue.push(img);writingLoadQueued();}}},{root:scroll,rootMargin:'700px 0px'});
 root.querySelectorAll('img[data-src]').forEach(img=>observer.observe(img));return observer;
}
function writingScrollPage(container,element){if(element)container.scrollTo({top:element.offsetTop-container.offsetTop-14,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
function writingRenderContinuous(){
 const key=writing.doc?.projectId+':'+writing.doc?.pdfVersion+':'+writing.doc?.totalPages;if(key===writingContinuous.documentKey)return;
 writingContinuous.documentKey=key;writingContinuous.readObserver?.disconnect();writingContinuous.pageObserver?.disconnect();
 const root=$('#writingPageStack');root.innerHTML=Array.from({length:writing.doc?.totalPages||0},(_,i)=>`<article class="continuous-page" data-continuous-page="${i+1}"><header><label><input type="checkbox" data-continuous-select="${i+1}">第 ${i+1} 页</label><button type="button" data-continuous-go="${i+1}" title="定位第 ${i+1} 页" aria-label="定位第 ${i+1} 页">↗</button></header><div class="continuous-paper"><img class="loading" data-src="${writingPageUrl(i+1)}" alt="PDF 第 ${i+1} 页"><button type="button" class="continuous-retry" data-continuous-retry>重新载入</button></div></article>`).join('');
 writingContinuous.readObserver=writingObserveImages(root,$('#writingPdfScroll'));
 let frame=0;$('#writingPdfScroll').onscroll=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{if(writing.view!=='content'||writing.mode!=='pdf')return;const scroll=$('#writingPdfScroll'),top=scroll.getBoundingClientRect().top+scroll.clientHeight*.25;let nearest=null,distance=Infinity;for(const node of root.children){const rect=node.getBoundingClientRect(),d=top<rect.top?rect.top-top:top>rect.bottom?top-rect.bottom:0;if(d<distance){distance=d;nearest=node;}}if(nearest&&Number(nearest.dataset.continuousPage)!==writing.page)writingPageSync(Number(nearest.dataset.continuousPage));});};
}
writingShowPage=function(page,scroll=true){if(!writing.doc?.totalPages)return;writingRenderContinuous();page=Math.max(1,Math.min(Number(page)||1,writing.doc.totalPages));writingPageSync(page);if(scroll)requestAnimationFrame(()=>writingScrollPage($('#writingPdfScroll'),$(`[data-continuous-page="${page}"]`)));};
writingRenderThumbnails=function(){const root=$('#writingThumbnails');const count=writing.doc?.totalPages||0;if(root.dataset.count===String(count))return;root.dataset.count=count;root.innerHTML=Array.from({length:count},(_,i)=>`<button type="button" data-writing-page="${i+1}" title="第 ${i+1} 页；Shift 连选" aria-label="选择第 ${i+1} 页">${i+1}</button>`).join('');};
writingTogglePage=page=>writingSelectedRange(page);
$('#writingThumbnails').onclick=writingWatch(e=>{const button=e.target.closest('[data-writing-page]');if(button&&!writing.busy){writingSelectedRange(Number(button.dataset.writingPage),e.shiftKey);writingShowPage(Number(button.dataset.writingPage));}});
$('#writingThumbnails').onchange=null;
$('#writingSelectionMode').onchange=()=>{if(writing.busy)return;writing.selectionMode=$('#writingSelectionMode').value;if(writing.selectionMode==='single'&&writing.pages.size>1){writingReset();writingContinuous.fullDocument=false;writing.pages=new Set([writing.page]);}$('#writingPageSelectionToolbar').hidden=writing.selectionMode!=='multiple';writingShowPage(writing.page,false);};
function writingInstallContinuous(){
 $('#writingPdfScroll').insertAdjacentHTML('beforeend','<div id="writingPageStack" class="continuous-stack" aria-label="连续 PDF 页面"></div>');
 $('#writingPageStack').onclick=writingWatch(e=>{const input=e.target.closest('[data-continuous-select]'),go=e.target.closest('[data-continuous-go]'),retry=e.target.closest('[data-continuous-retry]');if(input&&!writing.busy)writingSelectedRange(Number(input.dataset.continuousSelect),e.shiftKey);if(go)writingShowPage(Number(go.dataset.continuousGo));if(retry){const img=retry.parentElement.querySelector('img');img.dataset.src=img.src;writingContinuous.queue.push(img);writingLoadQueued();}});
 $('#writingPageSelectionToolbar').insertAdjacentHTML('beforeend','<button type="button" id="writingAllPages" class="text-button">全选页面</button>');
 $('.ai-heading-actions').insertAdjacentHTML('afterbegin','<button type="button" id="writingWholeReview" class="secondary"><span aria-hidden="true">▤</span> 全文审核</button>');
 $('#writingAllPages').onclick=writingWatch(()=>{if(writing.busy)return;const total=writing.doc?.totalPages||0;if(!total||total>80)throw new Error('全文选择支持 1～80 页，请先编译或按章节选择');writingReset();writingContinuous.fullDocument=false;writing.pages=new Set(Array.from({length:total},(_,i)=>i+1));writingShowPage(writing.page,false);});
 $('#writingWholeReview').onclick=writingWatch(async()=>{if(writing.busy)return;await writingSetMode('pdf');if(!writing.doc?.totalPages)throw new Error('请先保存并编译，再进行全文审核');if(writing.doc.totalPages>80)throw new Error('全文审核最多 80 页，请按章节选择');writingReset();writingContinuous.fullDocument=true;writing.selectionMode='multiple';$('#writingSelectionMode').value='multiple';$('#writingPageSelectionToolbar').hidden=false;writing.pages=new Set(Array.from({length:writing.doc.totalPages},(_,i)=>i+1));$('#writingTask').value='audit';$('#writingProvider').value='deepseek';writingShowPage(writing.page,false);$('#writingInstruction').focus();});
 $('#writingClearPages').onclick=()=>{if(writing.busy)return;writingReset();writingContinuous.fullDocument=false;writing.pages.clear();writingShowPage(writing.page,false);};
 $('#writingSelectCurrentPage').onclick=writingWatch(()=>{if(!writing.busy&&!writing.pages.has(writing.page))writingSelectedRange(writing.page);});
 $('#writingChoosePages').onclick=writingWatch(()=>{if(writing.busy)return;const pages=writingParsePages($('#writingPageRange').value,writing.doc?.totalPages||0);writingReset();writingContinuous.fullDocument=false;writing.pages=new Set(pages);writingShowPage(pages[0]);});
}
function writingMarker(box,label='改动'){if(!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite))return '';const [x,y,r,b]=box.map(n=>Math.max(0,Math.min(1,n)));return `<span class="continuous-mark" style="left:${x*100}%;top:${y*100}%;width:${Math.max(.003,r-x)*100}%;height:${Math.max(.003,b-y)*100}%" aria-label="${esc(label)}" title="${esc(label)}"></span>`;}
function writingCompareUrl(page,which){return '/api/ai/page-image?id='+encodeURIComponent(writing.context.id)+'&project='+encodeURIComponent(writing.context.projectId)+'&v='+writing.preview.id+'&page='+page+'&which='+which;}
function writingComparisonScroll(page){const row=$(`[data-compare-row="${page}"]`);writing.comparePage=page;$('#writingComparePage').value=page;writingScrollPage($('#writingCompareScroll'),row);}
const writingLegacyComparison=writingRenderComparison;
writingRenderComparison=function(page=null){
 if(!writing.preview?.success)return;const pages=writing.preview.pages||[{page:writing.context.page,shownPage:writing.context.page,changed:writing.preview.changed,bounds:writing.preview.bounds}],key=writing.context.id+':'+writing.preview.id;
 const current=pages.find(p=>p.page===Number(page||writing.comparePage))||pages[0];writing.comparePage=current.page;
 $('#writingComparePage').hidden=pages.length<2;$('#writingComparePage').innerHTML=pages.map(p=>`<option value="${p.page}">第 ${p.page} 页</option>`).join('');$('#writingComparePage').value=current.page;
 if(key!==writingContinuous.previewKey){writingContinuous.previewKey=key;writingContinuous.compareObserver?.disconnect();
  $('#writingCompareStack').innerHTML=pages.map(p=>`<section class="continuous-pair" data-compare-row="${p.page}" aria-label="第 ${p.page} 页对照"><header><strong>第 ${p.page} 页${p.shownPage!==p.page?' → 第 '+p.shownPage+' 页':''}</strong><span>${p.changed?'有可见改动':'无可见改动'}</span></header><div class="continuous-pair-pages">${['before','after'].map(which=>`<figure class="continuous-${which}"><figcaption>${which==='before'?'修改前':'修改后 · 待应用'}<span>${which==='before'?'红色标记原区域':'绿色标记候选区域'}</span></figcaption><div class="continuous-paper"><img class="loading" data-src="${writingCompareUrl(p.page,which)}" alt="第 ${p.page} 页${which==='before'?'修改前':'修改后'}">${p.changed?writingMarker(p.bounds,'页面可见变化区域'):''}<button type="button" class="continuous-retry" data-compare-retry>重新载入</button></div></figure>`).join('')}</div></section>`).join('');
  writingContinuous.compareObserver=writingObserveImages($('#writingCompareStack'),$('#writingCompareScroll'));
 }
 $('#writingCompareMeta').textContent=pages.length+' 页连续对照 · '+pages.filter(p=>p.changed).length+' 页有变化';
 if(!$('#writingOverlay').hidden){const base=writingCompareUrl(current.page,'before');$('#writingOverlayBefore').src=base;$('#writingOverlayAfter').src=writingCompareUrl(current.page,'after');}
 writingControls();if(page)requestAnimationFrame(()=>writingComparisonScroll(current.page));
};
function writingSetupComparison(){
 $('#writingCompareScroll').insertAdjacentHTML('afterbegin','<div id="writingCompareStack" aria-label="连续修改对照"></div>');
 $('.writing-compare-toolbar').insertAdjacentHTML('beforeend','<label class="continuous-ratio">左右宽度 <input id="writingCompareRatio" type="range" min="25" max="75" value="50" aria-label="调整修改前后宽度"></label>');
 $('#writingCompareStack').onclick=e=>{const retry=e.target.closest('[data-compare-retry]');if(retry){const img=retry.parentElement.querySelector('img');img.dataset.src=img.src;writingContinuous.queue.push(img);writingLoadQueued();}};
 $('#writingCompareRatio').oninput=e=>{$('#writingCompareStack').style.setProperty('--compare-ratio',e.target.value+'%');try{localStorage.setItem('studio.compareRatio',e.target.value);}catch{}};
 try{const n=Number(localStorage.getItem('studio.compareRatio'));if(n>=25&&n<=75){$('#writingCompareRatio').value=n;$('#writingCompareRatio').oninput({target:$('#writingCompareRatio')});}}catch{}
 for(const button of $$('[data-writing-compare]'))button.onclick=()=>{const overlay=button.dataset.writingCompare==='overlay';$('#writingCompareStack').hidden=overlay;$('#writingCompareImages').hidden=true;$('#writingOverlay').hidden=!overlay;$('#writingSliderLabel').hidden=!overlay;$$('[data-writing-compare]').forEach(b=>b.classList.toggle('active',b===button));if(overlay){$('#writingOverlayBefore').src=writingCompareUrl(writing.comparePage,'before');$('#writingOverlayAfter').src=writingCompareUrl(writing.comparePage,'after');}};
 $('#writingComparePage').onchange=e=>{writingRenderComparison(Number(e.target.value));writingRemember();};
 let frame=0;$('#writingCompareScroll').onscroll=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{if(writing.view!=='comparison'||!$('#writingOverlay').hidden)return;const top=$('#writingCompareScroll').getBoundingClientRect().top+70;for(const row of $('#writingCompareStack').children){const r=row.getBoundingClientRect();if(r.bottom>top){writing.comparePage=Number(row.dataset.compareRow);$('#writingComparePage').value=writing.comparePage;break;}}});};
 $('#writingZoom').onchange=e=>{const zoom=e.target.value;$('#writingCompareStack').classList.toggle('zoomed',zoom!=='fit');$('#writingCompareStack').style.setProperty('--comparison-min',zoom==='125'?'2100px':'1660px');};
 $('#writingFocusToggle').onclick=()=>{const row=$(`[data-compare-row="${writing.comparePage}"]`),mark=row?.querySelector('.continuous-mark');if(mark){writingScrollPage($('#writingCompareScroll'),row);mark.scrollIntoView({block:'center',inline:'nearest',behavior:'smooth'});row.classList.add('focus-flash');setTimeout(()=>row.classList.remove('focus-flash'),1200);}else writingStatus('本页没有可定位的可见变化，可查看源码差异。');};
}
const writingOldFocus=writingFocusChange;
writingFocusChange=async function(index){
 if(writing.mode==='source')return writingOldFocus(index);const edit=writing.result?.edits?.[index];if(!edit)return;const ident=writing.context.id,preview=writingSamePreview()?writing.preview.id:null,ticket=++writingFocusTicket;
 $$('[data-writing-card]').forEach(el=>el.classList.toggle('focused',Number(el.dataset.writingCard)===index));
 const query='id='+encodeURIComponent(ident)+'&index='+index+(edit.key?'&key='+encodeURIComponent(edit.key):'')+(preview?'&preview='+preview:'');const focus=await api('ai/page-focus?'+query);
 if(ticket!==writingFocusTicket||ident!==writing.context?.id||preview!==(writingSamePreview()?writing.preview.id:null)||writing.result?.edits?.[index]?.key!==edit.key)return;
 if(focus.kind==='source'){writingDiffFocus(index);return;}
 if(preview&&focus.after){writingRenderComparison();writingSetView('comparison');$('[data-writing-compare="split"]').click();const row=$(`[data-compare-row="${focus.page}"]`);for(const side of ['before','after']){const paper=row?.querySelector('.continuous-'+side+' .continuous-paper');if(paper){const img=paper.querySelector('img');if(focus[side]?.page){if(img.dataset.queuedLoad){writingContinuous.loading--;delete img.dataset.queuedLoad;img.onload=null;img.onerror=null;}img.dataset.src='/api/ai/focus-image?'+query+'&which='+side;writingContinuous.queue.push(img);writingLoadQueued();paper.parentElement.querySelector('figcaption').title='第 '+focus[side].page+' 页';}paper.querySelectorAll('.continuous-mark').forEach(e=>e.remove());paper.insertAdjacentHTML('beforeend',writingMarker(focus[side]?.box,'修改 '+(index+1)));}}writingComparisonScroll(focus.page);row?.querySelector('.continuous-mark')?.scrollIntoView({block:'center',inline:'nearest',behavior:'smooth'});}
 else if(focus.before){writingSetView('content');writingShowPage(focus.before.page);const paper=$(`[data-continuous-page="${focus.before.page}"] .continuous-paper`);paper.querySelectorAll('.continuous-mark').forEach(e=>e.remove());paper.insertAdjacentHTML('beforeend',writingMarker(focus.before.box,'修改 '+(index+1)));}
};
const writingOldIssue=writingFocusIssue;
writingFocusIssue=function(index){if(writing.mode==='source')return writingOldIssue(index);const issue=writing.result?.issues?.[index];if(!issue?.page)return;writingSetView('content');writingShowPage(issue.page);const paper=$(`[data-continuous-page="${issue.page}"] .continuous-paper`);paper?.querySelectorAll('.continuous-mark').forEach(e=>e.remove());if(issue.bbox)paper?.insertAdjacentHTML('beforeend',writingMarker(issue.bbox,'检查提示'));};
function writingSetupResize(){
 const grid=$('.writing-grid'),review=$('.writing-review');review.insertAdjacentHTML('beforebegin','<div id="writingPaneResize" class="continuous-resizer" role="separator" tabindex="0" aria-label="拖动调整页面与建议宽度" aria-orientation="vertical" aria-valuemin="20" aria-valuemax="60" aria-valuenow="32"><span></span></div>');
 const handle=$('#writingPaneResize');let ratio=32;try{ratio=Number(localStorage.getItem('studio.writingPane'))||32;}catch{}
 const apply=value=>{ratio=Math.max(20,Math.min(60,value));grid.style.setProperty('--review-width',ratio+'%');handle.setAttribute('aria-valuenow',Math.round(ratio));writingEditor?.layout();writingDiffEditor?.layout();};apply(ratio);
 handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();handle.setPointerCapture(e.pointerId);document.body.classList.add('writing-resizing');};
 handle.onpointermove=e=>{if(handle.hasPointerCapture(e.pointerId)){const rect=grid.getBoundingClientRect();apply((rect.right-e.clientX)/rect.width*100);}};
 const save=()=>{document.body.classList.remove('writing-resizing');try{localStorage.setItem('studio.writingPane',ratio);}catch{}};
 handle.onpointerup=e=>{handle.releasePointerCapture(e.pointerId);save();};handle.onlostpointercapture=save;handle.onpointercancel=save;
 handle.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();apply(e.key==='Home'?32:ratio+(e.key==='ArrowLeft'?2:-2));save();}};handle.ondblclick=()=>{apply(32);save();};
}
function writingSetupPageRail(){
 const rail=$('#writingThumbnails'),content=$('#writingContent');
 rail.insertAdjacentHTML('afterend','<div id="writingPageRailResize" class="continuous-resizer" role="separator" tabindex="0" aria-label="拖动调整页码列表宽度" aria-orientation="vertical" aria-valuemin="76" aria-valuemax="240"><span></span></div>');
 const handle=$('#writingPageRailResize');let width=86,drag=null,frame=0,blockClick=false;
 try{const saved=Number(localStorage.getItem('studio.pageRailWidth'));if(Number.isFinite(saved)&&saved>=76)width=saved;}catch{}
 const apply=value=>{width=Math.max(76,Math.min(240,content.clientWidth*.4||240,value));rail.style.setProperty('--page-rail-width',width+'px');handle.setAttribute('aria-valuenow',String(Math.round(width)));};
 const save=()=>{document.body.classList.remove('writing-resizing');try{localStorage.setItem('studio.pageRailWidth',String(width));}catch{}};
 apply(width);const syncVisibility=()=>{handle.hidden=rail.hidden;};syncVisibility();new MutationObserver(syncVisibility).observe(rail,{attributes:true,attributeFilter:['hidden']});
 handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();handle.setPointerCapture(e.pointerId);document.body.classList.add('writing-resizing');};
 handle.onpointermove=e=>{if(handle.hasPointerCapture(e.pointerId))apply(e.clientX-rail.getBoundingClientRect().left);};
 handle.onpointerup=e=>{handle.releasePointerCapture(e.pointerId);save();};handle.onlostpointercapture=save;handle.onpointercancel=save;
 handle.ondblclick=()=>{apply(86);save();};handle.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();apply(e.key==='Home'?86:width+(e.key==='ArrowRight'?8:-8));save();}};
 const paint=()=>{if(!drag)return;for(const button of rail.querySelectorAll('[data-writing-page]')){const selected=drag.pages.has(Number(button.dataset.writingPage));button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));}};
 const hit=()=>{if(!drag?.active)return;const box=rail.getBoundingClientRect(),x=Math.max(box.left+10,Math.min(box.right-26,drag.x)),y=Math.max(box.top+14,Math.min(box.bottom-14,drag.y)),button=document.elementFromPoint(x,y)?.closest('[data-writing-page]');if(!button||!rail.contains(button))return;const page=Number(button.dataset.writingPage);if(page===drag.end)return;drag.end=page;drag.pages=new Set(drag.before);for(let n=Math.min(drag.start,page);n<=Math.max(drag.start,page);n++)drag.remove?drag.pages.delete(n):drag.pages.add(n);paint();};
 const tick=()=>{if(!drag?.active)return;const box=rail.getBoundingClientRect(),edge=35,delta=drag.y<box.top+edge?-Math.min(12,(box.top+edge-drag.y)/3):drag.y>box.bottom-edge?Math.min(12,(drag.y-box.bottom+edge)/3):0;if(delta){rail.scrollTop+=delta;hit();}frame=requestAnimationFrame(tick);};
 rail.addEventListener('pointerdown',e=>{const button=e.target.closest('[data-writing-page]');if(!button||e.button!==0||writing.busy||state?.running||state?.packageBusy)return;drag={element:button,pointer:e.pointerId,start:Number(button.dataset.writingPage),end:null,x:e.clientX,y:e.clientY,originX:e.clientX,originY:e.clientY,before:new Set(writing.pages),pages:new Set(writing.pages),remove:e.altKey,active:false};button.setPointerCapture(e.pointerId);});
 rail.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.pointer)return;drag.x=e.clientX;drag.y=e.clientY;if(!drag.active&&Math.hypot(e.clientX-drag.originX,e.clientY-drag.originY)>=5){drag.active=true;rail.classList.add('selecting-pages');frame=requestAnimationFrame(tick);}if(drag.active){e.preventDefault();hit();}});
 const finish=cancel=>{if(!drag)return;const selection=drag;drag=null;cancelAnimationFrame(frame);rail.classList.remove('selecting-pages');if(selection.element.hasPointerCapture(selection.pointer))selection.element.releasePointerCapture(selection.pointer);if(!selection.active)return;blockClick=true;setTimeout(()=>blockClick=false,350);if(cancel||selection.pages.size>80){writingPageSync(writing.page);if(!cancel)writingError('一次最多选择 80 页');return;}writingReset();writingContinuous.fullDocument=false;writing.pages=selection.pages;writing.selectionMode='multiple';$('#writingSelectionMode').value='multiple';$('#writingPageSelectionToolbar').hidden=false;writingContinuous.anchor=selection.end||selection.start;writingShowPage(writingContinuous.anchor,false);};
 rail.addEventListener('pointerup',()=>finish(false));rail.addEventListener('pointercancel',()=>finish(true));rail.addEventListener('lostpointercapture',()=>finish(true));
 rail.addEventListener('click',e=>{if(blockClick){e.preventDefault();e.stopImmediatePropagation();blockClick=false;}},true);
 rail.title='点击选页，按住拖动连续选择；Alt 拖动取消选择';rail.addEventListener('dragstart',e=>e.preventDefault());
}
function writingConfirmRequests(count,remaining){return new Promise(resolve=>{modal(writingContinuous.fullDocument?'开始全文审核':'开始多页审阅',`<div class="continuous-confirm"><strong>${writing.pages.size} 页 · ${count} 次 AI 请求</strong><p>${writingContinuous.fullDocument?'先综合全文建立审阅意见，再逐页检查内容与版式。':'共享章节提纲、所选源码与相邻正文，依次审阅页面。'}</p>${remaining!==null?'<p>今日剩余 '+remaining+' 次</p>':''}<button type="button" id="writingConfirmStart" class="primary">开始审阅</button></div>`);const dialog=$('#modal'),cancel=()=>resolve(false);dialog.addEventListener('close',cancel,{once:true});$('#writingConfirmStart').onclick=()=>{dialog.removeEventListener('close',cancel);closeModal();resolve(true);};});}
const writingStartOriginal=writingStart;
writingStart=async function(){if(writing.busy)return;const count=writingRequestCount();if(count>1){const budget=await api('ai/usage');if(budget.remaining!==null&&count>budget.remaining)throw new Error('本次需要 '+count+' 次请求，今日剩余 '+budget.remaining+' 次；请缩小范围或在 AI 用量中调整上限');if(!await writingConfirmRequests(count,budget.remaining))return;}return writingStartOriginal();};
const writingSignatureOriginal=writingRequestSignature,writingSettingsOriginal=writingSettings,writingSetSettingsOriginal=writingSetSettings;
writingRequestSignature=()=>writingSignatureOriginal()+':'+(writingContinuous.fullDocument&&writing.mode==='pdf');
writingRequestCount=()=>$('#writingProvider').value==='local'?0:writing.mode==='pdf'?writing.pages.size+(writingContinuous.fullDocument?1:0):$('#writingTask').value==='workflow'?2:1;
writingSettings=()=>({...writingSettingsOriginal(),wholeDocument:writingContinuous.fullDocument});
writingSetSettings=function(value){writingContinuous.fullDocument=!!value.wholeDocument;writingSetSettingsOriginal(value);};
const writingOpenOriginal=writingOpen;writingOpen=async function(...args){if(writing.project!==state?.projectId)writingContinuous.fullDocument=false;return writingOpenOriginal(...args);};
const writingControlsOriginal=writingControls;
writingControls=function(){writingControlsOriginal();const locked=writing.busy||!!state?.running||!!state?.packageBusy;for(const id of ['writingAllPages','writingWholeReview'])$('#'+id).disabled=locked||!writing.doc?.totalPages;$('#writingWorkbench').classList.toggle('is-processing',!!writing.busy);$('#writingWorkbench').setAttribute('aria-busy',String(!!writing.busy));for(const input of $$('[data-continuous-select]'))input.disabled=locked;$('#writingWholeReview').classList.toggle('active',writingContinuous.fullDocument&&writing.mode==='pdf');$('#writingWholeReview').setAttribute('aria-pressed',String(writingContinuous.fullDocument&&writing.mode==='pdf'));if(writing.mode==='pdf')$('#writingTargetLabel').textContent=(writingContinuous.fullDocument?'全文审核':'PDF')+' · '+(writing.pages.size?'第 '+writingCompactPages(writing.pages)+' 页':'未选择');if(writingContinuous.fullDocument&&writing.mode==='pdf'&&writingPrimaryKind()==='generate'&&!writing.busy)$('#writingPrimaryAction').textContent='开始全文审核';};
const writingSetViewOriginal=writingSetView;writingSetView=function(view){writingSetViewOriginal(view);$('#writingPdfToolbar').hidden=view!=='content'||writing.mode!=='pdf';$('#writingSourceToolbar').hidden=view!=='content'||writing.mode!=='source';$('#writingPageSelectionToolbar').hidden=view!=='content'||writing.mode!=='pdf'||writing.selectionMode!=='multiple';};
writingInstallContinuous();writingSetupComparison();writingSetupResize();writingSetupPageRail();
$('#writingPrimaryAction').onclick=writingWatch(writingPrimary);$('#writingSuggest').onclick=writingWatch(writingStart);
$('#writingPageRange').title='最多 80 页；支持 1,3-5，也可 Shift 连选';
$('#writingThumbnailsToggle').click();for(const id of ['writingPdfScroll','writingCompareScroll'])$('#'+id).tabIndex=0;
writingControls();
