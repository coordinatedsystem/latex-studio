'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths = {
 files:'M4 4h6l2 2h8v14H4z M8 10h8 M8 14h6',folder:'M3 6h7l2 2h9v12H3z',file:'M6 3h8l4 4v14H6z M14 3v5h5',
 code:'m9 6-6 6 6 6m6-12 6 6-6 6',pdf:'M6 3h8l4 4v14H6z M14 3v5h5 M8 13h8 M8 17h5',search:'M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15z m5.5-2 5 5',
 save:'M4 3h13l3 3v15H4z M8 3v6h8V3 M8 21v-8h8v8',undo:'M8 5 3 10l5 5 M3 10h10a7 7 0 0 1 7 7v3',redo:'m16 5 5 5-5 5 M21 10H11a7 7 0 0 0-7 7v3',
 replace:'M4 5h10 M4 10h7 m6-7 4 4-4 4 M14 7h7 M4 17h10 m-4-4 4 4-4 4 M14 17h7',sidebar:'M3 4h18v16H3z M9 4v16 M5.5 8h1 M5.5 12h1',
 play:'m8 4 12 8-12 8z',stop:'M6 6h12v12H6z',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M9 3l-1 3-3 1-2 3 2 2-1 3 3 3 3-1 2 2 3-1 1-3 3-1 1-3-2-2 1-3-3-2-3 1-2-2z',
 help:'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M9 8a3 3 0 0 1 6 0c0 3-3 2-3 5 M12 17v1',command:'M9 9H6a3 3 0 1 1 3-3v12a3 3 0 1 1-3-3h12a3 3 0 1 1-3 3V6a3 3 0 1 1 3 3H9v6',
 close:'m6 6 12 12 M6 18 18 6',more:'M5 12h.01 M12 12h.01 M19 12h.01',refresh:'M20 7v6h-6 M4 17v-6h6 M5 7a8 8 0 0 1 14-2l1 2 M4 17l1 2a8 8 0 0 0 14-2',
 upload:'M12 16V3 m-5 5 5-5 5 5 M4 15v6h16v-6',download:'M12 3v13 m-5-5 5 5 5-5 M4 16v5h16v-5',filePlus:'M14 3H6v18h12V7z M14 3v5h5 M9 14h6 M12 11v6',
 shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-6',list:'M9 5h12 M9 12h12 M9 19h12 M3 5h1 M3 12h1 M3 19h1',fold:'m8 3 4 4 4-4 M3 12h18 m-13 9 4-4 4 4',
 wrap:'M3 5h18 M3 10h14a4 4 0 0 1 0 8h-4 m3-3-3 3 3 3 M3 15h5',history:'M3 3v6h6 M3 9a9 9 0 1 1 0 6 M12 7v6l4 2',braces:'M9 3H7v6l-3 3 3 3v6h2 M15 3h2v6l3 3-3 3v6h-2',
 expand:'M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5',terminal:'m4 6 5 6-5 6 M12 18h8',copy:'M9 8h12v13H9z M15 8V3H3v13h6',image:'M3 3h18v18H3z m0 14 6-6 5 5 3-3 4 4 M16 7h.01',
 chevron:'m8 5 7 7-7 7'
};
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[n]||paths.file}"/></svg>`;
function icons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{const svg=icon(el.dataset.icon);if(el.tagName==='BUTTON'&&el.querySelector('span'))el.insertAdjacentHTML('afterbegin',svg);else el.insertAdjacentHTML('afterbegin',svg);el.removeAttribute('data-icon');});}
icons();
const defaultPrefs={fontSize:13,wrap:true,minimap:false,autosave:true,offline:true,autoCompile:false,main:'report.tex',ratio:41};
let prefs={...defaultPrefs};try{prefs={...prefs,...JSON.parse(localStorage.getItem('latexStudioPrefs')||'{}')}}catch{}
function persist(){localStorage.setItem('latexStudioPrefs',JSON.stringify(prefs));}
let editor,monacoApi,active=null,models=new Map(),state=null,lastPdf=0,pollBusy=false,lastTree='',autoTimer,saveTimer,outlineTimer,externalTick=0,diagnosticsOnly=false,compileRequested=false;
let searchTimer,searchSequence=0,pendingAutoCompile=false;
let pdfTicket=0,pdfAbort,pdfBlobUrl='',pdfPhase='idle',pdfPages=0,previewLastError='',serviceDisconnected=false;
const collapsedFolders=new Set();
const commands=[
 ['保存当前文件','save','Ctrl+S'],['保存全部文件','saveAll','Ctrl+Shift+S'],['保存并编译预览','compile','Ctrl+Enter'],['查找当前文件','find','Ctrl+F'],['查找并替换','replace','Ctrl+H'],['搜索整个项目（含上下文）','projectSearch','Ctrl+Shift+F'],['转到行号','goto','Ctrl+G'],['插入 LaTeX 模板','snippet',''],['撤销','undo','Ctrl+Z'],['重做','redo','Ctrl+Y'],['切换自动换行','wrap','Alt+Z'],['折叠所有章节','foldAll',''],['展开所有章节','unfoldAll',''],['新建文件','new',''],['上传图片 / 素材','upload',''],['历史版本','history',''],['重新载入当前文件','reload',''],['文档大纲','outline',''],['编译日志','logs',''],['下载 PDF','download',''],['设置','settings',''],['帮助与快捷键','help','']
];
commands.push(['项目主页','home',''],['新建项目','newProject',''],['导入项目','importProject',''],['打开本地文档','openProject',''],['宏包管理','packages',''],['检查当前项目所需宏包','analyzePackages','']);
function toast(message,error=false){const el=document.createElement('div');el.className='toast'+(error?' error':'');const text=document.createElement('span');text.textContent=message;const close=document.createElement('button');close.type='button';close.className='toast-dismiss';close.setAttribute('aria-label','关闭提示');close.textContent='×';close.onclick=()=>el.remove();el.append(text,close);$('#toastRegion').append(el);setTimeout(()=>el.remove(),error?8500:3500);}
async function api(path,data){const headers=data===undefined?{}:{'Content-Type':'application/json'};if(state?.projectId)headers['X-Studio-Project']=state.projectId;const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers,body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Object.assign(new Error(result.error||'请求失败'),{status:response.status});return result;}
function modal(title,body){$('#modalTitle').textContent=title;$('#modalBody').innerHTML=body;if(!$('#modal').open)$('#modal').showModal();$('#modal').scrollTop=0;$('#modalBody').scrollTop=0;return $('#modalBody');}
function closeModal(){$('#modal').close();}
async function inputDialog(title,label,value='',description=''){
 const body=modal(title,`<p>${esc(description)}</p><label class="field"><span>${esc(label)}</span><input id="dialogInput" autocomplete="off" value="${esc(value)}" required></label><div class="dialog-actions"><button type="button" class="secondary" id="dialogCancel">取消</button><button type="button" class="primary" id="dialogSubmit">确定</button></div>`);
 return new Promise(resolve=>{let done=false;const finish=v=>{if(done)return;done=true;$('#modal').removeEventListener('close',cancel);closeModal();resolve(v);};const cancel=()=>finish(null);$('#dialogCancel').onclick=cancel;$('#dialogSubmit').onclick=()=>{const value=$('#dialogInput').value.trim();if(value)finish(value)};$('#dialogInput').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('#dialogSubmit').click()}};$('#modal').addEventListener('close',cancel,{once:true});setTimeout(()=>{$('#dialogInput').focus();$('#dialogInput').select()},50);});
}
async function confirmDialog(title,message,action='确定'){
 modal(title,`<p>${esc(message)}</p><div class="dialog-actions"><button type="button" class="secondary" id="dialogCancel">取消</button><button type="button" class="danger" id="dialogSubmit">${esc(action)}</button></div>`);
 return new Promise(resolve=>{let done=false;const finish=v=>{if(done)return;done=true;$('#modal').removeEventListener('close',cancel);closeModal();resolve(v)};const cancel=()=>finish(false);$('#dialogCancel').onclick=cancel;$('#dialogSubmit').onclick=()=>finish(true);$('#modal').addEventListener('close',cancel,{once:true});});
}
function language(path){const ext=path.split('.').pop().toLowerCase();return({tex:'latex',sty:'latex',cls:'latex',bib:'bibtex',py:'python',json:'json',md:'markdown',csv:'plaintext'})[ext]||'plaintext'}
function fileIcon(path){return /\.(png|jpg|jpeg|webp|svg|gif)$/i.test(path)?'image':path.endsWith('.pdf')?'pdf':/\.(tex|sty|cls)$/i.test(path)?'braces':/\.py$/i.test(path)?'code':'file'}
function setSaveStatus(message,error=false){$('#saveStatus').textContent=message;$('#saveStatus').dataset.state=error?'error':models.get(active)?.dirty?'dirty':'saved';$('#saveDot').className='status-dot'+(error?' error':models.get(active)?.dirty?' dirty':'');}
function renderTabs(){
 $('#documentTabs').innerHTML=[...models].map(([path,info])=>`<button class="document-tab ${path===active?'active':''}" data-open="${esc(path)}" title="${esc(path)}">${icon(fileIcon(path))}<span class="tab-name">${esc(path.split('/').pop())}</span>${info.dirty?'<span class="dirty-indicator"></span>':''}<span class="tab-close" role="button" tabindex="0" data-close="${esc(path)}" title="关闭文件">×</span></button>`).join('');
 $$('#documentTabs [data-open]').forEach(b=>b.onclick=e=>{if(!e.target.closest('[data-close]'))switchFile(b.dataset.open)});
 $$('#documentTabs [data-open]').forEach(b=>b.onauxclick=e=>{if(e.button===1){e.preventDefault();closeFile(b.dataset.open).catch(err=>toast(err.message,true));}});
 $$('#documentTabs [data-close]').forEach(b=>{b.onclick=async e=>{e.stopPropagation();await closeFile(b.dataset.close)};b.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();b.click()}}});
}
function renderTree(){
 if(!state)return;let html='',groups={};for(const f of state.files){const group=f.path.includes('/')?f.path.slice(0,f.path.lastIndexOf('/')):'';(groups[group]??=[]).push(f)}
 const keys=Object.keys(groups).sort((a,b)=>a===''?-1:b===''?1:a.localeCompare(b));
 for(const group of keys){if(group)html+=`<button class="folder-row" data-folder="${esc(group)}">${icon('folder')}<span>${esc(group)}</span></button>`;for(const f of groups[group])html+=`<button class="file-row ${f.path.endsWith('.tex')?'tex':f.path.endsWith('.py')?'py':''} ${f.path===active?'active':''}" data-file="${esc(f.path)}" data-group="${esc(group)}" title="${esc(f.path)} · ${(f.size/1024).toFixed(1)} KB" style="padding-left:${group?22:9}px">${icon(fileIcon(f.path))}<span class="file-name">${esc(f.path.split('/').pop())}</span></button>`;}
 $('#fileTree').innerHTML=html;
 $$('#fileTree [data-file]').forEach(b=>{b.onclick=()=>openFile(b.dataset.file).catch(e=>toast(e.message,true));b.oncontextmenu=e=>{e.preventDefault();openFile(b.dataset.file).then(showFileMenu)}});
 $$('#fileTree [data-group]').forEach(b=>b.hidden=collapsedFolders.has(b.dataset.group));
 $$('#fileTree [data-folder]').forEach(b=>{b.classList.toggle('collapsed',collapsedFolders.has(b.dataset.folder));b.setAttribute('aria-expanded',String(!collapsedFolders.has(b.dataset.folder)));b.onclick=()=>{const name=b.dataset.folder;if(collapsedFolders.has(name))collapsedFolders.delete(name);else collapsedFolders.add(name);b.classList.toggle('collapsed',collapsedFolders.has(name));b.setAttribute('aria-expanded',String(!collapsedFolders.has(name)));$$('#fileTree [data-group]').filter(e=>e.dataset.group===name).forEach(e=>e.hidden=collapsedFolders.has(name));};});
}
function renderOutline(){
 const info=models.get(active);if(!info?.model){$('#outlineList').innerHTML='<p class="outline-empty">打开源文件以查看文档结构。</p>';return;}
 const items=[];const isPython=active.endsWith('.py');info.model.getLinesContent().forEach((text,i)=>{let m;if(isPython){m=text.match(/^(\s*)(?:async\s+)?(def|class)\s+(\w+)/);if(m)items.push({line:i+1,title:m[3],level:m[1].length?1:0});}else{m=text.match(/^\s*\\(part|chapter|section|subsection|subsubsection|paragraph)\*?(?:\[[^\]]*\])?\{([^}]*)/);if(m)items.push({line:i+1,title:m[2].replace(/\\\w+\s*/g,''),level:Math.max(0,['part','chapter','section','subsection','subsubsection','paragraph'].indexOf(m[1])-2)});}});
 $('#outlineList').innerHTML=items.length?items.map(i=>`<button class="outline-item" data-line="${i.line}" style="padding-left:${8+i.level*12}px">${esc(i.title)}<small>${i.line}</small></button>`).join(''):'<p class="outline-empty">没有找到章节。LaTeX 的 section、subsection 或 Python 的函数会显示在这里。</p>';
 $$('#outlineList [data-line]').forEach(b=>b.onclick=()=>goLine(+b.dataset.line));
}
function switchPanel(name){$$('[data-panel]').forEach(b=>{const on=b.dataset.panel===name;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));$('#panel-'+b.dataset.panel).hidden=!on});if(name==='outline'){renderOutline();updateOutlineCursor(editor?.getPosition()?.lineNumber||1);}if(name==='search')$('#projectQuery').focus();}
function revealSidebar(){if(innerWidth<=850)$('#workspace').classList.add('sidebar-visible');else $('#workspace').classList.remove('sidebar-hidden');editor?.layout();}
async function openFile(path,line,column){
 if(models.has(path)){switchFile(path);if(line)goLine(line,column);return;}
 const item=state?.files.find(f=>f.path===path);if(!item)throw new Error('找不到此项目文件');
 if(!item.editable){models.set(path,{asset:true,dirty:false});switchFile(path);return;}
 const data=await api('file?path='+encodeURIComponent(path));
 const model=monacoApi.editor.createModel(data.content,language(path),monacoApi.Uri.parse('inmemory://project/'+path));
 const info={model,revision:data.revision,dirty:false,viewState:null,saving:null};models.set(path,info);
 model.onDidChangeContent(()=>{info.dirty=true;document.dispatchEvent(new Event('studio-source-change'));if(path===active){setSaveStatus('尚未保存');clearTimeout(outlineTimer);outlineTimer=setTimeout(renderOutline,400)}renderTabs();clearTimeout(saveTimer);if(prefs.autosave)saveTimer=setTimeout(()=>saveAll().catch(e=>toast(e.message,true)),1400);clearTimeout(autoTimer);if(prefs.autoCompile)autoTimer=setTimeout(()=>{if(state?.running)pendingAutoCompile=true;else compile().catch(e=>toast(e.message,true));},2200);});
 switchFile(path);if(line)goLine(line,column);
}
function switchFile(path){
 if(!models.has(path))return;const previous=models.get(active);if(previous?.model)previous.viewState=editor.saveViewState();active=path;const info=models.get(path);
 $('#assetPreview').hidden=!info.asset;$('#editor').hidden=!!info.asset;
 if(info.asset){editor.setModel(null);const url='/project/'+path.split('/').map(encodeURIComponent).join('/');$('#assetPreview').innerHTML=path.endsWith('.pdf')?`<iframe title="素材 PDF" src="/vendor/pdfjs/web/viewer.html?file=${encodeURIComponent(url)}#zoom=page-width"></iframe>`:`<img alt="${esc(path)}" src="${url}">`;}
 else{editor.setModel(info.model);if(info.viewState)editor.restoreViewState(info.viewState);editor.focus();setTimeout(()=>editor.layout(),0);}
 $('#fileBreadcrumb').textContent=path.replaceAll('/','  /  ');$('#languageStatus').textContent=info.asset?'素材预览':({latex:'LaTeX',python:'Python',bibtex:'BibTeX',markdown:'Markdown'})[language(path)]||language(path);setSaveStatus(info.dirty?'尚未保存':'所有更改已保存');renderTabs();renderTree();renderOutline();
}
async function closeFile(path){
 const info=models.get(path);if(info.dirty){if(!await confirmDialog('关闭文件',`${path} 有未保存的改动。关闭前保存？`,'保存并关闭'))return;await saveFile(path)}
 const next=[...models.keys()].filter(p=>p!==path).at(-1);if(path===active){if(next)switchFile(next);else{active=null;editor.setModel(null);$('#assetPreview').hidden=true;$('#editor').hidden=false;$('#fileBreadcrumb').textContent='未打开文件';}}
 info.model?.dispose();models.delete(path);renderTabs();renderTree();renderOutline();
}
async function saveFile(path=active){
 const info=models.get(path);if(!info||info.asset||!info.dirty)return;if(info.saving){await info.saving;if(info.dirty)return saveFile(path);return;}
 const value=info.model.getValue(),version=info.model.getAlternativeVersionId();
 info.saving=(async()=>{try{const result=await api('save',{path,content:value,revision:info.revision});info.revision=result.revision;info.dirty=version!==info.model.getAlternativeVersionId();if(path===active)setSaveStatus(info.dirty?'尚未保存':'已保存 · '+new Date().toLocaleTimeString('zh-CN',{hour12:false}));renderTabs();if(result.historyWarning){toast(result.historyWarning,true);setSaveStatus('文件已保存 · 历史未保存',true);}}catch(e){setSaveStatus('保存失败 · 请处理文件冲突',true);throw e}finally{info.saving=null}})();return info.saving;
}
async function saveAll(){for(const [path] of models)await saveFile(path)}
function goLine(line,column=1){if(!models.get(active)?.model)return;editor.setPosition({lineNumber:line,column:column||1});editor.revealLineInCenter(line);editor.focus();if(innerWidth<=850)$('#workspace').classList.remove('sidebar-visible');updateOutlineCursor(line);syncControls();}
function editorAction(id){if(models.get(active)?.model)editor.getAction(id)?.run();}
async function reloadCurrent(){const info=models.get(active);if(!info?.model)return;if(info.dirty&&!await confirmDialog('重新载入','当前未保存改动会被磁盘版本替换，是否继续？','重新载入'))return;const data=await api('file?path='+encodeURIComponent(active));info.model.pushEditOperations([],[{range:info.model.getFullModelRange(),text:data.content}],()=>null);info.revision=data.revision;info.dirty=false;renderTabs();setSaveStatus('已重新载入磁盘文件');renderOutline();}
async function compile(){
 if(compileRequested)return;if(state?.editorAiBusy){toast('请等待 AI 验证完成，或先停止任务');return;}if(state?.running){toast('正在编译，请等待完成后再次编译');return;}
 compileRequested=true;try{await saveAll();await api('compile',{main:prefs.main,offline:prefs.offline});$('#compileButton').disabled=true;await poll();}finally{compileRequested=false;}
}
function previewStatus(phase,message,detail=''){
 pdfPhase=phase;const loading=phase==='loading',error=phase==='error';$('#previewFreshness').dataset.state=phase;$('#previewFreshness').textContent=message;$('#previewMessage').hidden=!(loading||error);$('#previewSpinner').hidden=!loading;$('#previewRecovery').hidden=!error;$('#previewMessageTitle').textContent=loading?'正在加载 PDF':'预览未能加载';$('#previewMessageText').textContent=detail;$('#pdfFrame').setAttribute('aria-busy',String(loading));
 $$('[data-action="nativePreview"]').forEach(b=>{b.setAttribute('aria-pressed',String(phase==='native'));});
 $('#previewFreshness').title=phase==='native'&&previewLastError?'兼容阅读器未能启动：'+previewLastError:phase==='ready'?'PDF 已完成页面绘制':'';
}
function deadline(promise,ms,message){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);})]).finally(()=>clearTimeout(timer));}
function logPreviewError(message){previewLastError=String(message);api('preview-event',{event:'viewer-error',message:previewLastError}).catch(()=>{});}
function useNativePreview(automatic=false){
 if(!pdfBlobUrl){setPdf(state?.pdfVersion||lastPdf,true,true);return;}
 ++pdfTicket;pdfAbort?.abort();$('#noPdf').hidden=true;$('#pdfFrame').src=pdfBlobUrl+'#toolbar=1&navpanes=0&view=FitH';previewStatus('native','系统预览');if(automatic)toast('已自动切换到系统 PDF 阅读器');
}
async function setPdf(version,force=false,native=false,requestedPage=null,previewSource=null){
 if(!force&&lastPdf===version)return;lastPdf=version;const ticket=++pdfTicket,project=state?.projectId;pdfAbort?.abort();pdfAbort=new AbortController();previewLastError='';$('#noPdf').hidden=true;previewStatus('loading','加载中…','正在读取编译结果…');
 try{
  const response=await fetch(previewSource||'/preview.pdf?v='+encodeURIComponent(version),{credentials:'same-origin',cache:'no-store',signal:pdfAbort.signal,headers:state?.projectId?{'X-Studio-Project':state.projectId}:{}});
  if(!response.ok)throw new Error(response.status===401?'本地会话已失效，请双击启动快捷方式重新连接。':'读取 PDF 失败（HTTP '+response.status+'）');
  const bytes=new Uint8Array(await response.arrayBuffer());if(ticket!==pdfTicket)return;
  if(bytes.length<5||String.fromCharCode(...bytes.subarray(0,5))!=='%PDF-')throw new Error('服务返回的内容不是有效的 PDF。');
  const oldBlob=pdfBlobUrl;pdfBlobUrl=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));if(oldBlob)URL.revokeObjectURL(oldBlob);
  if(native){useNativePreview();return;}
  const frame=$('#pdfFrame');let page=requestedPage||1;try{if(!requestedPage)page=frame.contentWindow?.PDFViewerApplication?.page||1;}catch{}
  const loaded=new Promise((resolve,reject)=>{const done=()=>{frame.removeEventListener('load',onLoad);frame.removeEventListener('error',onError);};const onLoad=()=>{done();resolve();};const onError=()=>{done();reject(new Error('PDF 阅读器资源未能加载。'));};frame.addEventListener('load',onLoad);frame.addEventListener('error',onError);});
  frame.src='/vendor/pdfjs/web/viewer.html?file=&studio=1&v=compat2-'+version+'#zoom=page-width&pagemode=none&page='+page;
  await deadline(loaded,15000,'阅读器启动超时。');if(ticket!==pdfTicket)return;
  const app=frame.contentWindow?.PDFViewerApplication;if(!app)throw new Error(previewLastError||'浏览器未能启动 PDF 阅读器。');
  await deadline(app.initializedPromise,15000,'PDF 阅读器初始化超时。');if(ticket!==pdfTicket)return;
  themePdf();$('#previewMessageText').textContent='正在绘制页面…';
  if(typeof writingTrackPdf==='function')writingTrackPdf(app,ticket,project);
  let renderedHandler,pagesHandler;const pagesInitialized=new Promise(resolve=>{pagesHandler=resolve;app.eventBus.on('pagesinit',pagesHandler);});
  const rendered=new Promise((resolve,reject)=>{renderedHandler=event=>{if(event.error)reject(new Error(event.error.message||'页面绘制失败'));else resolve();};app.eventBus.on('pagerendered',renderedHandler);});rendered.catch(()=>{});
  try{await deadline(app.open({data:bytes,filename:prefs.main.replace(/.*\//,'').replace(/\.tex$/,'.pdf')}),20000,'PDF 文档解析超时。');if(ticket!==pdfTicket)return;await deadline(pagesInitialized,15000,'PDF 页面初始化超时。');if(ticket!==pdfTicket)return;pdfPages=app.pdfDocument.numPages;app.pdfViewer.currentScaleValue='page-width';app.page=Math.min(page,pdfPages);await deadline(rendered,15000,'页面绘制超时。');}finally{app.eventBus.off('pagerendered',renderedHandler);app.eventBus.off('pagesinit',pagesHandler);}
  if(ticket===pdfTicket)previewStatus('ready',previewSource?'候选预览 · 未应用 · '+pdfPages+' 页':pdfPages+' 页');
 }catch(error){if(ticket!==pdfTicket||error.name==='AbortError')return;logPreviewError(error.message);if(pdfBlobUrl&&!/会话|HTTP|不是有效/.test(error.message)){useNativePreview(true);}else previewStatus('error','加载失败',error.message);}
}
function themePdf(){
 const frame=$('#pdfFrame');let doc;try{doc=frame.contentDocument}catch{return}if(!doc||!doc.getElementById('viewerContainer'))return;
 if(!doc.getElementById('studioPdfTheme')){const css=doc.createElement('link');css.id='studioPdfTheme';css.rel='stylesheet';css.href='/pdf-theme.css';doc.head.append(css);}
}
document.addEventListener('webviewerloaded',event=>{const win=event.detail?.source;if(win?.PDFViewerApplicationOptions){win.PDFViewerApplicationOptions.set('disablePreferences',true);win.PDFViewerApplicationOptions.set('viewerCssTheme',1);win.PDFViewerApplicationOptions.set('localeProperties',{lang:'zh-CN'});win.PDFViewerApplicationOptions.set('workerSrc','../build/pdf.worker.mjs?studio=compat2');}});
window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===$('#pdfFrame').contentWindow&&event.data?.type==='studio-pdf-error')logPreviewError(event.data.message);});
$('#pdfFrame').addEventListener('load',themePdf);
let pollPending=null;
function poll(){if(!pollPending)pollPending=pollOnce().finally(()=>{pollPending=null;});return pollPending;}
async function pollOnce(){
 pollBusy=true;try{
  const next=await api('state');const wasRunning=state?.running;const changed=!!state?.projectId&&state.projectId!==next.projectId;
  if(changed&&[...models.values()].some(m=>m.dirty)){setSaveStatus('另一窗口切换了项目 · 本页未保存改动已保留',true);return;}
  if(changed)resetProjectModels();state=next;serviceDisconnected=false;document.title='LaTeX Studio';if(changed||!active)prefs.main=next.main;
  const treeKey=JSON.stringify(next.files);if(treeKey!==lastTree){lastTree=treeKey;renderTree()}
  $('#compileButton').disabled=next.running||next.packageBusy||next.editorAiBusy;$('#cancelButton').disabled=!next.running;$('#compileLabel').textContent=next.running?'正在编译…':next.packageBusy?'宏包处理中':'编译预览';$('#compileOverlay').hidden=!next.running;
  if(next.hasPdf){$('#noPdf').hidden=true;if(document.body.dataset.view==='editor'&&(typeof editorAiHoldPdf!=='function'||!editorAiHoldPdf(next)))setPdf(next.pdfVersion);}else if(typeof editorAiHoldPdf!=='function'||!editorAiHoldPdf(next)){$('#noPdf').hidden=false;$('#previewMessage').hidden=true;}
  $('#compileStatus').dataset.state=next.running?'running':next.success===true?'success':next.success===false?'error':'idle';
  if(next.running){$('#compileStatus').textContent='编译中…';}
  else if(next.success!==null){$('#compileStatus').textContent=(next.success?'编译成功':'编译失败')+' · '+next.duration+' 秒';}
  const log=next.lines.join('\n');if($('#logOutput').textContent!==log){const atEnd=$('#logOutput').scrollTop+$('#logOutput').clientHeight>=$('#logOutput').scrollHeight-40;$('#logOutput').textContent=log;if(atEnd)$('#logOutput').scrollTop=$('#logOutput').scrollHeight;}
  $('#compileMeta').textContent=next.running?'实时输出':next.success===null?'':(next.success?'成功':'失败')+' · '+next.duration+' 秒';
  renderDiagnostics(next.diagnostics);
  if(wasRunning&&!next.running){toast(next.success?'编译成功，PDF 已更新':'编译失败，请查看日志',!next.success);if(!next.success)toggleLogs(true);if(pendingAutoCompile&&prefs.autoCompile){pendingAutoCompile=false;setTimeout(()=>run('compile'),100);}}
  syncControls();
  if(!next.running&&++externalTick%4===0)await checkExternalChanges();
  if(changed&&next.files.some(f=>f.path===next.main))await openFile(next.main);
  if(typeof hubNotifyState==='function')hubNotifyState(next);
 }catch(e){if(!serviceDisconnected){setSaveStatus(e.status===401?'本地会话失效 · 请重新启动编辑器':'本地服务未连接',true);if(!state||e.status===401)previewStatus('error','连接失效','请双击「启动可视化编辑器.cmd」重新连接。');serviceDisconnected=true;}}finally{pollBusy=false;}
}
function resetProjectModels(){
 clearTimeout(saveTimer);clearTimeout(autoTimer);clearTimeout(outlineTimer);editor?.setModel(null);for(const info of models.values())info.model?.dispose();models.clear();active=null;lastTree='';lastPdf=0;++pdfTicket;pdfAbort?.abort();if(pdfBlobUrl)URL.revokeObjectURL(pdfBlobUrl);pdfBlobUrl='';pdfPages=0;$('#pdfFrame').src='about:blank';$('#projectQuery').value='';$('#searchResults').innerHTML='';collapsedFolders.clear();renderTabs();renderOutline();previewStatus('idle','等待编译');
}
async function checkExternalChanges(){
 for(const [path,info] of models){if(!info.model||info.dirty||info.saving)continue;try{const data=await api('file?path='+encodeURIComponent(path));if(data.revision!==info.revision){const view=path===active?editor.saveViewState():null;info.model.pushEditOperations([],[{range:info.model.getFullModelRange(),text:data.content}],()=>null);info.revision=data.revision;info.dirty=false;if(view)editor.restoreViewState(view);renderTabs();setSaveStatus('已同步外部修改');}}catch{}}
}
function renderDiagnostics(items){
 $('#problemCount').textContent=items.length;$('#diagnosticList').innerHTML=items.length?items.map((d,i)=>`<button class="diagnostic ${d.severity}" data-diag="${i}">${d.severity==='error'?'错误':'提示'} · ${esc(d.file)}:${d.line}　${esc(d.message)}</button>`).join(''):'<div class="no-results">没有可定位到源码的问题。详细输出请查看编译日志。</div>';
 $$('#diagnosticList [data-diag]').forEach(b=>b.onclick=()=>{const d=items[+b.dataset.diag];if(state.files.some(f=>f.path===d.file))openFile(d.file,d.line).catch(e=>toast(e.message,true));else toast('这条提示来自编译器宏包：'+d.file)});
 if(monacoApi)for(const [path,info] of models){if(info.model)monacoApi.editor.setModelMarkers(info.model,'tectonic',items.filter(d=>d.file===path).map(d=>({startLineNumber:d.line,startColumn:1,endLineNumber:d.line,endColumn:info.model.getLineMaxColumn(Math.min(d.line,info.model.getLineCount())),message:d.message,severity:d.severity==='error'?monacoApi.MarkerSeverity.Error:monacoApi.MarkerSeverity.Warning})))}
}
function toggleLogs(force){const on=force===undefined?$('#logPanel').hidden:force;$('#logPanel').hidden=!on;$('#workspace').classList.toggle('with-log',on);setTimeout(()=>editor?.layout(),0)}
function wrapSelection(command){if(!models.get(active)?.model)return;const selection=editor.getSelection();const text=editor.getModel().getValueInRange(selection);editor.executeEdits('latex-insert',[{range:selection,text:'\\'+command+'{'+text+'}',forceMoveMarkers:true}]);editor.focus();}
const snippets=[
 {title:'章节标题',note:'section / subsection',code:'\\section{${1:章节标题}}\n${0}'},
 {title:'图片',note:'带标题和引用标签的 figure',code:'\\begin{figure}[htbp]\n  \\centering\n  \\includegraphics[width=0.8\\linewidth]{${1:figures/image.pdf}}\n  \\caption{${2:图片标题}}\n  \\label{fig:${3:example}}\n\\end{figure}\n${0}'},
 {title:'三线表',note:'booktabs 学术表格',code:'\\begin{table}[htbp]\n  \\centering\n  \\caption{${1:表格标题}}\n  \\label{tab:${2:example}}\n  \\begin{tabular}{lcc}\n    \\toprule\n    ${3:项目} & ${4:数值一} & ${5:数值二} \\\\\n    \\midrule\n    ${6:示例} & 1 & 2 \\\\\n    \\bottomrule\n  \\end{tabular}\n\\end{table}\n${0}'},
 {title:'数学公式',note:'equation 编号公式',code:'\\begin{equation}\n  ${1:y = f(x)}\n  \\label{eq:${2:example}}\n\\end{equation}\n${0}'},
 {title:'项目列表',note:'itemize 无序列表',code:'\\begin{itemize}\n  \\item ${1:第一项}\n  \\item ${2:第二项}\n\\end{itemize}\n${0}'},
 {title:'引用与标签',note:'ref / label / cite',code:'${1:参见}\\ref{${2:标签}}${0}'}
];
function insertSnippet(index){closeModal();if(!models.get(active)?.model)return;editor.focus();editor.getContribution('snippetController2').insert(snippets[index].code);}
function showSnippets(){const body=modal('插入 LaTeX 结构','<p>插入后按 Tab 跳转到下一个占位位置。图片、表格模板使用报告中已有的宏包。</p><div class="snippets">'+snippets.map((s,i)=>`<button type="button" class="snippet-card" data-snippet="${i}"><strong>${esc(s.title)}</strong><small>${esc(s.note)}</small></button>`).join('')+'</div>');body.querySelectorAll('[data-snippet]').forEach(b=>b.onclick=()=>insertSnippet(+b.dataset.snippet))}
async function showSettings(){
 const locations=await api('overview');
 modal('设置',`<div class="settings-section"><h3>文件位置</h3><label class="field-row"><span>项目目录</span><input id="settingProjects" aria-label="项目目录" value="${esc(locations.projects)}" spellcheck="false"></label><label class="field-row"><span>缓存目录</span><input id="settingCache" aria-label="缓存目录" value="${esc(locations.cache)}" spellcheck="false"></label><p class="settings-note">选择空文件夹，已有项目和缓存会一并迁移。</p></div><div class="settings-section"><h3>编辑与编译</h3><label class="field-row"><span>字号</span><input type="number" min="10" max="24" id="settingFont" value="${prefs.fontSize}"></label><label class="field-row"><span>自动换行</span><input type="checkbox" id="settingWrap" ${prefs.wrap?'checked':''}></label><label class="field-row"><span>代码缩略图</span><input type="checkbox" id="settingMinimap" ${prefs.minimap?'checked':''}></label><label class="field-row"><span>自动保存</span><input type="checkbox" id="settingAutosave" ${prefs.autosave?'checked':''}></label><label class="field-row"><span>离线编译</span><input type="checkbox" id="settingOffline" ${prefs.offline?'checked':''}></label><label class="field-row"><span>主文档</span><select id="settingMain">${(state?.files||[]).filter(f=>f.path.endsWith('.tex')).map(f=>`<option value="${esc(f.path)}" ${f.path===prefs.main?'selected':''}>${esc(f.path)}</option>`).join('')}</select></label></div><p id="settingError" class="settings-error" role="alert" hidden></p><div class="dialog-actions"><button class="primary" type="button" id="applySettings">保存设置</button></div>`);
 $('#applySettings').onclick=async()=>{
  const button=$('#applySettings');button.disabled=true;$('#settingError').hidden=true;
  try{
   const projects=$('#settingProjects').value.trim(),cache=$('#settingCache').value.trim();
   if(projects!==locations.projects||cache!==locations.cache){button.textContent='正在迁移…';await saveAll();await api('storage/locations',{projects,cache});}
   prefs.fontSize=Math.min(24,Math.max(10,+$('#settingFont').value||13));prefs.wrap=$('#settingWrap').checked;prefs.minimap=$('#settingMinimap').checked;prefs.autosave=$('#settingAutosave').checked;prefs.offline=$('#settingOffline').checked;prefs.main=$('#settingMain').value||prefs.main;persist();applyPrefs();closeModal();await poll();if(typeof loadHubOverview==='function')await loadHubOverview();toast('设置已保存');
  }catch(e){if($('#settingError')){$('#settingError').textContent=e.message;$('#settingError').hidden=false;button.disabled=false;button.textContent='保存设置';}}
 };
}
function applyPrefs(){editor?.updateOptions({fontSize:prefs.fontSize,fontWeight:'450',wordWrap:prefs.wrap?'on':'off',minimap:{enabled:prefs.minimap}});$('#autoCompile').checked=prefs.autoCompile;$('#workspace').style.setProperty('--editor-ratio',prefs.ratio+'%');$('#divider').setAttribute('aria-valuenow',String(prefs.ratio));syncControls();}
function showHelp(){modal('让写作更专注',`<p>左侧编辑源码，右侧查看 PDF。编译前会保存所有已打开文件。PDF 工具栏支持全文搜索、页码跳转、目录与缩略图、缩放、旋转、打印和下载。</p><div class="help-grid">${[['保存','Ctrl S'],['保存并编译','Ctrl Enter'],['查找 / 替换','Ctrl F / Ctrl H'],['项目搜索（含前后文）','Ctrl Shift F'],['命令面板','Ctrl Shift P / Ctrl K'],['转到行号','Ctrl G'],['多光标','Alt + 鼠标点击'],['注释 / 取消注释','Ctrl /'],['自动换行','Alt Z'],['撤销 / 重做','Ctrl Z / Ctrl Y']].map(([a,b])=>`<span>${a}</span><kbd>${b}</kbd>`).join('')}</div><p style="margin-top:22px">文件会自动保留最近 30 个保存前的版本。也可以关闭自动保存，使用保存按钮手动写入磁盘。</p><p>开源组件：<a href="https://github.com/microsoft/monaco-editor" target="_blank" rel="noreferrer">Monaco Editor（MIT）</a> · <a href="https://github.com/mozilla/pdf.js" target="_blank" rel="noreferrer">PDF.js（Apache-2.0）</a> · Tectonic。全部组件均在本地加载。</p>`)}
function showPalette(){
 modal('命令面板','<input id="commandQuery" class="command-input" placeholder="搜索操作…" aria-label="筛选命令" role="combobox" aria-autocomplete="list" aria-controls="commandList" aria-expanded="true"><div id="commandList" class="command-list" role="listbox"></div>');
 let selected=0;
 const choose=()=>{const buttons=$$('#commandList [data-command]');buttons.forEach((b,i)=>{b.classList.toggle('selected',i===selected);b.setAttribute('aria-selected',String(i===selected));});const current=buttons[selected];if(current){$('#commandQuery').setAttribute('aria-activedescendant',current.id);current.scrollIntoView({block:'nearest'});}else $('#commandQuery').removeAttribute('aria-activedescendant');};
 const render=()=>{selected=0;const query=$('#commandQuery').value.trim().toLowerCase();$('#commandList').innerHTML=commands.filter(c=>c[0].toLowerCase().includes(query)).map((c,i)=>`<button id="command-option-${i}" class="command-item" type="button" role="option" data-command="${c[1]}">${esc(c[0])}<kbd>${esc(c[2])}</kbd></button>`).join('')||'<div class="no-results">没有找到操作</div>';$$('[data-command]').forEach((b,i)=>{b.onclick=()=>{closeModal();run(b.dataset.command)};b.onpointermove=()=>{if(selected!==i){selected=i;choose();}}});choose();};
 $('#commandQuery').oninput=render;$('#commandQuery').onkeydown=e=>{const count=$$('#commandList [data-command]').length;if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();if(count){selected=(selected+(e.key==='ArrowDown'?1:-1)+count)%count;choose();}}else if(e.key==='Enter'){e.preventDefault();$$('#commandList [data-command]')[selected]?.click();}};render();setTimeout(()=>$('#commandQuery').focus(),40);
}
async function newFile(){const name=await inputDialog('新建文件','相对项目的路径','notes.tex','例如 notes.tex、code/example.py 或 figures/notes.txt。');if(!name)return;await api('create',{path:name,content:name.endsWith('.tex')?'% 新建 LaTeX 文件\n':''});await poll();await openFile(name)}
async function uploadFiles(files){for(const file of files){if(file.size>18*1024*1024){toast(file.name+' 超过 18 MB',true);continue}const path=await inputDialog('导入文件','保存到项目中的路径','figures/'+file.name,'将文件复制到当前项目，已有文件不会被覆盖。');if(!path)continue;const buffer=await file.arrayBuffer();let binary='';const bytes=new Uint8Array(buffer);for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));await api('upload',{path,content:btoa(binary)});toast('已导入 '+path)}await poll()}
function showFileMenu(){if(!active)return;const path=active;modal('文件操作',`<p>${esc(path)}</p><div class="command-list"><button class="command-item" type="button" id="saveAs">另存为副本</button><button class="command-item" type="button" id="renameFile">重命名 / 移动</button><button class="command-item" type="button" id="reloadFile">重新载入磁盘版本</button><button class="command-item danger" type="button" id="deleteFile">删除此文件</button></div>`);
 $('#saveAs').onclick=async()=>{try{const target=await inputDialog('另存为副本','新文件路径',path.replace(/(\.[^.]+)$/,'-副本$1'));if(!target)return;const info=models.get(path);if(info.asset)throw new Error('素材可以通过上传方式复制');await api('create',{path:target,content:info.model.getValue()});await poll();await openFile(target)}catch(e){toast(e.message,true)}};
 $('#renameFile').onclick=async()=>{try{const target=await inputDialog('重命名文件','新文件路径',path,'引用此文件的 LaTeX 路径需要自行更新。');if(!target||target===path)return;await saveFile(path);await api('rename',{path,newPath:target});await closeFile(path);await poll();await openFile(target)}catch(e){toast(e.message,true)}};
 $('#reloadFile').onclick=()=>{closeModal();reloadCurrent().catch(e=>toast(e.message,true))};
 $('#deleteFile').onclick=async()=>{try{if(!await confirmDialog('删除文件','确定删除 '+path+'？保存前版本将保留在本地历史目录。','删除文件'))return;await api('delete',{path});const info=models.get(path);if(info)info.dirty=false;await closeFile(path);await poll();toast('已删除 '+path)}catch(e){toast(e.message,true)}};
}
async function showHistory(){if(!active||!models.get(active)?.model)return;const path=active;const versions=await api('history?path='+encodeURIComponent(path));modal('本地历史 · '+path,`<p>保留最近 30 次保存前的文件内容。点击恢复只替换编辑区，保存后才会写入磁盘。</p>${versions.length?versions.map(v=>`<div class="history-row"><span>${v.slice(0,4)}-${v.slice(4,6)}-${v.slice(6,8)}　${v.slice(9,11)}:${v.slice(11,13)}:${v.slice(13,15)}</span><button class="secondary" type="button" data-version="${esc(v)}">恢复到编辑区</button></div>`).join(''):'<div class="no-results">暂时没有历史。修改并保存后会自动创建。</div>'}`);$$('[data-version]').forEach(b=>b.onclick=async()=>{try{const data=await api('history-content?path='+encodeURIComponent(path)+'&version='+b.dataset.version);switchFile(path);editor.executeEdits('history-restore',[{range:editor.getModel().getFullModelRange(),text:data.content}]);closeModal();toast('历史版本已恢复到编辑区，可使用撤销返回')}catch(e){toast(e.message,true)}})}
async function projectSearch(){
 clearTimeout(searchTimer);const query=$('#projectQuery').value;const ticket=++searchSequence;
 if(!query.trim()){$('#searchCount').textContent='输入后自动搜索';$('#searchResults').innerHTML='';return;}
 const caseSensitive=$('#searchCase').classList.contains('active'),regex=$('#searchRegex').classList.contains('active');$('#searchCount').textContent='正在查找…';$('#searchResults').setAttribute('aria-busy','true');
 try{const results=await api('search',{query,case:caseSensitive,regex});if(ticket!==searchSequence)return;$('#searchCount').textContent=`${results.length}${results.length>=300?'（最多显示 300）':''} 处匹配`;
 $('#searchResults').innerHTML=results.length?results.map((r,i)=>`<button class="search-result" data-result="${i}" title="转到 ${esc(r.path)} 第 ${r.line} 行"><strong>${esc(r.path)}:${r.line}</strong>${r.before?`<code class="search-context">${esc(r.before)}</code>`:''}<code class="match">${highlightMatch(r.text,query,regex,caseSensitive)}</code>${r.after?`<code class="search-context">${esc(r.after)}</code>`:''}</button>`).join(''):'<div class="no-results">没有找到匹配内容。</div>';
 $$('[data-result]').forEach(b=>b.onclick=()=>{const r=results[+b.dataset.result];openFile(r.path,r.line,r.column).then(()=>{if(innerWidth<=850)$('#workspace').classList.remove('sidebar-visible');}).catch(e=>toast(e.message,true));});
 }catch(e){if(ticket===searchSequence){$('#searchCount').textContent='搜索失败';$('#searchResults').textContent=e.message;}}finally{if(ticket===searchSequence)$('#searchResults').removeAttribute('aria-busy');}
}
async function run(action){try{switch(action){
 case 'editorAi':if(typeof editorAiOpen==='function')editorAiOpen();break;
 case 'ai':case 'aiSelection':case 'aiSettings':if(typeof aiRun==='function')await aiRun(action);break;
 case 'home':case 'editorView':case 'packages':case 'newProject':case 'importProject':case 'openProject':case 'openProjectPath':case 'refreshHub':case 'health':case 'analyzePackages':case 'refreshPackages':case 'clearPackageSearch':case 'cancelPackage':if(typeof hubRun==='function')await hubRun(action);break;
 case 'save':await saveFile();toast('已保存');break;case 'saveAll':await saveAll();toast('全部文件已保存');break;case 'compile':if(typeof hubView==='function')hubView('editor');await compile();break;case 'cancel':pendingAutoCompile=false;await api('cancel',{});break;
 case 'undo':editor?.trigger('toolbar','undo');break;case 'redo':editor?.trigger('toolbar','redo');break;case 'find':editorAction('actions.find');break;case 'replace':editorAction('editor.action.startFindReplaceAction');break;case 'goto':editorAction('editor.action.gotoLine');break;
 case 'wrap':prefs.wrap=!prefs.wrap;persist();applyPrefs();break;case 'foldAll':editorAction('editor.foldAll');break;case 'unfoldAll':editorAction('editor.unfoldAll');break;case 'bold':wrapSelection('textbf');break;case 'italic':wrapSelection('textit');break;
 case 'palette':showPalette();break;case 'settings':await showSettings();break;case 'help':showHelp();break;case 'snippet':showSnippets();break;case 'history':await showHistory();break;case 'fileMenu':showFileMenu();break;case 'reload':await reloadCurrent();break;
 case 'new':await newFile();break;case 'upload':$('#uploadInput').click();break;case 'refresh':await poll();toast('文件列表已刷新');break;
 case 'sidebar':if(innerWidth<=850)$('#workspace').classList.toggle('sidebar-visible');else $('#workspace').classList.toggle('sidebar-hidden');editor?.layout();break;
 case 'outline':revealSidebar();switchPanel('outline');break;case 'projectSearch':revealSidebar();switchPanel('search');break;
 case 'clearSearch':$('#projectQuery').value='';await projectSearch();$('#projectQuery').focus();break;
 case 'logs':toggleLogs();break;case 'diagnostics':diagnosticsOnly=!diagnosticsOnly;$('#logOutput').hidden=diagnosticsOnly;$('#diagnosticList').hidden=!diagnosticsOnly;$('#diagnosticTab').classList.toggle('active',diagnosticsOnly);break;
 case 'copyLog':await navigator.clipboard.writeText(state.lines.join('\n'));toast('日志已复制');break;
 case 'refreshPdf':if(typeof editorAiClearPdf==='function')editorAiClearPdf();if(state?.hasPdf)await setPdf(state.pdfVersion,true);break;case 'nativePreview':useNativePreview();break;case 'focusPreview':$('#workspace').classList.toggle('preview-focus');editor?.layout();break;
 case 'download':if(typeof editorAiDownloadCandidate==='function'&&editorAiDownloadCandidate())break;if(!state.hasPdf){toast('请先编译文档');break}const a=document.createElement('a');a.href='/preview.pdf?v='+state.pdfVersion;a.download=prefs.main.replace(/.*\//,'').replace(/\.tex$/,'.pdf');a.click();break;
 }}catch(e){toast(e.message,true)}finally{syncControls();}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(b&&!b.disabled){e.preventDefault();run(b.dataset.action)}});
