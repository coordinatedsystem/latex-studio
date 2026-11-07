'use strict';
function writingDesignUpdate(){
 const kind=writingPrimaryKind(),titles={generate:'准备修改',preview:'审阅建议',apply:'确认效果',continue:'修改完成',rebase:'重新关联',retry:'继续处理'};
 $('#writingPhaseTitle').textContent=writing.busy?(writing.preview?.running?'正在生成预览':'正在处理'):titles[kind]||'写作助手';
 $('#writingPhaseNumber').textContent=(writing.applied?4:writing.preview?.success?3:writing.result?2:1)+' / 4';
 $('#writingWorkbench').dataset.empty=String(!writing.result);
 const empty=$('#writingResults .writing-result-empty');
 if(empty&&!writing.result&&!writing.busy){
  if(!empty.querySelector('.writing-presets')){
   empty.innerHTML='<span>✦</span><strong>你想如何改进文稿？</strong><div class="writing-presets"><button type="button" data-writing-preset="format">排版优化</button><button type="button" data-writing-preset="correct">检查纠错</button><button type="button" data-writing-preset="translate">翻译</button></div>';
   empty.querySelectorAll('[data-writing-preset]').forEach(button=>button.onclick=()=>{
    if(writing.busy||state?.running||state?.packageBusy)return;
    $('#writingTask').value=button.dataset.writingPreset;writingTaskControls();writingRemember();$('#writingInstruction').focus();
   });
  }
  empty.querySelectorAll('[data-writing-preset]').forEach(button=>{button.setAttribute('aria-pressed',String(button.dataset.writingPreset===$('#writingTask').value));button.disabled=!!state?.running||!!state?.packageBusy;});
 }
}
const writingDesignOldControls=writingControls;writingControls=function(){writingDesignOldControls();writingDesignUpdate();};
const writingDesignOldStep=writingStep;writingStep=function(step){writingDesignOldStep(step);writingDesignUpdate();};
const writingDesignOldResult=writingRenderResult;writingRenderResult=function(){writingDesignOldResult();writingDesignUpdate();};
writingDesignUpdate();
