'use strict';
let hubOverview=null,hubOverviewBusy=false,hubLastProject='',hubSwitching=false;
let packageFilter='all',packagePage=0,packageData=null,packageQueryTimer,packageRequest=0,packageBusyRequest=false,packageLastJob='',packageLastRunning=false,packagePollBusy=false;

function bytesLabel(value){return value>=1048576?(value/1048576).toFixed(1)+' MB':value>=1024?(value/1024).toFixed(1)+' KB':value+' B';}
function hubView(view){
 if(view!=='editor'&&$('#editorToolPanel')){$('#editorToolPanel').hidden=true;$('#editorToolsMenu').open=false;}
 hideTooltip();if(view!=='editor'&&pdfPhase==='loading'){++pdfTicket;pdfAbort?.abort();lastPdf=0;}
 document.body.dataset.view=view;$$('[data-nav]').forEach(b=>{b.classList.toggle('active',b.dataset.nav===view);b.setAttribute('aria-current',b.dataset.nav===view?'page':'false');});
 if(view==='editor'){requestAnimationFrame(()=>{editor?.layout();if(state?.hasPdf&&(typeof editorAiHoldPdf!=='function'||!editorAiHoldPdf(state)))setPdf(state.pdfVersion);if(models.get(active)?.model)editor?.focus();});}
 if(view==='home')loadHubOverview().catch(e=>toast(e.message,true));
 if(view==='packages')loadPackages().catch(e=>toast(e.message,true));
}
async function loadHubOverview(){
 if(hubOverviewBusy)return;hubOverviewBusy=true;try{hubOverview=await api('overview');renderHome();}finally{hubOverviewBusy=false;}
}
function renderHome(){
 const info=hubOverview;if(!info)return;
 $('#engineBadge').textContent=info.engineReady?'就绪':'未找到编译器';$('#engineBadge').className='state-badge '+(info.engineReady?'success':'warning');
 $('#environmentInfo').innerHTML=`<span>编译器 <code>${esc(info.runtime)}</code></span><span>宏包缓存 <code>${esc(info.cache)}</code></span>`;
 const recent=info.recent||[];$('#recentProjects').innerHTML=recent.length?recent.map((p,i)=>`<article class="recent-card ${p.id===info.current.id?'current':''}"><div class="recent-document">${icon('pdf')}</div><button class="recent-open" data-recent="${i}" ${p.exists?'':'disabled'}><strong>${esc(p.name)}</strong><span>${esc(p.main)}<span class="recent-date">${esc(p.opened||'')}</span></span><code>${esc(p.root)}</code></button><div class="recent-card-actions">${p.id===info.current.id?'<span class="state-badge success">当前</span>':''}${!p.exists?'<span class="state-badge warning">路径不存在</span>':''}<button class="tiny" data-forget="${i}" title="从最近列表移除，不删除文件" aria-label="从最近列表移除">${icon('close')}</button></div></article>`).join(''):'<p class="hub-empty">还没有项目。可以新建文档，或导入已有的 .tex 文件夹。</p>';
 $$('[data-recent]').forEach(b=>b.onclick=()=>hubSwitch('projects/open',{path:recent[+b.dataset.recent].root}).catch(e=>toast(e.message,true)));
 $$('[data-forget]').forEach(b=>b.onclick=async()=>{try{await api('projects/forget',{id:recent[+b.dataset.forget].id});await loadHubOverview();}catch(e){toast(e.message,true);}});
}
async function hubSwitch(route,payload){
 if(hubSwitching)throw new Error('项目操作正在进行，请稍候');
 if(state?.running||state?.packageBusy)throw new Error('请等待编译或宏包任务结束后再切换项目');
 hubSwitching=true;try{await saveAll();const result=await api(route,payload);if(result.cancelled){closeModal();return;}closeModal();for(let i=0;i<25&&state?.projectId!==result.projectId;i++){await poll();if(state?.projectId!==result.projectId)await new Promise(resolve=>setTimeout(resolve,100));}if(state?.projectId!==result.projectId)throw new Error('项目已打开，但本页尚未同步；请先保留未保存内容，再刷新页面。');hubView('editor');await loadHubOverview();toast(result.imported?'已导入 '+result.imported+' 个文件'+(result.skipped?.length?'，忽略 '+result.skipped.length+' 个非项目文件':''):'项目已打开');}finally{hubSwitching=false;}
}
async function newProjectDialog(){
 modal('新建文档',`<label class="field"><span>项目名称</span><input id="newProjectName" value="我的文档" autocomplete="off"></label><div class="field"><span>初始模板</span><div class="template-options"><label><input type="radio" name="projectTemplate" value="minimal" checked><strong>简洁文章</strong><span>中文字体、页边距与基础公式</span></label><label><input type="radio" name="projectTemplate" value="report"><strong>学术报告</strong><span>标题、章节、公式和结论</span></label></div></div><div class="dialog-actions"><button type="button" class="secondary" id="newProjectCancel">取消</button><button type="button" class="primary" id="newProjectCreate">创建并打开</button></div>`);
 $('#newProjectCancel').onclick=closeModal;$('#newProjectCreate').onclick=async()=>{const name=$('#newProjectName').value.trim();if(!name){$('#newProjectName').focus();return;}const template=$('input[name=projectTemplate]:checked').value;$('#newProjectCreate').disabled=true;try{await hubSwitch('projects/new',{name,template});}catch(e){toast(e.message,true);if($('#newProjectCreate'))$('#newProjectCreate').disabled=false;}};
 $('#newProjectName').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('#newProjectCreate').click();}};setTimeout(()=>{$('#newProjectName').focus();$('#newProjectName').select();},30);
}
function importProjectDialog(){
 modal('导入项目',`<p>导入会创建独立副本。带有图片、参考文献或自定义宏包的项目，请选择整个文件夹以保留相对路径。</p><div class="import-choices"><button id="importTexChoice" class="snippet-card" type="button">${icon('file')}<strong>选择 .tex 与配套文件</strong><small>适合单文件文档，或同目录中的配套文件</small></button><button id="importFolderChoice" class="snippet-card" type="button">${icon('folder')}<strong>选择项目文件夹</strong><small>保留目录结构，自动识别主文档</small></button></div><p class="import-limits">单文件最多 24 MB；整个项目最多 90 MB。</p>`);
 $('#importTexChoice').onclick=()=>$('#projectFileInput').click();$('#importFolderChoice').onclick=()=>$('#projectFolderInput').click();
}
async function encodeFile(file){const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(binary);}
async function importChosenFiles(files,folder=false){
 if(!files.length)return;const total=files.reduce((n,f)=>n+f.size,0);if(total>90*1048576)throw new Error('项目超过 90 MB，请去掉视频、缓存或大型无关文件后再导入');if(files.some(f=>f.size>24*1048576))throw new Error('存在超过 24 MB 的文件');
 const defaultName=folder?files[0].webkitRelativePath.split('/')[0]:files.find(f=>f.name.toLowerCase().endsWith('.tex'))?.name.replace(/\.tex$/i,'')||'导入项目';
 const name=await inputDialog('导入项目','项目名称',defaultName,'文件会复制到项目库，原文件保留。');if(!name)return;
 modal('正在导入','<div class="import-progress"><span class="spinner"></span><strong id="importProgress">准备项目文件…</strong></div>');
 try{const uploaded=[];for(let i=0;i<files.length;i++){const file=files[i],path=folder?file.webkitRelativePath.split('/').slice(1).join('/'):file.name;if(!path)continue;$('#importProgress').textContent=`读取 ${i+1} / ${files.length}：${file.name}`;uploaded.push({path,content:await encodeFile(file)});}$('#importProgress').textContent='保存项目并识别主文档…';await hubSwitch('projects/import',{name,files:uploaded});}catch(e){closeModal();throw e;}
}
async function openNativeProject(){
 modal('打开本地文档','<div class="import-progress"><span class="spinner"></span><strong>请在文件选择器中选择 .tex 主文档…</strong></div>');
 try{await hubSwitch('projects/open',{pick:true});}catch(e){closeModal();throw e;}
}
async function openProjectPath(){const path=await inputDialog('打开本地项目','.tex 文件或文件夹的完整路径','','例如 D:\\文档\\论文\\main.tex。此操作直接编辑原项目；如需副本，请使用导入。');if(path)await hubSwitch('projects/open',{path});}

