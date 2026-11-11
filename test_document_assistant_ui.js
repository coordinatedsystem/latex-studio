const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const nodes=new Map(),calls=[];const $=selector=>{if(!nodes.has(selector))nodes.set(selector,{value:'',hidden:false,disabled:false,textContent:'',classList:{toggle(){}},getBoundingClientRect:()=>({height:200})});return nodes.get(selector);};
 const c=vm.createContext({console,Map,Set,JSON,Array,String,Number,Promise,encodeURIComponent,setTimeout,clearTimeout,esc:text=>String(text).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),$,$$:()=>[],state:{projectId:'p1'},prefs:{main:'main.tex'},models:new Map(),saveAll:async()=>{},setInterval:()=>1,clearInterval(){},localStorage:{setItem(){},getItem(){return null;}},api:async(path,data)=>{calls.push([path,data]);return {};}});
 let source=fs.readFileSync(__dirname+'/web/document-assistant.js','utf8');source=source.slice(0,source.indexOf('function conversationInstall'));vm.runInContext(source+';this.assistant=studioAssistant;',c);c.conversationControls=()=>{};c.realRender=c.conversationRender;c.conversationRender=()=>{};c.conversationNotice=()=>{};
 c.assistant.project='p1';return {c,$,calls};
}
test('sending chat carries only selected contexts and attachment IDs, not full attachments',async()=>{
 const f=fixture();f.$('#conversationInput').value='Discuss';f.$('#conversationStepLimit').value='12';f.c.assistant.attachments=[{id:'attachment',name:'a.pdf'}];
 f.c.api=async(path,data)=>{f.calls.push([path,data]);return path.endsWith('/start')?{id:'job',running:false,revision:1}:{id:'job',running:false,revision:2};};
 await f.c.conversationSend();const payload=f.calls.find(x=>x[0].endsWith('/start'))[1];assert.equal(payload.mode,'chat');assert.equal(payload.attachments[0],'attachment');assert.equal(payload.contexts.length,0);assert.equal(f.c.assistant.id,'job');
});
test('late response after project switch cannot replace the new conversation',async()=>{
 const f=fixture();f.$('#conversationInput').value='Old question';let resolve,entered;const reached=new Promise(r=>entered=r);f.c.api=()=>new Promise(r=>{resolve=r;entered();});
 const pending=f.c.conversationSend();await reached;f.c.state={projectId:'p2'};f.c.assistant.ticket++;f.c.assistant.id='new';resolve({id:'old',running:false});await pending;assert.equal(f.c.assistant.id,'new');
});
test('stale polling cannot overwrite job or clear another project polling state',async()=>{
 const f=fixture();f.c.assistant.id='old';let resolve;f.c.api=()=>new Promise(r=>resolve=r);const pending=f.c.conversationPoll();f.c.state={projectId:'p2'};f.c.assistant.ticket++;f.c.assistant.polling='new-poll';resolve({id:'old',running:false});await pending;assert.equal(f.c.assistant.job,null);assert.equal(f.c.assistant.polling,'new-poll');
});
test('unchanged poll response does not rerender the conversation',async()=>{
 const f=fixture();f.c.assistant.id='job';f.c.assistant.job={id:'job',revision:5};let renders=0;f.c.conversationRender=()=>renders++;f.c.api=async()=>({unchanged:true,running:true});await f.c.conversationPoll();assert.equal(renders,0);assert.equal(f.c.assistant.job.revision,5);
});
test('source association converts browser offsets to Unicode code points',async()=>{
 const f=fixture();f.c.writing={mode:'source',file:'main.tex',full:'a😀text',range:{start:1,end:3}};await f.c.conversationContext();assert.equal(f.c.assistant.contexts[0].start,1);assert.equal(f.c.assistant.contexts[0].end,2);await f.c.conversationContext();assert.equal(f.c.assistant.contexts.length,1);
});
test('PDF association adds selected pages without sending all document pages',async()=>{
 const f=fixture();f.c.writing={mode:'pdf',pages:new Set([2,4])};await f.c.conversationContext();assert.deepEqual(Array.from(f.c.assistant.pages),[2,4]);
});
test('dirty buffers cannot be associated as stale disk selections',async()=>{
 const f=fixture();f.c.models.set('main.tex',{dirty:true});await assert.rejects(f.c.conversationContext(),/保存/);
});
test('new frontend is loaded after the document workbench and registers both modes',()=>{
 const html=fs.readFileSync(__dirname+'/web/index.html','utf8'),js=fs.readFileSync(__dirname+'/web/document-assistant.js','utf8');assert.ok(html.indexOf('src="/document-assistant.js"')>html.indexOf('src="/writing-continuous.js"'));assert.match(js,/data-assistant-mode="chat"/);assert.match(js,/data-assistant-mode="agent"/);assert.match(js,/role="separator"/);
});
test('composer dragging is clamped and supports keyboard resizing',()=>{
 const f=fixture(),handle=f.$('#conversationComposerResize'),panel=f.$('#studioConversation');const values=[];panel.clientHeight=600;panel.style={setProperty:(name,value)=>values.push(value)};handle.setPointerCapture=()=>{};handle.hasPointerCapture=()=>true;handle.releasePointerCapture=()=>{};
 f.c.conversationSetupResize();handle.onpointerdown({button:0,clientY:300,pointerId:1,preventDefault(){}});handle.onpointermove({pointerId:1,clientY:-500});assert.equal(values.at(-1),'390px');handle.onkeydown({key:'Home',preventDefault(){}});assert.equal(values.at(-1),'150px');
});

