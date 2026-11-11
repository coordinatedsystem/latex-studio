'use strict';
const catComparison={key:null,data:null,parts:[],index:0,full:false,zoom:150,ticket:0,diffs:new Map()};
function catComparisonKey(){return state.projectId+':'+studioAssistant.id;}
function catComparisonTabs(){
 const job=studioAssistant.job,active=studioAssistant.surface==='conversation';if(!active)return;
 $$('[data-writing-view]').forEach(button=>{const view=button.dataset.writingView;button.disabled=view==='comparison'?(!job?.verified||!!job?.running):view==='diff'?(!job?.changedPaths?.length||!!job?.running):false;button.classList.toggle('active',view===writing.view);button.setAttribute('aria-pressed',String(view===writing.view));});
}
function catMark(box,side,anchor=false){
 if(!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite))return '';
 const [x,y,r,b]=box.map(n=>Math.max(0,Math.min(1,n)));
 return `<span class="cat-mark ${side} ${anchor?'anchor':''}" style="left:${x*100}%;top:${y*100}%;width:${Math.max(.008,r-x)*100}%;height:${Math.max(.01,b-y)*100}%" title="${anchor?'改动位置的上下文':side==='before'?'删除 / 修改前':'新增 / 修改后'}"></span>`;
}
function catImage(side,page,boxes=[],anchor=false){
 if(!page)return '<p class="cat-page-empty">本版本没有对应页面</p>';
 return `<div class="cat-page-scroll"><div class="cat-page-canvas" style="width:${catComparison.full?100:catComparison.zoom}%"><img decoding="async" loading="lazy" alt="${side==='before'?'修改前':'修改后'}第 ${page} 页" src="/api/ai/assistant/effect-image?id=${studioAssistant.id}&which=${side}&page=${page}&project=${encodeURIComponent(state.projectId)}">${boxes.map(b=>catMark(b,side,anchor)).join('')}</div></div>`;
}
function catPart(change,index){
 const old=change.before[index],after=change.after[index];
 return {change:change.id,kind:change.kind,beforePage:old?.page||change.beforeAnchor?.page||null,afterPage:after?.page||change.afterAnchor?.page||null,beforeBoxes:old?.boxes||[change.beforeAnchor?.box].filter(Boolean),afterBoxes:after?.boxes||[change.afterAnchor?.box].filter(Boolean),beforeAnchor:!old,afterAnchor:!after};
}
function catPaintComparison(){
 const data=catComparison.data,part=catComparison.parts[catComparison.index],host=$('#conversationPdf');if(!data)return;
 const rows=catComparison.full?(data.pagePairs.length?data.pagePairs:Array.from({length:Math.max(data.beforePages,data.afterPages)},(_,i)=>({beforePage:i<data.beforePages?i+1:null,afterPage:i<data.afterPages?i+1:null}))):[part||{beforePage:data.beforePages?1:null,afterPage:data.afterPages?1:null}];
 const usedBefore=new Set(rows.map(p=>p.beforePage)),usedAfter=new Set(rows.map(p=>p.afterPage));
 if(catComparison.full){for(let p=1;p<=data.beforePages;p++)if(!usedBefore.has(p))rows.push({beforePage:p,afterPage:null});for(let p=1;p<=data.afterPages;p++)if(!usedAfter.has(p))rows.push({beforePage:null,afterPage:p});}
 const marks=(side,page)=>data.changes.flatMap(c=>c[side].filter(r=>r.page===page).flatMap(r=>r.boxes));
 const options=(total,page)=>Array.from({length:total},(_,i)=>`<option value="${i+1}" ${page===i+1?'selected':''}>${i+1}</option>`).join('');
 host.innerHTML=`<div class="cat-compare-toolbar"><div><button type="button" id="catPrevious" ${!part||catComparison.index===0?'disabled':''}>←</button><select id="catChange" aria-label="选择改动">${catComparison.parts.map((p,i)=>`<option value="${i}" ${i===catComparison.index?'selected':''}>改动 ${i+1} · 第 ${p.beforePage||'—'} → ${p.afterPage||'—'} 页</option>`).join('')||'<option>未检测到文本差异</option>'}</select><button type="button" id="catNext" ${!part||catComparison.index===catComparison.parts.length-1?'disabled':''}>→</button></div><button type="button" id="catFull">${catComparison.full?'聚焦改动':'全文浏览'}</button><label>缩放 <select id="catZoom" aria-label="对比缩放">${[100,150,200,250].map(n=>`<option value="${n}" ${catComparison.zoom===n?'selected':''}>${n}%</option>`).join('')}</select></label><span class="cat-legend"><i class="before"></i>修改前 <i class="after"></i>修改后</span></div><p class="cat-compare-note">${esc(data.note||'按修改内容对齐，前后页码可以不同。')}${data.truncated?' · 仅显示前 150 处差异':''}</p>${rows.map(p=>`<section class="cat-pdf-row"><figure><figcaption><b>修改前</b><label>第 <select data-cat-page="before" aria-label="修改前页次">${options(data.beforePages,p.beforePage)}</select> 页</label></figcaption>${catImage('before',p.beforePage,p.beforeBoxes||marks('before',p.beforePage),p.beforeAnchor)}</figure><figure><figcaption><b>修改后</b><label>第 <select data-cat-page="after" aria-label="修改后页次">${options(data.afterPages,p.afterPage)}</select> 页</label></figcaption>${catImage('after',p.afterPage,p.afterBoxes||marks('after',p.afterPage),p.afterAnchor)}</figure></section>`).join('')}`;
 $('#catZoom').onchange=e=>{catComparison.zoom=Number(e.target.value);catPaintComparison();};
 $('#catPrevious').onclick=()=>{catComparison.index--;catComparison.full=false;catPaintComparison();};$('#catNext').onclick=()=>{catComparison.index++;catComparison.full=false;catPaintComparison();};$('#catChange').onchange=e=>{catComparison.index=Number(e.target.value);catComparison.full=false;catPaintComparison();};$('#catFull').onclick=()=>{catComparison.full=!catComparison.full;catPaintComparison();};
 $$('[data-cat-page]').forEach(select=>select.onchange=()=>{const side=select.dataset.catPage,figure=select.closest('figure'),canvas=figure.querySelector('.cat-page-scroll');if(canvas)canvas.outerHTML=catImage(side,Number(select.value));});
 if(!catComparison.full)$$('.cat-page-canvas img').forEach(image=>{const focus=()=>{const marker=image.parentElement.querySelector('.cat-mark');if(marker){const scroll=image.closest('.cat-page-scroll');scroll.scrollTop=Math.max(0,parseFloat(marker.style.top)/100*image.clientHeight-90);scroll.scrollLeft=Math.max(0,parseFloat(marker.style.left)/100*image.clientWidth-30);}};image.onload=focus;if(image.complete)focus();});
}
async function catShowComparison(){
 const key=catComparisonKey(),ticket=++catComparison.ticket,host=$('#conversationPdf');host.innerHTML='<p class="cat-loading">正在按内容对齐前后页面…</p>';
 if(catComparison.key!==key||!catComparison.data){const data=await api('ai/assistant/comparison?id='+studioAssistant.id);if(key!==catComparisonKey()||ticket!==catComparison.ticket)return;catComparison.key=key;catComparison.data=data;catComparison.parts=data.changes.flatMap(c=>Array.from({length:Math.max(c.before.length,c.after.length,1)},(_,i)=>catPart(c,i)));catComparison.index=0;catComparison.full=false;}
 if(writing.view==='comparison'&&key===catComparisonKey())catPaintComparison();
}
async function catShowDiff(path=null){
 const key=catComparisonKey(),ticket=++catComparison.ticket,files=studioAssistant.job?.changedPaths||[];path=files.includes(path)?path:files[0];if(!path)return;
 const host=$('#conversationPdf');host.innerHTML='<p class="cat-loading">正在读取源码差异…</p>';const diff=await api('ai/assistant/diff?id='+studioAssistant.id+'&path='+encodeURIComponent(path));if(key!==catComparisonKey()||ticket!==catComparison.ticket||writing.view!=='diff')return;
 const row=(r)=>`<div class="cat-source-row"><div class="${r.kind!=='equal'&&r.beforeLine?'removed':''}"><span>${r.beforeLine||''}</span><code>${esc(r.before)}</code></div><div class="${r.kind!=='equal'&&r.afterLine?'added':''}"><span>${r.afterLine||''}</span><code>${esc(r.after)}</code></div></div>`;
 host.innerHTML=`<div class="cat-compare-toolbar"><label>文件 <select id="catDiffFile">${files.map(f=>`<option ${f===path?'selected':''}>${esc(f)}</option>`).join('')}</select></label><span class="cat-legend"><i class="before"></i>删除 / 修改前 <i class="after"></i>新增 / 修改后</span></div><div class="cat-source-head"><b>修改前</b><b>修改后</b></div>${(diff.blocks||[]).map(b=>`<section class="cat-source-hunk">${b.rows.map(row).join('')}</section>`).join('')||'<p>没有源码差异</p>'}`;$('#catDiffFile').onchange=e=>catShowDiff(e.target.value).catch(e=>conversationNotice(e.message));
}
function catSetView(view,previous){
 if(studioAssistant.surface!=='conversation'||view==='content'){$('#writingWorkbench').classList.remove('cat-comparing');++catComparison.ticket;$('#conversationPdf').hidden=true;return previous(view);}
 if(!['comparison','diff'].includes(view))return previous(view);
 $('#writingWorkbench').classList.add('cat-comparing');writing.view=view;$('#writingContent').hidden=true;$('#writingComparison').hidden=true;$('#writingDiff').hidden=true;$('#conversationPdf').hidden=false;catComparisonTabs();
 const operation=view==='comparison'?catShowComparison():catShowDiff();operation.catch(e=>{if(writing.view===view){$('#conversationPdf').innerHTML=`<p class="cat-loading" role="alert">${esc(e.message)}</p>`;}});
}
