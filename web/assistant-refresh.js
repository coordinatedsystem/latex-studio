/* Local candidate compilation is automatic; model requests stay explicit. */
const assistantPreview={key:null,timer:null};
function assistantQueuePreview(){
 if(writing.applied||writing.stale||!writing.context||!writing.selected.size){clearTimeout(assistantPreview.timer);return;}
 if(writing.busy||state?.running||state?.packageBusy||writing.job?.running||writing.preview?.running||writingSamePreview())return;
 if(writing.requestSignature&&writing.requestSignature!==writingRequestSignature())return;
 const key=JSON.stringify([writing.context.id,writing.job?.id]);
 const selection=JSON.stringify([...writing.selected].sort((a,b)=>a-b));
 if(assistantPreview.key===key)return;
 assistantPreview.key=key;clearTimeout(assistantPreview.timer);
 assistantPreview.timer=setTimeout(()=>{
  if(writing.busy||writing.applied||writing.stale||!writing.context||key!==JSON.stringify([writing.context.id,writing.job?.id])||selection!==JSON.stringify([...writing.selected].sort((a,b)=>a-b)))return;
  writingWatch(writingPreview)();
 },300);
}
function assistantRefreshInstall(){
 $('#writingInstruction').placeholder='输入修改要求…';
 const steps=$('.writing-steps');
 steps.setAttribute('aria-label','任务进度');
 const labels=['选择','修改','预览','完成'];
 steps.querySelectorAll('li').forEach((step,index)=>{
  step.replaceChildren();
  const dot=document.createElement('span');dot.setAttribute('aria-hidden','true');
  step.append(dot,document.createTextNode(labels[index]));
 });
}
writingControls=uiPatchRegistry.wrap('writingControls',writingControls,'assistant-refresh.js',previous=>function(){previous();assistantQueuePreview();});
assistantRefreshInstall();