$$('[data-panel]').forEach(b=>b.onclick=()=>switchPanel(b.dataset.panel));
$('#autoCompile').checked=prefs.autoCompile;$('#autoCompile').onchange=e=>{prefs.autoCompile=e.target.checked;pendingAutoCompile=false;persist();toast(prefs.autoCompile?'自动编译已开启':'自动编译已关闭');if(prefs.autoCompile)run('compile')};
$('#projectQuery').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(projectSearch,350);};
$('#projectQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();projectSearch();}else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();run('clearSearch');}};
for(const id of ['searchCase','searchRegex'])$('#'+id).onclick=e=>{const on=e.currentTarget.classList.toggle('active');e.currentTarget.setAttribute('aria-pressed',String(on));if($('#projectQuery').value.trim())projectSearch();};
$('#contextToggle').onclick=e=>{const on=e.currentTarget.classList.toggle('active');e.currentTarget.setAttribute('aria-pressed',String(on));$('#searchResults').classList.toggle('context-hidden',!on);};
$('#uploadInput').onchange=e=>{uploadFiles([...e.target.files]).catch(e=>toast(e.message,true));e.target.value=''};
document.addEventListener('keydown',e=>{if($('#modal').open)return;const ctrl=e.ctrlKey||e.metaKey;let action=null;if(ctrl&&e.key==='Enter')action='compile';else if(ctrl&&e.key.toLowerCase()==='s')action=e.shiftKey?'saveAll':'save';else if(ctrl&&e.shiftKey&&e.key.toLowerCase()==='f')action='projectSearch';else if(ctrl&&e.shiftKey&&e.key.toLowerCase()==='p'||ctrl&&e.key.toLowerCase()==='k')action='palette';if(action){e.preventDefault();e.stopPropagation();run(action)}},true);
window.addEventListener('beforeunload',e=>{if([...models.values()].some(v=>v.dirty)){e.preventDefault();e.returnValue='存在未保存更改'}});
const divider=$('#divider');
function finishResize(){divider.onpointermove=null;document.body.classList.remove('dragging');divider.classList.remove('dragging');divider.setAttribute('aria-valuenow',String(prefs.ratio));persist();editor?.layout();}
divider.onpointerdown=e=>{if($('#workspace').classList.contains('preview-focus')||innerWidth<=850)return;e.preventDefault();hideTooltip();divider.setPointerCapture(e.pointerId);document.body.classList.add('dragging');divider.classList.add('dragging');divider.onpointermove=e=>{const bounds=$('#workspace').getBoundingClientRect();const side=$('#workspace').classList.contains('sidebar-hidden')?0:$('#sidebar').getBoundingClientRect().width;const available=bounds.width-side;const left=Math.max(260,Math.min(available-280,e.clientX-bounds.left-side));prefs.ratio=Math.round(left/bounds.width*1000)/10;$('#workspace').style.setProperty('--editor-ratio',prefs.ratio+'%');editor?.layout();};};
divider.onpointerup=finishResize;divider.onpointercancel=finishResize;divider.onlostpointercapture=()=>{if(document.body.classList.contains('dragging'))finishResize();};
divider.ondblclick=()=>{prefs.ratio=41;applyPrefs();persist();editor?.layout();toast('已恢复默认分栏');};
divider.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();prefs.ratio=e.key==='Home'?41:Math.min(65,Math.max(25,prefs.ratio+(e.key==='ArrowRight'?1:-1)));applyPrefs();persist();}};

