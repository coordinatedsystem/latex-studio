const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function setup(){
 const nodes=new Map(),calls=[],messages=[],edits=[];
 const $=id=>{if(!nodes.has(id))nodes.set(id,{value:id==='#editorAiMode'?'repair':id==='#editorAiLimit'?'1':id==='#workflowVersion'?'20261107-120000-1':'',hidden:true,disabled:false,open:true,innerHTML:'',children:[0,1,2,3].map(()=>({classList:{add(){}}})),listeners:{},addEventListener(name,fn){this.listeners[name]=fn},classList:{add(){}},contentWindow:{PDFViewerApplication:{pdfDocument:{}}}});return nodes.get(id)};
 const model={version:1,getValue:()=> 'current',getVersionId(){return this.version},getValueLength:()=>7,getFullModelRange:()=>({})};
 const c=vm.createContext({$,console,commands:[],Date,Number,Math,JSON,Map,innerWidth:1200,state:{projectId:'one'},active:'main.tex',models:new Map([['main.tex',{model}]]),editorAiJob:null,editorAiTarget:null,editorAiPreview:null,editorAiRender(){},editorAiOpen(){},openFile:async(...a)=>calls.push({open:a}),editorAiDirty:()=>false,run(){},showHistory(){},language:()=> 'latex',esc:s=>s,toast:s=>messages.push(s),editor:{executeEdits:(...a)=>edits.push(a)},monacoApi:{editor:{createModel:t=>({text:t,dispose(){}}),createDiffEditor:()=>({dispose(){},setModel(){}})}},modal(){},closeModal(){},api:async(p,data)=>{calls.push({p,data});if(p.startsWith('history-content'))return {content:'old'};if(p.startsWith('history?'))return ['20261107-120000-1'];return {requests:0,tokens:0,failures:0,limit:20};}});
 vm.runInContext(fs.readFileSync(__dirname+'/web/workflow-tools.js','utf8'),c);return {c,$,calls,messages,edits,model};
}
test('render never starts a paid request',()=>{const {c,$,calls}=setup();vm.runInContext('editorAiRender()',c);assert.equal(calls.length,0)});
test('history comparison restores only in editor and leaves saving explicit',async()=>{const {c,$,calls,edits}=setup();await vm.runInContext('showHistory()',c);$('#workflowRestore').onclick();assert.equal(edits.length,1);assert.equal(edits[0][1][0].text,'old');assert.ok(calls.every(x=>x.data===undefined));});
test('stale history comparison refuses to overwrite newer edits',async()=>{const {c,$,model,edits,messages}=setup();await vm.runInContext('showHistory()',c);model.version++;$('#workflowRestore').onclick();assert.equal(edits.length,0);assert.match(messages[0],/已变化/);});
test('locate refuses dirty source and candidate PDFs before lookup',async()=>{const {c,calls}=setup();c.editorAiDirty=()=>true;await assert.rejects(vm.runInContext('workflowLocate()',c),/保存并编译/);c.editorAiDirty=()=>false;c.editorAiPreview={};await assert.rejects(vm.runInContext('workflowLocate()',c),/原 PDF/);assert.equal(calls.length,0);});

test('forward lookup loads an unrendered PDF page before scrolling',async()=>{
 const {c,$}=setup(),scrolls=[];c.editor={getPosition:()=>({lineNumber:100})};
 c.api=async()=>({page:3,x:.2,y:.3});
 $('#pdfFrame').contentWindow.PDFViewerApplication={pdfDocument:{getPage:async n=>{assert.equal(n,3);return {view:[10,20,610,820]}}},pdfViewer:{scrollPageIntoView:v=>scrolls.push(v)}};
 await vm.runInContext('workflowLocate()',c);assert.equal(scrolls[0].pageNumber,3);assert.equal(scrolls[0].destArray[2],130);assert.equal(scrolls[0].destArray[3],580);
});
test('Ctrl double-click resolves PDF coordinates to a source line',async()=>{
 const {c,$,calls}=setup(),listeners={};
 $('#pdfFrame').contentDocument={addEventListener:(name,fn)=>listeners[name]=fn};
 $('#pdfFrame').listeners.load();c.api=async route=>{calls.push({route});return {path:'main.tex',line:70}};
 const sheet={dataset:{pageNumber:'2'},getBoundingClientRect:()=>({left:10,top:20,width:600,height:800})};
 await listeners.dblclick({target:{closest:()=>sheet},ctrlKey:true,clientX:130,clientY:260});
 assert.match(calls[0].route,/page=2&x=0.2&y=0.3/);assert.deepEqual(Array.from(calls[1].open),['main.tex',70]);
});
test('PDF response cannot navigate after source becomes dirty',async()=>{
 const {c,$,calls}=setup(),listeners={};$('#pdfFrame').contentDocument={addEventListener:(name,fn)=>listeners[name]=fn};$('#pdfFrame').listeners.load();
 c.api=async()=>{c.editorAiDirty=()=>true;return {path:'main.tex',line:99}};
 await listeners.dblclick({target:{closest:()=>({dataset:{pageNumber:'1'},getBoundingClientRect:()=>({left:0,top:0,width:600,height:800})})},ctrlKey:true,clientX:120,clientY:160});
 assert.equal(calls.length,0);
});
