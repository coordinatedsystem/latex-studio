'use strict';
function writingDesignUpdate(){
 const kind=writingPrimaryKind(),titles={generate:'准备修改',preview:'审阅建议',apply:'确认效果',continue:'修改完成',rebase:'重新关联',retry:'继续处理'};
 $('#writingPhaseTitle').textContent=writing.busy?(writing.preview?.running?'正在生成预览':'正在处理'):titles[kind]||'写作助手';
 $('#writingPhaseNumber').textContent=(writing.applied?4:writing.preview?.success?3:writing.result?2:1)+' / 4';
 $('#writingWorkbench').dataset.empty=String(!writing.result);
 const empty=$('#writingResults .writing-result-empty');
 if(empty&&!writing.result&&!writing.busy){
  empty.innerHTML='<strong>修改建议将在这里显示</strong><p>选择左侧内容，写下要求后获取建议。</p>';
 }
}
writingControls=uiPatchRegistry.wrap('writingControls',writingControls,'writing-design.js',previous=>function(){previous();writingDesignUpdate();});
writingStep=uiPatchRegistry.wrap('writingStep',writingStep,'writing-design.js',previous=>function(step){previous(step);writingDesignUpdate();});
writingRenderResult=uiPatchRegistry.wrap('writingRenderResult',writingRenderResult,'writing-design.js',previous=>function(){previous();writingDesignUpdate();});
writingDesignUpdate();
