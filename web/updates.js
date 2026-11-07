'use strict';
let updatePoll=null;
async function showUpdates(){
 const s=await api('updates');
 modal('版本与更新',`<div class="update-product"><strong>LaTeX Studio</strong><span>v${esc(s.version)} · 稳定版</span></div><div class="update-status" id="updateStatus" role="status">${esc(s.job.stage)}</div><div id="updateRelease"></div><div class="update-actions"><button type="button" id="updateCheck" class="primary">检查更新</button><button type="button" id="updateDownload" class="secondary" hidden>下载安装包</button><button type="button" id="updateInstall" class="primary" hidden>运行安装包</button></div><details class="update-config"><summary>更新设置</summary><label class="field-row"><span>启动时检查</span><input id="updateAutomatic" type="checkbox" ${s.automatic?'checked':''}></label><label class="field"><span>GitHub 只读凭据（可选）${s.configured?'（已保存）':''}</span><input id="updateToken" type="password" autocomplete="new-password" placeholder="留空保留已保存的凭据"></label><p>公开仓库无需填写。私有仓库仅需 Contents 读取权限，本机加密保存。</p><button id="updateSave" type="button" class="secondary">保存设置</button><button id="updateClear" type="button" class="text-button">清除凭据</button></details><a href="https://github.com/coordinatedsystem/latex-studio" target="_blank" rel="noreferrer">项目仓库 ↗</a>`);
 const render=s=>{
  if(!$('#updateStatus'))return;
  $('#updateStatus').textContent=s.job.error||s.job.stage+(s.job.size?' · '+Math.round((s.job.downloaded||0)/s.job.size*100)+'%':'');
  $('#updateRelease').textContent=s.release?(s.release.available?'可更新至 v':'最新版本 v')+s.release.version+(s.release.notes?'\n'+s.release.notes:''):'';
  $('#updateCheck').disabled=s.job.running;$('#updateDownload').hidden=!s.release?.available||s.ready;$('#updateDownload').disabled=s.job.running;$('#updateInstall').hidden=!s.ready;
 };
 const watch=fn=>async()=>{try{render(await fn())}catch(e){if($('#updateStatus'))$('#updateStatus').textContent=e.message}};
 $('#updateCheck').onclick=async()=>{$('#updateCheck').disabled=true;$('#updateStatus').textContent='正在检查…';try{render(await api('updates/check',{}))}catch(e){$('#updateStatus').textContent=e.message}finally{if($('#updateCheck'))$('#updateCheck').disabled=false}};
 $('#updateDownload').onclick=watch(async()=>{const next=await api('updates/download',{});clearInterval(updatePoll);updatePoll=setInterval(async()=>{try{const next=await api('updates');render(next);if(!next.job.running)clearInterval(updatePoll)}catch{clearInterval(updatePoll)}},700);return next;});
 $('#updateInstall').onclick=async()=>{try{await saveAll();await api('updates/install',{});$('#updateStatus').textContent='安装向导已打开，完成后重新启动应用'}catch(e){$('#updateStatus').textContent=e.message}};
 $('#updateSave').onclick=watch(async()=>{const value=await api('updates/settings',{automatic:$('#updateAutomatic').checked,token:$('#updateToken').value});$('#updateToken').value='';toast('更新设置已保存');return value});
 $('#updateClear').onclick=watch(async()=>{const value=await api('updates/settings',{automatic:$('#updateAutomatic').checked,clearToken:true});$('#updateToken').value='';toast('更新凭据已清除');return value});render(s);
}
$('#modal').addEventListener('close',()=>clearInterval(updatePoll));
const updateOldSettings=showSettings;showSettings=async function(){await updateOldSettings();const section=document.createElement('div');section.className='settings-section';section.innerHTML='<h3>版本与更新</h3><div class="update-setting-row"><span>LaTeX Studio <strong id="settingsVersion"></strong></span><button type="button" class="secondary" id="settingsUpdates">管理更新</button></div>';$('#applySettings').parentElement.before(section);$('#settingsUpdates').onclick=()=>showUpdates().catch(e=>toast(e.message,true));const s=await api('updates');if($('#settingsVersion'))$('#settingsVersion').textContent='v'+s.version;};
commands.push(['版本与更新','updates','']);const updateOldRun=run;run=async function(action){if(action==='updates')return showUpdates();return updateOldRun(action);};
// Background checks are opt-in; a notification never installs an update.
setTimeout(async()=>{try{const s=await api('updates');if(s.automatic){const next=await api('updates/check',{});if(next.release?.available)toast('LaTeX Studio 有新版本，可在设置中查看')}}catch{}},5000);
