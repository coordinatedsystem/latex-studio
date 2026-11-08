'use strict';
function studioClearSourceHighlight(){
 clearTimeout(sourceNavigation.highlightTimer);
 try{sourceNavigation.highlightModel?.deltaDecorations(sourceNavigation.decorations||[],[]);}catch{}
 sourceNavigation.decorations=[];sourceNavigation.highlightModel=null;
}
function studioBindSourceHighlight(){
 if(!editor||sourceNavigation.boundEditor===editor)return;sourceNavigation.boundEditor=editor;
 editor.onMouseDown(studioClearSourceHighlight);editor.onDidChangeModelContent(studioClearSourceHighlight);editor.onDidChangeModel(studioClearSourceHighlight);
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'||e.target.closest?.('.monaco-editor'))studioClearSourceHighlight();});
document.addEventListener('studio-source-change',studioClearSourceHighlight);

const studioHelp={
 home:['项目',['新建、导入文件夹，或打开本地 .tex 文件。','点击项目继续编辑；项目与缓存位置可在设置中修改。']],
 editor:['编辑器',['Ctrl+S 保存，Ctrl+Enter 保存全部并编译；Ctrl+F 查找，Ctrl+H 替换。','“定位 PDF →”跳到当前源码对应位置；PDF 中双击，或点“← 定位源码”后选取文字。','定位高亮会自动消退，也可点击源码或按 Esc 清除。']],
 packages:['宏包管理',['搜索宏包名称或用途，选择未缓存的宏包下载。','点击宏包查看关联资源；已缓存资源可供本机各项目编译使用。']],
 writing:['写作与版面',['选择 PDF 页面或源码范围，输入修改目标，再获取建议。','查看代码差异和编译后的 PDF 对照，确认后才应用到原稿。','可多选页面或进行全文审核；可撤销已应用的修改。']],
 editorAi:['编辑器 AI',['选择“修改代码”“修复报错”或“解释代码”，再选取源码、填写要求。','修改会先在副本中编译；通过后可查看差异和修改效果，再确认应用。','“清空”只清除面板中的对话与候选预览，不改变源码。运行中先停止；拖动分隔线调整面板。']],
 references:['引用检查',['点击“检查当前项目”，再点击统计卡片查看文件、标签、引用或文献。','展开条目查看原文与使用位置；“源码 / PDF”跳到对应位置。','定位后窗口保持打开；拖动标题栏移动，右下角缩放，“—”收起后可从状态栏恢复。']],
 glossary:['术语表',['添加原文与统一译法，保存到当前项目。','写作与翻译任务会读取相关术语；筛选后也可导入、导出术语。']],
 tests:['服务测试',['本地环境检查不会调用 AI。','点击对应服务测试才会发出示例请求，用于检查连接和响应格式；不代表所有任务质量。']],
 impact:['改动影响地图',['在编辑器选择源码，再分析当前选择；也可分析整个文件。','查看关联标签、引用、素材与页码。页码需要当前源码已编译；静态分析不能预测所有重排影响。']],
 consistency:['数据一致性检查',['核对正文与表格中的指标和项目内 CSV、JSON、Python 静态数值。','可按不一致结果筛选；多个依据冲突时手动选择数据基准。','支持常见单位换算与舍入；不会执行 Python，也不会自动改写论文。']],
 history:['版本历史',['选择历史版本，对比它与当前编辑内容。','“恢复到编辑区”后仍可撤销，保存后才写入文件。']],
 settings:['设置',['调整编辑、自动编译、项目与缓存位置。','在“版本与更新”检查和下载新版；更改存储位置前先保存文档。']],
 service:['服务配置',['填写所选服务的密钥并保存，再使用写作或修复功能。','密钥由当前 Windows 账户加密保存，不会展示在对话或导出文件中。']],
 updates:['版本与更新',['检查版本后，下载并校验安装包，再打开安装向导。','可选择安装位置；换到其他位置不会自动迁移原有项目与设置。']]
};
function studioShowHelp(topic){
 const [title,steps]=studioHelp[topic]||studioHelp.editor;let dialog=$('#featureHelpDialog');
 if(!dialog){dialog=document.createElement('dialog');dialog.id='featureHelpDialog';dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation();});document.body.append(dialog);}
 dialog.innerHTML='<header><h2></h2><button type="button" class="tiny" aria-label="关闭功能说明">×</button></header><ol></ol>';
 dialog.querySelector('h2').textContent=title;for(const step of steps){const li=document.createElement('li');li.textContent=step;dialog.querySelector('ol').append(li);}
 dialog.querySelector('button').onclick=()=>dialog.close();dialog.showModal();
}
function studioHelpButton(topic){const b=document.createElement('button');b.type='button';b.className='feature-help';b.dataset.featureHelp=topic;b.title='功能说明';b.setAttribute('aria-label','查看功能说明');b.textContent='!';return b;}
function studioInstallHelp(){
 for(const [selector,topic] of [['.home-hero','home'],['.package-title','packages'],['.ai-heading-actions','writing'],['.editor-subbar>div:last-child','editor'],['#logPanel .log-heading>div:last-child','editorAi']])$(selector)?.append(studioHelpButton(topic));
 $('.editor-tool-panel-heading').insertBefore(studioHelpButton('tool'),$('#editorToolClose'));
 document.addEventListener('click',e=>{const b=e.target.closest('[data-feature-help]');if(b){e.preventDefault();e.stopPropagation();studioShowHelp(b.dataset.featureHelp==='tool'?editorTool:b.dataset.featureHelp);}});
 const modalHeader=$('#modal header');if(modalHeader){const button=studioHelpButton('settings');modalHeader.insertBefore(button,modalHeader.lastElementChild);button.onclick=()=>{const title=$('#modalTitle').textContent;button.dataset.featureHelp=/版本与更新/.test(title)?'updates':/服务/.test(title)?'service':/历史/.test(title)?'history':'settings';};}
}
function studioInstallFloatingTools(){
 const panel=$('#editorToolPanel'),head=$('.editor-tool-panel-heading');
 const grip=document.createElement('span');grip.id='editorToolDrag';grip.textContent='⠿';grip.tabIndex=0;grip.setAttribute('role','button');grip.setAttribute('aria-label','移动工具窗口，方向键微调，Home 还原');grip.title='拖动移动 · 方向键微调 · 双击还原';head.prepend(grip);
 const minimize=document.createElement('button');minimize.type='button';minimize.className='tiny';minimize.textContent='—';minimize.title='收起工具';minimize.setAttribute('aria-label','收起文档工具');head.insertBefore(minimize,$('#editorToolClose'));minimize.onclick=()=>editorToolClose();
 const restore=document.createElement('button');restore.id='editorToolRestore';restore.textContent='文档工具';restore.title='恢复上次打开的工具';$('.statusbar>div').append(restore);restore.onclick=()=>editorToolOpen(editorTool).catch(e=>toast(e.message,true));
 let saved={};try{saved=JSON.parse(localStorage.getItem('studio.toolWindow')||'{}');}catch{}
 let position=null,drag=null;const bounds=()=>({w:Math.max(200,innerWidth-24),h:Math.max(180,innerHeight-100)});
 const apply=(x,y,w=panel.offsetWidth||580,h=panel.offsetHeight||560)=>{const b=bounds();w=Math.max(Math.min(360,b.w),Math.min(b.w,w));h=Math.max(Math.min(220,b.h),Math.min(b.h,h));x=Math.max(12,Math.min(innerWidth-w-12,x));y=Math.max(70,Math.min(innerHeight-h-30,y));Object.assign(panel.style,{left:x+'px',top:y+'px',right:'auto',bottom:'auto',width:w+'px',height:h+'px'});position={x,y,w,h};};
 const save=()=>{if(!position)return;try{localStorage.setItem('studio.toolWindow',JSON.stringify(position));}catch{}};
 const reset=()=>{const b=bounds(),w=Math.min(580,b.w),h=Math.min(580,b.h);apply(innerWidth-w-13,Math.min(137,innerHeight-h-30),w,h);save();};
 if(Number.isFinite(saved.x)&&Number.isFinite(saved.y))apply(saved.x,saved.y,saved.w,saved.h);else reset();
 head.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button'))return;const r=panel.getBoundingClientRect();drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:r.left,top:r.top,w:r.width,h:r.height};head.setPointerCapture(e.pointerId);head.classList.add('moving');e.preventDefault();});
 head.addEventListener('pointermove',e=>{if(drag&&drag.id===e.pointerId)apply(drag.left+e.clientX-drag.x,drag.top+e.clientY-drag.y,drag.w,drag.h);});
 const finish=()=>{drag=null;head.classList.remove('moving');save();};head.addEventListener('pointerup',e=>{if(head.hasPointerCapture(e.pointerId))head.releasePointerCapture(e.pointerId);finish();});head.addEventListener('pointercancel',finish);head.addEventListener('lostpointercapture',finish);
 grip.ondblclick=reset;grip.onkeydown=e=>{if(e.key==='Home'){e.preventDefault();reset();return;}if(!e.key.startsWith('Arrow'))return;e.preventDefault();const n=e.shiftKey?40:12;apply(position.x+(e.key==='ArrowRight'?n:e.key==='ArrowLeft'?-n:0),position.y+(e.key==='ArrowDown'?n:e.key==='ArrowUp'?-n:0));save();};
 new ResizeObserver(()=>{if(panel.hidden||drag)return;const r=panel.getBoundingClientRect();if(position&&(Math.abs(r.width-position.w)>1||Math.abs(r.height-position.h)>1)){apply(r.left,r.top,r.width,r.height);save();}}).observe(panel);
 window.addEventListener('resize',()=>{if(position){apply(position.x,position.y,position.w,position.h);save();}});
}
async function editorAiClearConversation(){
 if(editorAiJob?.running)throw new Error('请先停止或等待当前任务，再清空对话');
 const project=state.projectId;++editorAiSequence;await api('editor-ai/clear',{});if(project!==state.projectId)return;
 ++editorAiEffectTicket;editorAiEffectMeta=null;editorAiJob=null;editorAiTarget=null;$('#editorAiPrompt').value='';editorAiDiscardDiff();editorAiView(false);
 if(editorAiPreview)await editorAiRestorePdf();editorAiCapture();editorAiRender();$('#editorAiPrompt').focus();toast('对话已清空，源码未改动');
}
function studioInstallAiClear(){
 const clear=document.createElement('button');clear.type='button';clear.id='editorAiClear';clear.className='secondary';clear.textContent='清空';clear.title='清空对话与候选预览，源码保持原样';$('#editorAiExpand').before(clear);clear.onclick=editorAiWatch(editorAiClearConversation);
 const render=editorAiRender;editorAiRender=function(){render();clear.disabled=!!editorAiJob?.running;};editorAiRender();
}
studioInstallFloatingTools();studioInstallHelp();studioInstallAiClear();
