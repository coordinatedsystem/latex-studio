/* Local candidate compilation is automatic; model requests stay explicit. */
const assistantPreview={key:null,timer:null};
function assistantQueuePreview(){
 if(writing.applied||writing.stale||!writing.context||!writing.selected.size){clearTimeout(assistantPreview.timer);assistantPreview.key=null;return;}
 if(writing.busy||state?.running||state?.packageBusy||writing.job?.running||writing.preview?.running||writingSamePreview())return;
 if(writing.requestSignature&&writing.requestSignature!==writingRequestSignature())return;
 const key=JSON.stringify([writing.context.id,writing.job?.id,[...writing.selected].sort((a,b)=>a-b)]);
 if(assistantPreview.key===key)return;
 assistantPreview.key=key;clearTimeout(assistantPreview.timer);
 assistantPreview.timer=setTimeout(()=>{
  if(writing.busy||writing.applied||writing.stale||!writing.context||key!==JSON.stringify([writing.context.id,writing.job?.id,[...writing.selected].sort((a,b)=>a-b)]))return;
  writingWatch(writingPreview)();
 },300);
}
async function assistantPreset(kind){
 if(writing.busy)return;
 writingReset();$('.writing-request').classList.remove('compact');$('#writingRequestToggle').textContent='收起要求';
 if(kind==='references'){
  $('#writingFile').value=prefs.main;await writingSetMode('source');$('#writingSelectFile').click();
  $('#writingInstruction').value='删除当前文件的参考文献部分、文献生成命令及正文中的引用调用，保留其他正文、公式和文档结构。';
 }else $('#writingInstruction').value=kind==='shorten'?'精简所选内容，删除重复论述，保留关键结论。':'按我的要求重写所选内容，保持上下文连贯。';
 $('#writingTask').value='polish';$('#writingProvider').value='deepseek';writingTaskControls();writingControls();$('#writingInstruction').focus();
}
function assistantRefreshInstall(){
 $('.writing-request').insertAdjacentHTML('afterbegin','<div class="assistant-intro"><span>写下目标，交给 AI 修改</span><small>支持删节、重写和结构调整。候选会先编译预览，再由你确认。</small></div><div class="assistant-presets"><button type="button" data-assistant-preset="references">删除参考文献</button><button type="button" data-assistant-preset="shorten">精简内容</button><button type="button" data-assistant-preset="rewrite">重写选区</button></div>');
 $$('[data-assistant-preset]').forEach(button=>button.onclick=writingWatch(()=>assistantPreset(button.dataset.assistantPreset)));
 $('#writingInstruction').placeholder='例如：删除参考文献；把这一节缩短一半；重新组织这一段的论证。';
 $('#writingPreview').textContent='重新生成预览';
 $('#writingApply').textContent='确认应用此版本';
}
writingControls=uiPatchRegistry.wrap('writingControls',writingControls,'assistant-refresh.js',previous=>function(){previous();$$('[data-assistant-preset]').forEach(b=>b.disabled=writing.busy||!!state?.running);assistantQueuePreview();});
assistantRefreshInstall();