function syncControls(){
 const values={wrap:prefs.wrap,sidebar:innerWidth<=850?$('#workspace').classList.contains('sidebar-visible'):!$('#workspace').classList.contains('sidebar-hidden'),focusPreview:$('#workspace').classList.contains('preview-focus'),logs:!$('#logPanel').hidden};
 for(const [action,on] of Object.entries(values))$$(`[data-action="${action}"]`).forEach(b=>{b.setAttribute('aria-pressed',String(on));b.classList.toggle('active',on);});
 const clear=$('[data-action="clearSearch"]');if(clear)clear.disabled=!$('#projectQuery').value;
}
function updateOutlineCursor(line){const entries=$$('#outlineList [data-line]');let current=null;for(const b of entries)if(+b.dataset.line<=line)current=b;for(const b of entries){const on=b===current;b.classList.toggle('current',on);if(on)b.setAttribute('aria-current','location');else b.removeAttribute('aria-current');}}
function highlightMatch(text,query,regex,caseSensitive){
 try{const pattern=new RegExp(regex?query:query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),caseSensitive?'g':'gi');let html='',end=0;for(const match of text.matchAll(pattern)){if(!match[0])continue;html+=esc(text.slice(end,match.index))+'<mark>'+esc(match[0])+'</mark>';end=match.index+match[0].length;}return html+esc(text.slice(end));}catch{return esc(text);}
}
let tooltipTimer,tooltipTarget;
function hideTooltip(){clearTimeout(tooltipTimer);$('#interactionTooltip').hidden=true;if(tooltipTarget)tooltipTarget.removeAttribute('aria-describedby');tooltipTarget=null;}
function prepareTooltip(target){const el=target.closest?.('button[title],button[data-tip],#divider');if(!el||el.closest('#editor'))return;const title=el.dataset.tip||el.getAttribute('title');if(!title)return;if(el.hasAttribute('title')){el.dataset.tip=title;el.removeAttribute('title');}if(!el.getAttribute('aria-label'))el.setAttribute('aria-label',title);hideTooltip();tooltipTarget=el;tooltipTimer=setTimeout(()=>{if(!el.isConnected)return;const tip=$('#interactionTooltip');tip.textContent=title;tip.hidden=false;const rect=el.getBoundingClientRect();const box=tip.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(innerWidth-box.width-8,rect.left+rect.width/2-box.width/2))+'px';tip.style.top=(rect.bottom+box.height+16<innerHeight?rect.bottom+8:rect.top-box.height-8)+'px';el.setAttribute('aria-describedby','interactionTooltip');},450);}
document.addEventListener('pointerover',e=>prepareTooltip(e.target));
document.addEventListener('focusin',e=>prepareTooltip(e.target));
document.addEventListener('pointerout',e=>{if(tooltipTarget&&!tooltipTarget.contains(e.relatedTarget))hideTooltip();});
document.addEventListener('focusout',hideTooltip);document.addEventListener('scroll',hideTooltip,true);
document.addEventListener('pointerdown',e=>{hideTooltip();const b=e.target.closest('button');if(!b||b.disabled||b.closest('#editor')||e.button!==0||matchMedia('(prefers-reduced-motion: reduce)').matches)return;const rect=b.getBoundingClientRect();const size=Math.max(rect.width,rect.height)*2;const wave=document.createElement('span');wave.className='button-ink';wave.setAttribute('aria-hidden','true');wave.style.cssText=`width:${size}px;height:${size}px;left:${e.clientX-rect.left-size/2}px;top:${e.clientY-rect.top-size/2}px;`;b.classList.add('has-ink');b.append(wave);setTimeout(()=>{wave.remove();if(!b.querySelector('.button-ink'))b.classList.remove('has-ink');},450);});
document.addEventListener('keydown',e=>{if(e.key!=='Escape'||$('#modal').open||e.defaultPrevented)return;hideTooltip();if($('#workspace').classList.contains('preview-focus')){$('#workspace').classList.remove('preview-focus');editor?.layout();}else $('#workspace').classList.remove('sidebar-visible');syncControls();});
function registerLatex(m){
 m.languages.register({id:'latex',extensions:['.tex','.sty','.cls']});m.languages.register({id:'bibtex',extensions:['.bib']});
 m.languages.setLanguageConfiguration('latex',{comments:{lineComment:'%'},brackets:[['{','}'],['[',']'],['(',')']],autoClosingPairs:[{open:'{',close:'}'},{open:'[',close:']'},{open:'(',close:')'}],surroundingPairs:[{open:'{',close:'}'},{open:'$',close:'$'}]});
 m.languages.setMonarchTokensProvider('latex',{defaultToken:'',tokenizer:{root:[[/%.*/,'comment'],[/\\(?:begin|end)(?=\{)/,'keyword'],[/\\(?:section|subsection|subsubsection|chapter|part|title|author|caption|label|ref|cite|usepackage|documentclass)\*?/,'keyword'],[/\\[a-zA-Z@]+\*?/,'tag'],[/\\[^a-zA-Z]/,'tag'],[/\$\$/,{token:'string',next:'@displaymath'}],[/\$/,{token:'string',next:'@math'}],[/[{}\[\]]/,'delimiter.bracket'],[/\b\d+(?:\.\d+)?\b/,'number']],math:[[/\\[a-zA-Z]+/,'tag'],[/\$/,{token:'string',next:'@pop'}],[/[^$\\]+/,'string']],displaymath:[[/\\[a-zA-Z]+/,'tag'],[/\$\$/,{token:'string',next:'@pop'}],[/[^$\\]+/,'string'],[/\$/,'string']]}});
 m.languages.registerCompletionItemProvider('latex',{triggerCharacters:['\\','{'],provideCompletionItems(model,position){const word=model.getWordUntilPosition(position);const range={startLineNumber:position.lineNumber,endLineNumber:position.lineNumber,startColumn:word.startColumn,endColumn:word.endColumn};const simple=['textbf','textit','emph','section','subsection','subsubsection','label','ref','cite','includegraphics','caption','footnote','input','include','usepackage','begin','end'];return{suggestions:[...simple.map(c=>({label:c,kind:m.languages.CompletionItemKind.Function,insertText:c+'{${1}}',insertTextRules:m.languages.CompletionItemInsertTextRule.InsertAsSnippet,range,detail:'LaTeX 命令'})),...snippets.map(s=>({label:s.title,kind:m.languages.CompletionItemKind.Snippet,insertText:s.code,insertTextRules:m.languages.CompletionItemInsertTextRule.InsertAsSnippet,range,detail:s.note}))]}}});
 m.languages.registerFoldingRangeProvider('latex',{provideFoldingRanges(model){const ranges=[],stack=[],sections=[];model.getLinesContent().forEach((line,i)=>{if(/^\s*%/.test(line))return;const begin=line.match(/\\begin\{([^}]+)\}/);const end=line.match(/\\end\{([^}]+)\}/);if(begin)stack.push({name:begin[1],line:i+1});if(end){const j=stack.map(s=>s.name).lastIndexOf(end[1]);if(j>=0){const s=stack[j];stack.splice(j,1);if(i+1>s.line)ranges.push({start:s.line,end:i+1})}}const sec=line.match(/^\s*\\(section|subsection|subsubsection)\*?\{/);if(sec){const level=['section','subsection','subsubsection'].indexOf(sec[1]);while(sections.length&&sections.at(-1).level>=level){const s=sections.pop();if(i>s.line)ranges.push({start:s.line,end:i})}sections.push({level,line:i+1})}});for(const s of sections)if(model.getLineCount()>s.line)ranges.push({start:s.line,end:model.getLineCount()});return ranges;}});
 m.editor.defineTheme('studio-white',{base:'vs',inherit:true,rules:[{token:'',foreground:'253244'},{token:'comment',foreground:'66758A',fontStyle:''},{token:'keyword',foreground:'7651A8',fontStyle:''},{token:'tag',foreground:'2769AA',fontStyle:''},{token:'string',foreground:'287C58'},{token:'number',foreground:'B46920'},{token:'delimiter',foreground:'52647B'},{token:'identifier',foreground:'253244'},{token:'type',foreground:'975088'}],colors:{'editor.background':'#FFFFFF','editor.foreground':'#253244','editorLineNumber.foreground':'#7E8B9C','editorLineNumber.activeForeground':'#111111','editor.lineHighlightBackground':'#F4F8F5','editor.selectionBackground':'#D5EADD','editor.inactiveSelectionBackground':'#EAF2EC','editorCursor.foreground':'#111111','editorIndentGuide.background1':'#E4EAE6','editorIndentGuide.activeBackground1':'#A6C4B1','editorWidget.background':'#FFFFFF','editorWidget.foreground':'#111111','editorWidget.border':'#CBD8CF','editorGutter.background':'#FFFFFF','focusBorder':'#629575','input.foreground':'#111111','input.placeholderForeground':'#444444','list.activeSelectionForeground':'#111111','list.highlightForeground':'#111111','minimap.background':'#FCFDFC','scrollbarSlider.background':'#AABAAF60','scrollbarSlider.hoverBackground':'#8AA39390'}});
}
function init(){
 if(!window.require){$('#editor').innerHTML='<p class="loading-msg">编辑器资源未找到，请检查 latex-studio/vendor。</p>';return;}
 require.config({paths:{vs:'/vendor/monaco/min/vs'}});
 require(['vs/editor/editor.main'],async()=>{
  monacoApi=window.monaco;registerLatex(monacoApi);editor=monacoApi.editor.create($('#editor'),{theme:'studio-white',fontFamily:'"Studio Digits", "Studio Source Han", Consolas, "Microsoft YaHei", monospace',fontWeight:'450',fontSize:prefs.fontSize,lineHeight:23,lineNumbers:'on',minimap:{enabled:prefs.minimap},wordWrap:prefs.wrap?'on':'off',automaticLayout:true,scrollBeyondLastLine:false,padding:{top:10,bottom:25},renderLineHighlight:'line',smoothScrolling:true,roundedSelection:true,tabSize:2,insertSpaces:true,folding:true,showFoldingControls:'mouseover',contextmenu:true,quickSuggestions:{other:true,comments:false,strings:false},suggest:{showWords:false},unicodeHighlight:{ambiguousCharacters:false,invisibleCharacters:false,nonBasicASCII:false},accessibilitySupport:'auto',fixedOverflowWidgets:true});
  editor.onDidChangeCursorPosition(e=>{$('#cursorStatus').textContent=`行 ${e.position.lineNumber}，列 ${e.position.column}`;updateOutlineCursor(e.position.lineNumber);});
  editor.addAction({id:'studio.compile',label:'保存并编译 PDF',keybindings:[monacoApi.KeyMod.CtrlCmd|monacoApi.KeyCode.Enter],run:()=>run('compile')});
  editor.addAction({id:'studio.palette',label:'打开工作台命令面板',run:showPalette});
  applyPrefs();await poll();if(state){prefs.main=state.main;try{await openFile(state.main)}catch(e){toast(e.message,true)}}setInterval(poll,1000);
 },error=>{setSaveStatus('编辑器加载失败',true);toast('无法加载 Monaco 编辑器：'+error,true)});
}
init();
