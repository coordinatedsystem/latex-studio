'use strict';
let homeThumbnailKey='',packageDetailName='',packageDetailTrigger=null;
function homeFeaturedRender(){
 const info=hubOverview;if(!info)return;
 const current=info.current,recent=(info.recent||[]).find(p=>p.id===current.id);
 $('#homeFeaturedName').textContent=current.name||recent?.name||'当前文档';
 $('#homeFeaturedFile').textContent=(current.main||'')+(recent?.opened?' · '+recent.opened:'');
 $('#homeFeaturedPath').textContent=current.root||'';$('#homeFeaturedPath').title=current.root||'';
 $('#homeProjectCount').textContent=(info.recent||[]).length+' 个最近项目';
 const ready=state?.projectId===current.id&&state?.hasPdf,key=ready?current.id+':'+state.pdfVersion:'';
 if(key===homeThumbnailKey)return;homeThumbnailKey=key;
 const img=$('#homePreviewImage');img.hidden=true;$('#homePreviewPlaceholder').hidden=false;
 if(!ready){img.removeAttribute('src');return;}
 img.src='/api/review/page?project='+encodeURIComponent(current.id)+'&page=1&version='+encodeURIComponent(state.pdfVersion);
}
$('#homePreviewImage').onload=()=>{if(homeThumbnailKey){$('#homePreviewImage').hidden=false;$('#homePreviewPlaceholder').hidden=true;}};
$('#homePreviewImage').onerror=()=>{$('#homePreviewImage').hidden=true;$('#homePreviewPlaceholder').hidden=false;};
const homeDesignOldRender=renderHome;renderHome=function(){homeDesignOldRender();homeFeaturedRender();};
const homeDesignOldNotify=hubNotifyState;hubNotifyState=function(next){homeDesignOldNotify(next);if(document.body.dataset.view==='home')homeFeaturedRender();};
function packageDetailClose(focus=true){$('#packageDetails').hidden=true;packageDetailName='';if(focus&&packageDetailTrigger?.isConnected)packageDetailTrigger.focus();packageDetailTrigger=null;}
function packageDetailRender(p){
 $('#packageDetailsTitle').textContent=p.package;
 const status=p.corrupt?'缓存异常':p.verified?'已验证':p.cached?'已缓存':p.removed?'已移除':'未缓存';
 $('#packageDetailsBody').innerHTML=`<p>${esc(p.description||'')}</p><dl><dt>文件</dt><dd>${esc(p.name)}</dd><dt>分类</dt><dd>${esc(p.category||'—')}</dd><dt>大小</dt><dd>${esc(bytesLabel(p.size))}</dd><dt>状态</dt><dd>${status}</dd><dt>关联资源</dt><dd>${Number(p.resources)||0} 个</dd>${p.verification?'<dt>验证</dt><dd>'+esc(p.verification)+'</dd>':''}</dl><code>${esc((p.kind==='class'?'\\documentclass':'\\usepackage')+'{'+p.package+'}')}</code>`;
 $('#packageDetailsActions').innerHTML=`${p.cached?'<button type="button" id="packageDetailsUse" class="primary">查看用法</button><button type="button" id="packageDetailsCheck" class="secondary">检查</button>':'<button type="button" id="packageDetailsInstall" class="primary">下载并验证</button>'}`;
 const bind=(id,fn)=>{const button=$('#'+id);if(button){button.disabled=!!packageData?.job?.running;button.onclick=()=>fn().catch(e=>toast(e.message,true));}};
 bind('packageDetailsUse',()=>insertPackage(p));bind('packageDetailsCheck',()=>packageAction('check',p));bind('packageDetailsInstall',()=>packageAction('install',p));
}
function packageDetailOpen(p,trigger){packageDetailName=p.name;packageDetailTrigger=trigger;packageDetailRender(p);$('#packageDetails').hidden=false;$('#packageDetailsClose').focus();}
function packageDesignRender(){
 $('#packageListTitle').textContent=({all:'全部宏包',cached:'已缓存',available:'未缓存',removed:'已移除'})[packageFilter]||'宏包';
 $$('#packageList .package-description strong').forEach((strong,i)=>{
  const button=document.createElement('button');button.type='button';button.className='package-name-button';button.setAttribute('aria-label','查看 '+packageData.items[i].package+' 详情');
  strong.replaceWith(button);button.append(strong);button.onclick=()=>packageDetailOpen(packageData.items[i],button);
 });
 if(packageDetailName){const p=packageData.items.find(p=>p.name===packageDetailName);if(p)packageDetailRender(p);else packageDetailClose(false);}
}
const packageDesignOldRender=renderPackages;renderPackages=function(data){packageDesignOldRender(data);packageDesignRender();};
$('#packageDetailsClose').onclick=()=>packageDetailClose();
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#packageDetails').hidden&&!$('#modal').open){packageDetailClose();e.preventDefault();}});
const packageDesignOldView=hubView;hubView=function(view){if(view!=='packages')packageDetailClose(false);packageDesignOldView(view);if(view==='home')homeFeaturedRender();};
if(hubOverview)homeFeaturedRender();if(packageData)packageDesignRender();