test('tool progress merges start and finish instead of counting them twice',()=>{const f=fixture();const steps=f.c.conversationToolSteps([{tool:'thinking',status:'done'},{tool:'read_file',status:'running',detail:'main.tex'},{tool:'read_file',status:'done',detail:'已完成'}]);assert.equal(steps.length,2);assert.equal(steps[0].narrative,true);assert.equal(steps[1].status,'done');assert.match(steps[1].detail,/main.tex/);});
test('answers show readable structure while escaping document HTML',()=>{const f=fixture();const html=f.c.conversationMessageHtml('## 检查结果\n- **字号**过小\n<script>alert(1)</script>');assert.match(html,/conversation-answer-heading/);assert.match(html,/<strong>字号<\/strong>/);assert.ok(!html.includes('<script>'));});

test('stop requested before start returns is applied to the newly created job',async()=>{
 const f=fixture();f.$('#conversationInput').value='Pending';let resolveStart,entered;const reached=new Promise(r=>entered=r);
 f.c.api=async(path,data)=>{f.calls.push([path,data]);if(path.endsWith('/start'))return new Promise(r=>{resolveStart=r;entered();});if(path.endsWith('/cancel'))return {id:'new-job',revision:3,running:false};return {id:'new-job',revision:3,running:false};};
 const sending=f.c.conversationSend();await reached;await f.c.conversationStop();assert.equal(f.c.assistant.stopping,true);resolveStart({id:'new-job',revision:1,running:true});await sending;assert.equal(f.calls.find(x=>x[0].endsWith('/cancel'))[1].id,'new-job');assert.equal(f.c.assistant.job.running,false);
});
test('older running poll cannot resurrect a cancelled job',async()=>{
 const f=fixture();f.c.assistant.id='job';f.c.assistant.job={id:'job',revision:9,running:false};f.c.api=async()=>({id:'job',revision:2,running:true});await f.c.conversationPoll();assert.equal(f.c.assistant.job.running,false);assert.equal(f.c.assistant.job.revision,9);
});
test('stop failure permits retry instead of leaving the control disabled',async()=>{
 const f=fixture();f.c.assistant.id='job';f.c.assistant.job={id:'job',running:true};f.c.api=async()=>{throw new Error('offline');};await assert.rejects(f.c.conversationStop(),/offline/);assert.equal(f.c.assistant.stopping,false);
});

test('empty conversation renders without dereferencing a missing work log',()=>{
 const f=fixture(),list=f.$('#conversationMessages');Object.assign(list,{scrollHeight:0,scrollTop:0,clientHeight:300,querySelector:()=>null,insertAdjacentHTML(position,html){this.innerHTML+=html;}});f.c.realRender();assert.match(list.innerHTML,/conversation-empty/);
});

test('candidate effect and source actions route to the interactive document tabs',async()=>{
 const f=fixture(),views=[];f.c.writingSetView=view=>views.push(view);f.c.catShowDiff=async path=>f.calls.push(path);
 await f.c.conversationPreview();await f.c.conversationDiff('main.tex');assert.deepEqual(views,['comparison','diff']);assert.equal(f.calls[0],'main.tex');
});
test('display math keeps multiline formulas intact and code remains escaped',()=>{
 const f=fixture(),html=f.c.conversationMessageHtml('Formula:\n\\[\n\\frac{1}{2} + x^2\n\\]\n```tex\n<script>\n```');
 assert.match(html,/cat-math-raw/);assert.match(html,/fraction|frac/);assert.ok(!html.includes('<script>'));
});
