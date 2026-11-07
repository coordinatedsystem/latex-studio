'use strict';
let editorTool='references';
const editorToolNames={references:'引用检查',glossary:'术语表',tests:'服务测试'};
$('#editorToolBody').append($('#reviewWorkbench'));
async function editorToolOpen(tool){
 if(!editorToolNames[tool])return;
 hubView('editor');editorTool=tool;$('#editorToolsMenu').open=false;$('#editorToolPanel').hidden=false;$('#reviewWorkbench').hidden=false;
 $('#editorToolTitle').textContent=editorToolNames[tool];
 $$('.review-tool').forEach(el=>el.hidden=el.id!=='review-'+tool);
 $$('[data-editor-tool]').forEach(b=>{b.classList.toggle('active',b.dataset.editorTool===tool);b.setAttribute('aria-pressed',String(b.dataset.editorTool===tool));});
 reviewError();
 if(tool==='glossary')await reviewLoadGlossary();
 if(tool==='tests')await reviewHealth();
 if(tool==='references'&&referenceReport?.projectId!==state?.projectId){referenceReport=null;$('#referenceIssues').textContent='点击检查当前项目';}
}
function editorToolClose(){$('#editorToolPanel').hidden=true;$('#editorToolsMenu summary').focus();}
$$('[data-editor-tool]').forEach(b=>b.onclick=reviewWatch(()=>editorToolOpen(b.dataset.editorTool)));
$('#editorToolClose').onclick=editorToolClose;
document.addEventListener('pointerdown',e=>{if(!$('#editorToolsMenu').contains(e.target))$('#editorToolsMenu').open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#editorToolPanel').hidden&&!$('#modal').open){editorToolClose();e.preventDefault();}});
