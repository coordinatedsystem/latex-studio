const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/web/ai-studio.js','utf8');
function setup(){
 const elements=new Map();function $(id){if(!elements.has(id))elements.set(id,{value:id==='#aiProvider'?'local':id==='#aiScope'?'file':'',textContent:'',classList:{toggle(){},remove(){}},addEventListener(){},setAttribute(){},close(){}});return elements.get(id);}
 const ctx=vm.createContext({$, $$:()=>[],commands:[],Set,Map,console,clearInterval(){},setInterval(){},Date,toast(){},esc:s=>s,state:{projectId:'p'},models:new Map(),api:async()=>({}),openFile:async()=>{},run:async()=>{}});
 vm.runInContext(source,ctx);
 vm.runInContext(String.raw`let liveText='prefix\n甲😀错字\n尾错字\nsuffix';let writes=0;const model={getValue:()=>liveText,getFullModelRange:()=>({}),pushStackElement(){},pushEditOperations(a,edits){liveText=edits[0].text;writes++;}};models.set('main.tex',{model});aiContext={projectId:'p',path:'main.tex',full:liveText,text:'甲😀错字\n尾错字\n',start:7,end:19,line:2};aiResult={edits:[{start:3,end:5,before:'错字',after:'正确'},{start:7,end:9,before:'错字',after:'改正'}]};aiRenderResults=()=>{};`,ctx);
 // Derive the end offset from the actual UTF-16 selection length.
 vm.runInContext('aiContext.end=aiContext.start+aiContext.text.length;',ctx);
 return ctx;
}
test('selectively applies multiple suggestions against the snapshot, preserving surrounding content',async()=>{
 const ctx=setup();vm.runInContext('aiChosen=new Set([0]);',ctx);await vm.runInContext('aiApply()',ctx);
 assert.equal(vm.runInContext('liveText',ctx),'prefix\n甲😀正确\n尾错字\nsuffix');
 vm.runInContext('aiChosen=new Set([1]);',ctx);await vm.runInContext('aiApply()',ctx);
 assert.equal(vm.runInContext('liveText',ctx),'prefix\n甲😀正确\n尾改正\nsuffix');assert.equal(vm.runInContext('writes',ctx),2);
});
test('does not overwrite a buffer edited after the result was generated',async()=>{
 const ctx=setup();vm.runInContext("aiChosen=new Set([0]);liveText+='用户的新内容';",ctx);
 await assert.rejects(vm.runInContext('aiApply()',ctx),/发生了变化/);assert.equal(vm.runInContext('writes',ctx),0);
});
test('Windows CRLF buffers keep exact positioning across consecutive selective applications',async()=>{
 const ctx=setup();vm.runInContext(String.raw`liveText=liveText.replace(/\n/g,'\r\n');model.pushEditOperations=(a,edits)=>{liveText=edits[0].text.replace(/\n/g,'\r\n');writes++;};aiChosen=new Set([0]);`,ctx);
 await vm.runInContext('aiApply()',ctx);
 vm.runInContext('aiChosen=new Set([1]);',ctx);await vm.runInContext('aiApply()',ctx);
 assert.equal(vm.runInContext('liveText',ctx),'prefix\r\n甲😀正确\r\n尾改正\r\nsuffix');
});
test('captures a Windows selection with LF offsets matching the displayed textarea',async()=>{
 const ctx=setup();ctx.active='main.tex';ctx.monacoApi={};ctx.editor={getSelection:()=>({isEmpty:()=>false,getStartPosition:()=>({lineNumber:2,column:1}),getEndPosition:()=>({lineNumber:3,column:4})})};
 vm.runInContext(String.raw`liveText=liveText.replace(/\n/g,'\r\n');model.getOffsetAt=p=>liveText.split('\n').slice(0,p.lineNumber-1).reduce((a,b)=>a+b.length+1,0)+p.column-1;model.getPositionAt=offset=>({lineNumber:liveText.slice(0,offset).split('\n').length});$('#aiScope').value='selection';`,ctx);
 await vm.runInContext('aiCapture()',ctx);
 assert.equal(vm.runInContext('aiContext.full',ctx),'prefix\n甲😀错字\n尾错字\nsuffix');
 assert.equal(vm.runInContext('aiContext.start',ctx),7);
 assert.equal(vm.runInContext('aiContext.text',ctx),'甲😀错字\n尾错字');
 assert.equal(vm.runInContext("$('#aiInput').value",ctx),'甲😀错字\n尾错字');
});
test('does not apply a result to a different project',async()=>{
 const ctx=setup();vm.runInContext("aiChosen=new Set([0]);state.projectId='other';",ctx);
 await assert.rejects(vm.runInContext('aiApply()',ctx),/项目已切换/);assert.equal(vm.runInContext('writes',ctx),0);
});
test('converts Python character offsets for emoji before displaying or applying the result',async()=>{
 const ctx=setup();ctx.api=async()=>({id:'job',running:false,success:true,task:'check',result:{edits:[{start:2,end:4,before:'错字',after:'正确'}]}});
 vm.runInContext("aiJob={id:'job'};aiRenderResults=()=>{};",ctx);await vm.runInContext('aiPoll()',ctx);
 assert.equal(vm.runInContext('aiResult.edits[0].start',ctx),3);
 assert.equal(vm.runInContext('aiResult.edits[0].end',ctx),5);
});
