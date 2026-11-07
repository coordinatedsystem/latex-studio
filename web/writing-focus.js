'use strict';
let writingFocusState=null,writingFocusZoom=false,writingFocusTicket=0;
function writingCrop(box){
 const w=Math.min(1,Math.max(.4,box[2]-box[0]+.08)),h=Math.min(1,Math.max(.09,box[3]-box[1]+.07));
 return {x:Math.max(0,Math.min(1-w,(box[0]+box[2]-w)/2)),y:Math.max(0,Math.min(1-h,(box[1]+box[3]-h)/2)),w,h};
}
function writingFocusFrame(which,box,number){
 const frame=$('#writing'+which+'Window'),image=$('#writing'+which),marker=$('#writing'+which+'Marker');
 frame.classList.toggle('focus-crop',!!box&&writingFocusZoom);marker.hidden=!box;
 image.style.width='';image.style.left='';image.style.top='';frame.style.aspectRatio='';
 if(!box)return;
 const area=writingFocusZoom?writingCrop(box):{x:0,y:0,w:1,h:1};
 if(writingFocusZoom){const ratio=image.naturalHeight&&image.naturalWidth?image.naturalHeight/image.naturalWidth:Math.SQRT2;frame.style.aspectRatio=String(area.w/(ratio*area.h));image.style.width=100/area.w+'%';image.style.left=-area.x/area.w*100+'%';image.style.top=-area.y/area.h*100+'%';}
 marker.style.left=(box[0]-area.x)/area.w*100+'%';marker.style.top=(box[1]-area.y)/area.h*100+'%';marker.style.width=(box[2]-box[0])/area.w*100+'%';marker.style.height=(box[3]-box[1])/area.h*100+'%';marker.dataset.number=number==null?'改动':number;
}
function writingDrawFocus(){
 writingFocusFrame('Before',writingFocusState?.before?.box,writingFocusState?.index==null?null:writingFocusState.index+1);
 writingFocusFrame('After',writingFocusState?.after?.box,writingFocusState?.index==null?null:writingFocusState.index+1);
 $('#writingFocusToggle').textContent=writingFocusZoom?'整页':'聚焦改动';
}
function writingClearFocus(){
 ++writingFocusTicket;
 writingFocusState=null;writingFocusZoom=false;writingDrawFocus();$('#writingPdfSheet').classList.remove('focus-page');$('#writingPdfSheet').style.width='';$('#writingPdfScroll').classList.remove('focus-page-scroll');$('#writingResetPageFocus').hidden=true;
}
const writingNormalComparison=writingRenderComparison;
writingRenderComparison=function(page=null){writingClearFocus();writingNormalComparison(page);};
function writingDiffFocus(index){
 writingSetView('diff');writingShowDiff();const edit=writing.result.edits[index],line=Array.from(writing.context.source).slice(0,edit.start).join('').split('\n').length;
 writingDiffEditor?.getOriginalEditor().revealLineInCenter(line);
}
async function writingFocusChange(index){
 const edit=writing.result?.edits?.[index];if(!edit)return;
 const ticket=++writingFocusTicket,contextId=writing.context.id;
 writing.focusedEdit=index;$$('[data-writing-card]').forEach(el=>el.classList.toggle('focused',Number(el.dataset.writingCard)===index));
 if(writing.mode==='source'){
  if(writing.stale){writingDiffFocus(index);return;}
  writingSetView('content');const offset=(writing.context.start||0)+edit.start,a=Array.from(writing.full).slice(0,offset).join('').length,b=a+edit.before.length;
  const start=writingModel.getPositionAt(a),end=writingModel.getPositionAt(b),range=new monacoApi.Range(start.lineNumber,start.column,end.lineNumber,end.column);
  writingEditor.revealRangeInCenter(range);writingDecorations=writingEditor.deltaDecorations(writingDecorations,[{range,options:{className:'writing-source-focus',isWholeLine:false}}]);return;
 }
 if(writing.stale&&!writing.preview?.success){writingDiffFocus(index);return;}
 const preview=writingSamePreview()?writing.preview.id:null,query='id='+encodeURIComponent(writing.context.id)+'&index='+index+(edit.key?'&key='+encodeURIComponent(edit.key):'')+(preview?'&preview='+preview:'');
 const result=await api('ai/page-focus?'+query);
 if(ticket!==writingFocusTicket||contextId!==writing.context?.id||writing.result?.edits?.[index]?.key!==edit.key||preview!==(writingSamePreview()?writing.preview.id:null))return;
 if(result.kind==='source'){writingDiffFocus(index);writingStatus('此项修改的是源码设置，可在整页预览中确认效果。');return;}
 if(preview&&result.after){
  writingNormalComparison(result.page);writingSetView('comparison');
  $$('[data-writing-compare]').find(b=>b.dataset.writingCompare==='split').click();
  writingFocusState=result;writingFocusZoom=true;
  $('#writingBefore').src='/api/ai/focus-image?'+query+'&which=before';$('#writingAfter').src='/api/ai/focus-image?'+query+'&which=after';
  $('#writingCompareMeta').textContent='修改 '+(index+1)+' · 原第 '+(result.before?.page||result.page)+' 页 → 新第 '+result.after.page+' 页 · '+result.label;
  writingDrawFocus();$('#writingCompareScroll').scrollTop=0;
 }else if(result.before){
  writingSetView('content');writingShowPage(result.before.page);const sheet=$('#writingPdfSheet'),scroll=$('#writingPdfScroll'),box=result.before.box,marker=$('#writingPdfHighlight');
  sheet.classList.add('focus-page');scroll.classList.add('focus-page-scroll');sheet.style.width=Math.max(1000,scroll.clientWidth*1.65)+'px';$('#writingResetPageFocus').hidden=false;
  marker.hidden=false;marker.textContent=String(index+1);marker.style.left=box[0]*100+'%';marker.style.top=box[1]*100+'%';marker.style.width=(box[2]-box[0])*100+'%';marker.style.height=(box[3]-box[1])*100+'%';
  const position=()=>{scroll.scrollTo({left:sheet.offsetLeft+sheet.clientWidth*(box[0]+box[2])/2-scroll.clientWidth/2,top:sheet.offsetTop+sheet.clientHeight*(box[1]+box[3])/2-scroll.clientHeight/2,behavior:'smooth'});};
  if($('#writingPdfImage').complete&&$('#writingPdfImage').naturalWidth)requestAnimationFrame(position);else $('#writingPdfImage').addEventListener('load',position,{once:true});
 }else writingDiffFocus(index);
}
writingFocusEdit=index=>writingWatch(()=>writingFocusChange(index))();
$('#writingFocusToggle').onclick=()=>{
 if(!writing.preview?.success)return;
 if(!writingFocusState){const p=writing.preview.pages?.find(p=>p.page===writing.comparePage)||writing.preview.pages?.[0];if(!p?.bounds){writingStatus('本页没有可定位的像素变化，可查看源码差异。');return;}writingFocusState={index:null,before:{box:p.bounds},after:{box:p.bounds}};}
 if(!$('#writingOverlay').hidden)$$('[data-writing-compare]').find(b=>b.dataset.writingCompare==='split').click();
 writingFocusZoom=!writingFocusZoom;writingDrawFocus();
};
for(const side of ['Before','After'])$('#writing'+side).addEventListener('load',writingDrawFocus);
$('#writingResetPageFocus').onclick=writingClearFocus;
for(const button of $$('[data-writing-compare]'))button.addEventListener('click',()=>{if(button.dataset.writingCompare==='overlay'){writingFocusZoom=false;writingDrawFocus();}});
