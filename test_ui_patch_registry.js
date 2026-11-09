const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function load(){
 const source=fs.readFileSync(path.join(__dirname,'web','ui-patch-registry.js'),'utf8');
 const c=vm.createContext({console});
 vm.runInContext(source+';this.registry=uiPatchRegistry;',c);
 return c.registry;
}

test('wrap returns the builder output and still calls through to the target',()=>{
 const registry=load();
 const seen=[];
 const target=function(...args){seen.push(['target',...args]);};
 const wrapped=registry.wrap('demo',target,'a.js',previous=>function(...args){seen.push(['patch']);previous(...args);});
 wrapped(1,2);
 assert.deepEqual(seen,[['patch'],['target',1,2]]);
});

test('a missing target fails loudly instead of silently dropping the patch',()=>{
 const registry=load();
 assert.throws(
  ()=>registry.wrap('renderHome',undefined,'hub-design.js',previous=>function(){previous();}),
  /found no target function.*hub-design\.js.*index\.html/s
 );
});

test('a non-function target is rejected the same way as a missing one',()=>{
 const registry=load();
 assert.throws(()=>registry.wrap('x',{},'a.js',()=>function(){}),/found no target function/);
});

test('two files may chain onto the same target in load order',()=>{
 const registry=load();
 const order=[];
 let target=function(){order.push('base');};
 target=registry.wrap('hubNotifyState',target,'editor-ai.js',previous=>function(next){order.push('editor-ai');previous(next);});
 target=registry.wrap('hubNotifyState',target,'hub-design.js',previous=>function(next){order.push('hub-design');previous(next);});
 target('state');
 assert.deepEqual(order,['hub-design','editor-ai','base']);
 assert.deepEqual([...registry.describe()],['hubNotifyState <- editor-ai.js','hubNotifyState <- hub-design.js']);
});

test('the same file may not patch one target twice',()=>{
 const registry=load();
 const target=function(){};
 registry.wrap('run',target,'updates.js',()=>function(){});
 assert.throws(()=>registry.wrap('run',target,'updates.js',()=>function(){}),/applied twice by the same file/);
});

test('builder must be a function and owner must be named',()=>{
 const registry=load();
 assert.throws(()=>registry.wrap('x',function(){},'a.js',null),/needs a builder function/);
 assert.throws(()=>registry.wrap('x',function(){},'',()=>function(){}),/needs an owner file name/);
});

// Guards the real wiring: every uiPatchRegistry.wrap() call must sit in a file
// that index.html loads after the file declaring its target. This is the check
// that would have caught a silently dropped patch.
test('every wrap call in web/ loads after the file declaring its target',()=>{
 const web=path.join(__dirname,'web');
 const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
 const loadOrder=[...html.matchAll(/src="\/([a-z0-9-]+\.js)"/g)].map(m=>m[1]);
 const position=name=>loadOrder.indexOf(name);

 const callers=[];
 for(const file of fs.readdirSync(web).filter(f=>f.endsWith('.js'))){
  const source=fs.readFileSync(path.join(web,file),'utf8');
  for(const m of source.matchAll(/uiPatchRegistry\.wrap\(\s*'([^']+)'\s*,\s*([A-Za-z_$][\w$]*)\s*,\s*'([^']+)'/g)){
   callers.push({target:m[1],global:m[2],owner:m[3],file});
  }
 }
 assert.ok(callers.length>=10,`expected the known patch sites, found ${callers.length}`);

 for(const call of callers){
  assert.equal(call.owner,call.file,`${call.file} must name itself as the owner, found "${call.owner}"`);
  assert.ok(position(call.file)>-1,`${call.file} applies a UI patch but index.html never loads it`);
  const declaring=loadOrder.find(name=>{
   if(name===call.file||name==='ui-patch-registry.js')return false;
   const source=fs.readFileSync(path.join(web,name),'utf8');
   return new RegExp(`^(?:async )?function ${call.global}\\b`,'m').test(source);
  });
  assert.ok(declaring,`nothing declares ${call.global} used by ${call.file}`);
  assert.ok(position(declaring)<position(call.file),
   `${call.file} patches ${call.global} but loads before ${declaring}, which declares it`);
  assert.ok(position('ui-patch-registry.js')<position(call.file),
   `${call.file} patches ${call.global} before ui-patch-registry.js loads`);
 }
});
