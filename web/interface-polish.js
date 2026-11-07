'use strict';
let packageListRenderKey='',packageListAnimation=null;
const packageReducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function packageScrollState(){
 const list=$('#packageList');list.dataset.scrolled=String(list.scrollTop>2);$('#packageScrollTop').hidden=list.scrollTop<150;
}
function packageListUpdated(){
 const list=$('#packageList'),names=[...list.querySelectorAll('.package-description strong')].map(n=>n.textContent);
 const key=JSON.stringify([packageFilter,packagePage,$('#packageQuery').value.trim(),names]);
 if(key!==packageListRenderKey){
  packageListRenderKey=key;packageListAnimation?.cancel();list.scrollTop=0;
  if(!packageReducedMotion()&&typeof list.animate==='function')packageListAnimation=list.animate([{opacity:.55,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:160,easing:'ease-out'});
 }
 packageScrollState();
}
$('#packageList').addEventListener('scroll',packageScrollState,{passive:true});
$('#packageScrollTop').onclick=()=>{$('#packageList').scrollTo({top:0,behavior:packageReducedMotion()?'auto':'smooth'});$('#packageList').focus({preventScroll:true});};
$('#packageList').addEventListener('keydown',event=>{
 if(event.target!==event.currentTarget||!['Home','End'].includes(event.key))return;
 event.preventDefault();const list=event.currentTarget;list.scrollTo({top:event.key==='Home'?0:list.scrollHeight,behavior:packageReducedMotion()?'auto':'smooth'});
});
packageScrollState();
