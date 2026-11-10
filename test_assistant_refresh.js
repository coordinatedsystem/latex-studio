const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const timers=new Map();let id=0,count=0;
 const c=vm.createContext({writing:{context:{id:'context'},job:{id:'job',running:false},selected:new Set([0]),busy:false,stale:false,applied:false},state:{running:false},writingSamePreview:()=>false,writingPreview:async()=>{count++;},writingWatch:fn=>fn,setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key)});
 let source=fs.readFileSync(__dirname+'/web/assistant-refresh.js','utf8');source=source.slice(0,source.indexOf('function assistantRefreshInstall'));vm.runInContext(source,c);
 return {c,timers,count:()=>count,queue:()=>vm.runInContext('assistantQueuePreview()',c),flush:async()=>{for(const fn of timers.values())await fn();timers.clear();}};
}
test('automatically compiles a candidate once, without looping on failed previews',async()=>{const f=setup();f.queue();f.queue();assert.equal(f.timers.size,1);await f.flush();assert.equal(f.count(),1);f.queue();await f.flush();assert.equal(f.count(),1);});
test('deselecting or switching context cancels a queued preview',async()=>{const f=setup();f.queue();f.c.writing.selected.clear();f.queue();await f.flush();assert.equal(f.count(),0);f.c.writing.selected.add(0);f.queue();f.c.writing.context=null;await f.flush();assert.equal(f.count(),0);});

