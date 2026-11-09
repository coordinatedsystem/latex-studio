const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const timers=new Map(),calls=[],listeners={};let observer,id=0;
 const app={pdfDocument:{},pdfViewer:{currentScaleValue:1.25},eventBus:{dispatch:(name,data)=>calls.push(name)}};
 const frame={clientWidth:500,clientHeight:700,contentWindow:{PDFViewerApplication:app},addEventListener:(name,fn)=>listeners['frame:'+name]=fn};
 vm.runInNewContext(fs.readFileSync(__dirname+'/web/pdf-resize.js','utf8'),{document:{getElementById:()=>frame},window:{addEventListener:(name,fn)=>listeners[name]=fn},ResizeObserver:class{constructor(fn){observer=fn;}observe(){}},setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key)});
 return {frame,app,calls,listeners,resize:()=>observer(),flush:()=>{for(const fn of timers.values())fn();timers.clear();},timers};
}
test('pane resize resynchronizes PDF.js once after movement settles and preserves explicit zoom',()=>{const f=fixture();f.resize();f.frame.clientWidth=650;f.resize();f.frame.clientHeight=420;f.resize();assert.equal(f.timers.size,1);assert.deepEqual(f.calls,[]);f.flush();assert.deepEqual(f.calls,['resize']);assert.equal(f.app.pdfViewer.currentScaleValue,1.25);});
test('same-size notifications do not create a resize loop and hidden panes are skipped',()=>{const f=fixture();f.resize();f.flush();f.resize();assert.equal(f.timers.size,0);f.frame.clientWidth=0;f.resize();f.flush();assert.equal(f.calls.length,1);});
test('drag release synchronizes even when the final frame resize notification was coalesced',()=>{const f=fixture();f.listeners.pointerup();f.flush();assert.deepEqual(f.calls,['resize']);f.app.pdfDocument=null;f.listeners['frame:load']();f.flush();assert.equal(f.calls.length,1);});
