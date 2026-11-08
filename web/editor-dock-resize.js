/* Resizable editor dock, request column, and PDF comparison. No AI requests. */
(()=>{
 const workspace=$('#workspace'),dock=$('#logPanel'),panel=$('#editorAiPanel'),pages=$('.editor-ai-effect-pages');
 if(!workspace||!dock||!panel||!pages)return;
 const read=(key,fallback)=>{try{const raw=localStorage.getItem(key),n=raw===null?NaN:Number(raw);return Number.isFinite(n)?n:fallback;}catch{return fallback;}};
 const write=(key,value)=>{try{localStorage.setItem(key,String(value));}catch{}};
 const clamp=(n,low,high)=>Math.max(low,Math.min(high,n));
 const make=(id,label,orientation)=>{const el=document.createElement('div');el.id=id;el.className='editor-dock-resize';el.tabIndex=0;el.setAttribute('role','separator');el.setAttribute('aria-label',label);el.setAttribute('aria-orientation',orientation);el.title=label+' · 双击还原';el.innerHTML='<span></span>';return el;};
 const heightHandle=make('editorDockHeightResize','拖动调整底部面板高度','horizontal');dock.prepend(heightHandle);
 const composeHandle=make('editorAiColumnResize','拖动调整 AI 输入与结果宽度','vertical');$('.editor-ai-compose').after(composeHandle);
 const compareHandle=make('editorAiCompareResize','拖动调整修改前后预览宽度','vertical');pages.querySelector('figure').after(compareHandle);
 let heightRatio=read('studio.editorDockHeight',NaN),composeWidth=read('studio.editorAiComposeWidth',260),compareRatio=read('studio.editorAiCompareRatio',50);
 const layout=()=>{editor?.layout();editorAiDiffEditor?.layout();};
 const height=value=>{const h=workspace.clientHeight;if(h<220)return;heightRatio=clamp(value,Math.min(180,h*.5)/h,(h-100)/h);workspace.classList.add('dock-sized');workspace.style.setProperty('--studio-dock-height',Math.round(h*heightRatio)+'px');heightHandle.setAttribute('aria-valuemin','0');heightHandle.setAttribute('aria-valuemax','100');heightHandle.setAttribute('aria-valuenow',String(Math.round(heightRatio*100)));heightHandle.setAttribute('aria-valuetext',Math.round(h*heightRatio)+' 像素');layout();};
 const compose=value=>{const w=panel.clientWidth;if(w<1)return;composeWidth=clamp(value,Math.min(200,w*.4),Math.max(200,Math.min(560,w*.6,w-280)));panel.style.setProperty('--studio-ai-compose-width',Math.round(composeWidth)+'px');composeHandle.setAttribute('aria-valuemin','200');composeHandle.setAttribute('aria-valuemax',String(Math.round(Math.max(200,Math.min(560,w*.6,w-280)))));composeHandle.setAttribute('aria-valuenow',String(Math.round(composeWidth)));layout();};
 const compare=value=>{compareRatio=clamp(value,20,80);pages.style.setProperty('--studio-effect-left',compareRatio+'fr');pages.style.setProperty('--studio-effect-right',(100-compareRatio)+'fr');compareHandle.setAttribute('aria-valuemin','20');compareHandle.setAttribute('aria-valuemax','80');compareHandle.setAttribute('aria-valuenow',String(Math.round(compareRatio)));};
 const bind=(handle,axis,move,adjust,reset,save)=>{
  let pointer=null,frame=0,last=null;
  const finish=()=>{if(pointer===null)return;pointer=null;cancelAnimationFrame(frame);frame=0;if(last){move(last);last=null;}document.body.classList.remove('dragging','editor-dock-dragging',axis==='y'?'editor-dock-row-dragging':'editor-dock-column-dragging');handle.classList.remove('dragging');save();};
  handle.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();pointer=e.pointerId;handle.setPointerCapture(e.pointerId);document.body.classList.add('dragging','editor-dock-dragging',axis==='y'?'editor-dock-row-dragging':'editor-dock-column-dragging');handle.classList.add('dragging');});
  handle.addEventListener('pointermove',e=>{if(pointer!==e.pointerId)return;last={clientX:e.clientX,clientY:e.clientY};if(!frame)frame=requestAnimationFrame(()=>{frame=0;if(last){move(last);last=null;}});});
  handle.addEventListener('pointerup',e=>{if(pointer!==e.pointerId)return;if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);finish();});
  handle.addEventListener('lostpointercapture',finish);handle.addEventListener('pointercancel',finish);window.addEventListener('blur',finish);
  handle.addEventListener('dblclick',()=>{reset();save();});
  handle.addEventListener('keydown',e=>{const prev=axis==='y'?'ArrowDown':'ArrowLeft',next=axis==='y'?'ArrowUp':'ArrowRight';if(![prev,next,'Home'].includes(e.key))return;e.preventDefault();e.key==='Home'?reset():adjust((e.key===next?1:-1)*(e.shiftKey?3:1));save();});
 };
 bind(heightHandle,'y',e=>{const r=workspace.getBoundingClientRect();height((r.bottom-e.clientY)/r.height);},n=>height((Number.isFinite(heightRatio)?heightRatio:dock.clientHeight/workspace.clientHeight)+n*16/workspace.clientHeight),()=>height(workspace.classList.contains('editor-ai-open') ? .4 : .3),()=>write('studio.editorDockHeight',heightRatio));
 bind(composeHandle,'x',e=>compose(e.clientX-panel.getBoundingClientRect().left),n=>compose(composeWidth+n*16),()=>compose(260),()=>write('studio.editorAiComposeWidth',composeWidth));
 bind(compareHandle,'x',e=>{const r=pages.getBoundingClientRect();compare((e.clientX-r.left)/r.width*100);},n=>compare(compareRatio+n*2),()=>compare(50),()=>write('studio.editorAiCompareRatio',compareRatio));
 const originalExpand=editorAiExpand;editorAiExpand=function(){originalExpand();height(workspace.classList.contains('editor-ai-expanded') ? .65 : .4);write('studio.editorDockHeight',heightRatio);$('#editorAiExpand').title=workspace.classList.contains('editor-ai-expanded')?'还原面板':'展开面板';};$('#editorAiExpand').onclick=editorAiExpand;
 new ResizeObserver(()=>{if(Number.isFinite(heightRatio))height(heightRatio);compose(composeWidth);}).observe(workspace);
 new ResizeObserver(()=>compose(composeWidth)).observe(panel);compare(compareRatio);
})();
