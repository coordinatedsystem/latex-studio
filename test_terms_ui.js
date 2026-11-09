const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(){
 const nodes=new Map(),calls=[];const node=s=>{if(!nodes.has(s))nodes.set(s,{disabled:false,hidden:false,textContent:'',innerHTML:'',classList:{toggle(){}},querySelectorAll:()=>[],replaceChildren(){this.innerHTML='';},insertAdjacentHTML(){}});return nodes.get(s);};
 const c=vm.createContext({console,Set,Map,Promise,JSON,encodeURIComponent,state:{projectId:'p',running:false,aiBusy:false},models:new Map(),$ :node,$$:()=>[],esc:x=>String(x),reviewGuard:p=>{if(p!=='p')throw Error('project changed');},glossaryData:{terms:[{source:'反向传播',target:'existing translation',note:'keep'}],revision:'original'},glossaryDirty:false,glossaryRender(){},toast(){},api:async(route,data)=>{calls.push({route,data});if(route==='review/glossary')return {...data,revision:'new'};return {id:'plan',count:1,changes:[]};}});
 let source=fs.readFileSync(__dirname+'/web/terms-desk.js','utf8');source=source.slice(0,source.indexOf('function termsInstall'));
 vm.runInContext(source,c);vm.runInContext("termsDesk.project='p';termsDesk.result={id:'task',applied:false,groups:[{id:0,preferred:'反向传播',target:'backpropagation',relation:'same'},{id:1,preferred:'梯度下降',target:'gradient descent',relation:'related'}]};termsDesk.chosen=new Set([0,1]);",c);
 return {c,node,calls};
}
test('normalization preview sends only confirmed synonym groups',async()=>{const {c,calls}=setup();await vm.runInContext('termsPreview()',c);assert.equal(calls[0].route,'review/terms-plan');assert.deepEqual(JSON.parse(JSON.stringify(calls[0].data.choices)),[{id:0,preferred:'反向传播'}]);});
test('glossary import deduplicates existing terms without overwriting translations',async()=>{const {c,calls}=setup();await vm.runInContext('termsImport()',c);const saved=calls[0].data;assert.equal(saved.terms.length,2);assert.equal(saved.terms[0].target,'existing translation');assert.equal(saved.revision,'original');assert.equal(c.glossaryData.revision,'new');});
test('unsaved source blocks term application before any request',async()=>{const {c,calls}=setup();c.models.set('main.tex',{dirty:true});await assert.rejects(vm.runInContext('termsApply()',c),/未保存/);assert.equal(calls.length,0);});
test('compiling locks actions and applied results still allow glossary imports',()=>{const {c,node}=setup();c.state.running=true;vm.runInContext('termsControls()',c);assert.equal(node('#termsExtract').disabled,true);c.state.running=false;vm.runInContext('termsDesk.result.applied=true;termsDesk.plan={count:1};termsControls()',c);assert.equal(node('#termsApply').disabled,true);assert.equal(node('#termsImport').disabled,false);assert.equal(node('#termsUndo').hidden,false);});

test('stop immediately acknowledges cancellation and sends the current task id',async()=>{const {c,node,calls}=setup();vm.runInContext("termsDesk.job={id:'terms-running',running:true}",c);const pending=vm.runInContext('termsStop()',c);assert.match(node('#termsStatus').textContent,/正在停止/);await pending;assert.equal(calls[0].route,'ai/cancel');assert.equal(calls[0].data.id,'terms-running');assert.equal(node('#termsStop').disabled,false);});

test('document tools omit duplicate PDF locator while primary navigation stays available',()=>{const html=fs.readFileSync(__dirname+'/web/index.html','utf8'),workflow=fs.readFileSync(__dirname+'/web/workflow-tools.js','utf8');assert.doesNotMatch(html,/id="workflowLocate"/);assert.match(workflow,/async function workflowLocate/);assert.match(fs.readFileSync(__dirname+'/web/reference-navigation.js','utf8'),/定位 PDF/);});