async function loadPackages(){
 const request=++packageRequest;const query=$('#packageQuery').value.trim();$('#packageResultCount').textContent='正在搜索…';$('#packageList').setAttribute('aria-busy','true');
 try{const data=await api('packages?query='+encodeURIComponent(query)+'&filter='+packageFilter+'&page='+packagePage);if(request!==packageRequest)return;packageData=data;packagePage=data.page;renderPackages(data);renderPackageJob(data.job);}catch(e){if(request!==packageRequest)return;$('#packageList').innerHTML=`<div class="hub-empty error">${esc(e.message)}</div>`;$('#packageResultCount').textContent='读取失败';}finally{if(request===packageRequest)$('#packageList').setAttribute('aria-busy','false');}
}
function renderPackages(data){
 $('#catalogCount').textContent=data.catalogCount.toLocaleString();$('#cachedPackageCount').textContent=data.cachedPackages.toLocaleString();$('#cachedResourceCount').textContent=data.cachedResources.toLocaleString();$('#cacheSize').textContent=bytesLabel(data.cacheBytes);$('#packageCachePath').textContent=data.cachePath;$('#packageResultCount').textContent=data.total+' 项结果';$('#packagePageInfo').textContent=(data.page+1)+' / '+data.pages;$('#packagePrev').disabled=data.page<=0;$('#packageNext').disabled=data.page>=data.pages-1;
 $('#packageList').innerHTML=data.items.length?data.items.map((p,i)=>{
  const status=p.corrupt?'<span class="state-badge warning">缓存异常</span>':p.verified?'<span class="state-badge success">已验证</span>':p.cached?'<span class="state-badge neutral">已缓存</span>':p.removed?'<span class="state-badge warning">已移除</span>':'<span class="state-badge available">未缓存</span>';
  let actions=p.cached?`<button class="text-button" data-pkg-action="check" data-package-index="${i}">检查</button><button class="text-button" data-pkg-action="repair" data-package-index="${i}">重装</button><button class="text-button danger-text" data-pkg-action="remove" data-package-index="${i}" ${p.protected?'disabled title="核心编译资源不能移除"':''}>移除</button>`:`${p.removed?`<button class="secondary" data-pkg-action="restore" data-package-index="${i}">恢复</button>`:''}<button class="primary" data-pkg-action="install" data-package-index="${i}">${p.corrupt?'修复缓存':'下载并验证'}</button>`;
  if(p.cached)actions=`<button class="tiny" data-package-insert="${i}" title="${p.kind==='class'?'查看文档类用法':'插入到当前主文档'}" aria-label="查看或插入宏包用法">${icon('braces')}</button>`+actions;
  return `<article class="package-row"><div class="package-symbol ${p.kind==='class'?'class-symbol':''}">${icon(p.kind==='class'?'file':'braces')}</div><div class="package-description"><div><strong>${esc(p.package)}</strong>${p.protected?'<span class="core-label">核心</span>':''}<span class="category-label">${esc(p.category)}</span></div><p>${esc(p.description)}</p><code>${esc(p.name)} · ${bytesLabel(p.size)}${p.resources?' · '+p.resources+' 个关联资源':''}</code></div><div class="package-status" title="${esc(p.verification||'主文件缓存状态；依赖可通过下载验证或实际编译补全')}">${status}</div><div class="package-row-actions">${actions}</div></article>`;
 }).join(''):'<div class="hub-empty">没有找到匹配项。可以试试宏包英文名，或切换筛选条件。</div>';
 $$('[data-pkg-action]').forEach(b=>b.onclick=()=>packageAction(b.dataset.pkgAction,data.items[+b.dataset.packageIndex]).catch(e=>toast(e.message,true)));
 $$('[data-package-insert]').forEach(b=>b.onclick=()=>insertPackage(data.items[+b.dataset.packageInsert]).catch(e=>toast(e.message,true)));
 setPackageControlsBusy(!!data.job.running);if(typeof packageListUpdated==='function')packageListUpdated();
}
function setPackageControlsBusy(busy){$$('[data-pkg-action]').forEach(b=>b.disabled=busy||(b.dataset.pkgAction==='remove'&&packageData.items[+b.dataset.packageIndex].protected));$('#packageNavDot').hidden=!busy;}
function renderPackageJob(job){
 if(!job)return;$('#packageJob').hidden=!job.id;if(!job.id)return;
 const running=job.running;$('#packageJobSpinner').hidden=!running;$('#cancelPackageButton').hidden=!running;$('#packageJob').dataset.state=running?'running':job.success?'success':'error';
 const names={install:'下载与验证',repair:'重新下载与验证',remove:'移除缓存',restore:'恢复缓存',check:'完整性检查'};
 const warnings=job.result?.some(r=>r.verified===false||r.valid===false);$('#packageJobTitle').textContent=running?(names[job.action]||'处理中'):job.success?(warnings?'任务完成 · 请查看验证说明':'任务完成'):'任务未完成';$('#packageJobCurrent').textContent=running?job.current||'准备中':`${job.completed} / ${job.total} 项`;
 $('#packageProgress').max=job.total||1;$('#packageProgress').value=job.completed;const logs=job.lines.join('\n');if($('#packageLog').textContent!==logs){$('#packageLog').textContent=logs;$('#packageLog').scrollTop=$('#packageLog').scrollHeight;}
 setPackageControlsBusy(running);packageLastJob=job.id;packageLastRunning=running;
}
async function pollPackageJob(){
 if(packagePollBusy)return;packagePollBusy=true;try{const previous=packageLastRunning,job=await api('packages/job');renderPackageJob(job);if(previous&&!job.running){await loadPackages();await loadHubOverview();toast(job.success?'宏包任务已完成':'宏包任务未完成，请查看日志',!job.success);}}catch{}finally{packagePollBusy=false;}
}
async function packageAction(action,item){
 if(action==='remove'&&!await confirmDialog('移除宏包缓存',`${item.name} 主文件将移入可恢复的回收区，共享依赖会保留。引用此宏包的项目在恢复或重新下载前，可能无法离线编译。`,'移除缓存'))return;
 const job=await api('packages/action',{action,names:[item.name]});renderPackageJob(job);
}
async function insertPackage(item){
 if(item.kind==='class'){modal('文档类用法',`<p>将文档首行的 documentclass 设置为此类。切换文档类可能改变整体排版。</p><pre class="copy-example">\\documentclass{${esc(item.package)}}</pre><div class="dialog-actions"><button class="primary" type="button" id="copyClass">复制命令</button></div>`);$('#copyClass').onclick=async()=>{await navigator.clipboard.writeText('\\documentclass{'+item.package+'}');toast('命令已复制');};return;}
 await openFile(prefs.main);const model=editor.getModel();const value=model.getValue();const declarations=[...value.matchAll(/\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}/g)];if(declarations.some(d=>d[1].split(',').map(x=>x.trim()).includes(item.package))){hubView('editor');toast('主文档已引用 '+item.package);return;}
 const start=value.indexOf('\\begin{document}');if(start<0)throw new Error('主文档没有 begin{document}，请手动插入 usepackage');const position=model.getPositionAt(start);editor.executeEdits('package-insert',[{range:new monacoApi.Range(position.lineNumber,1,position.lineNumber,1),text:'\\usepackage{'+item.package+'}\n'}]);hubView('editor');toast('已插入 usepackage{'+item.package+'}');
}
async function analyzeProjectPackages(){
 await saveAll();const used=await api('packages/analyze');const missing=used.filter(p=>!p.cached&&p.available).map(p=>p.name);
 modal('当前项目所需宏包',`<p>扫描当前项目的 documentclass、usepackage 和可识别的依赖声明。</p><div class="dependency-list">${used.length?used.map(p=>`<div><code>${esc(p.name)}</code><span class="state-badge ${p.cached?'success':p.available?'warning':'neutral'}">${p.cached?'已缓存':p.available?'待下载':'未收录'}</span></div>`).join(''):'<p>没有找到宏包声明。</p>'}</div>${used.some(p=>!p.available)?'<p>未收录的自定义宏包可放在项目目录中。</p>':''}<div class="dialog-actions"><button type="button" class="primary" id="installMissingPackages" ${missing.length?'':'disabled'}>补齐 ${missing.length} 个缺失项</button></div>`);
 $('#installMissingPackages').onclick=async()=>{try{const job=await api('packages/action',{action:'install',names:missing.slice(0,30)});closeModal();hubView('packages');renderPackageJob(job);}catch(e){toast(e.message,true);}};
}
async function hubRun(action){switch(action){
 case 'home':hubView('home');break;case 'editorView':hubView('editor');break;case 'packages':hubView('packages');break;
 case 'newProject':await newProjectDialog();break;case 'importProject':importProjectDialog();break;case 'openProject':await openNativeProject();break;case 'openProjectPath':await openProjectPath();break;
 case 'refreshHub':await loadHubOverview();toast('项目列表已刷新');break;
 case 'health':await loadHubOverview();modal('编译环境',`<div class="health-list"><div><span>编译器</span><strong>${hubOverview.engineReady?'已找到 Tectonic':'缺少编译器'}</strong></div><div><span>宏包目录</span><strong>${hubOverview.cacheReady?'资源索引存在':'资源索引缺失'}</strong></div><div><span>离线格式</span><strong>${hubOverview.offlineFormatReady?'已缓存':'需联网准备'}</strong></div><div><span>共享目录</span><code>${esc(hubOverview.home)}</code></div><div><span>宏包缓存</span><code>${esc(hubOverview.cache)}</code></div><div><span>项目库</span><code>${esc(hubOverview.projects)}</code></div></div><p>已有缓存可离线使用。新宏包下载需要联网，下载和验证日志在宏包管理查看。</p>`);break;
 case 'analyzePackages':await analyzeProjectPackages();break;case 'refreshPackages':await loadPackages();break;
 case 'clearPackageSearch':$('#packageQuery').value='';packagePage=0;await loadPackages();$('#packageQuery').focus();break;
 case 'cancelPackage':await api('packages/cancel',{});toast('正在停止宏包任务');break;
}}
function hubNotifyState(next){
 if(hubLastProject!==next.projectId){hubLastProject=next.projectId;loadHubOverview().catch(()=>{});}
 $('#packageNavDot').hidden=!next.packageBusy;if(document.body.dataset.view==='packages'||packageLastRunning||next.packageBusy)pollPackageJob();
}
$('#projectFileInput').onchange=e=>{importChosenFiles([...e.target.files],false).catch(e=>toast(e.message,true));e.target.value='';};
$('#projectFolderInput').onchange=e=>{importChosenFiles([...e.target.files],true).catch(e=>toast(e.message,true));e.target.value='';};
$('#packageQuery').oninput=()=>{clearTimeout(packageQueryTimer);packageQueryTimer=setTimeout(()=>{packagePage=0;loadPackages();},350);};$('#packageQuery').onkeydown=e=>{if(e.key==='Enter'){clearTimeout(packageQueryTimer);packagePage=0;loadPackages();}if(e.key==='Escape')hubRun('clearPackageSearch');};
$$('[data-package-filter]').forEach(b=>b.onclick=()=>{packageFilter=b.dataset.packageFilter;packagePage=0;$$('[data-package-filter]').forEach(tab=>{const on=tab===b;tab.classList.toggle('active',on);tab.setAttribute('aria-selected',String(on));});loadPackages();});
$('#packagePrev').onclick=()=>{if(packagePage>0){packagePage--;loadPackages();$('#packagesPage').scrollTo({top:0,behavior:'smooth'});}};$('#packageNext').onclick=()=>{if(packageData&&packagePage<packageData.pages-1){packagePage++;loadPackages();$('#packagesPage').scrollTo({top:0,behavior:'smooth'});}};
loadHubOverview().catch(()=>{});
