// Regression checks for preview loading, independent of a browser or user files.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/web/app.js','utf8');
const setPdfCode='async function setPdf('+source.split('async function setPdf(')[1].split('\nfunction themePdf')[0];

function fixture({status=200,body='%PDF-1.5\n',missingViewer=false}={}){
 const events=[],errors=[],phases=[],requests=[],handlers=new Map(),frameListeners=new Map();let pagesReady=false;
 const bus={on(name,fn){const group=handlers.get(name)||new Set();group.add(fn);handlers.set(name,group);},off(name,fn){handlers.get(name)?.delete(fn);},emit(name,event={}){for(const fn of [...(handlers.get(name)||[])])fn(event);}};
 const viewer={set currentScaleValue(value){assert.ok(pagesReady,'Do not set scale before pagesinit');events.push('scale');}};
 const app={page:1,pdfDocument:{numPages:24},initializedPromise:Promise.resolve(),eventBus:bus,pdfViewer:viewer,
  async open(){events.push('open');setTimeout(()=>{pagesReady=true;events.push('pagesinit');bus.emit('pagesinit');setTimeout(()=>{events.push('pagerendered');bus.emit('pagerendered');},0);},0);}};
 const frame={contentWindow:{PDFViewerApplication:missingViewer?null:app},
  addEventListener(name,fn){frameListeners.set(name,fn);},removeEventListener(name,fn){if(frameListeners.get(name)===fn)frameListeners.delete(name);},
  set src(value){queueMicrotask(()=>frameListeners.get('load')?.());}};
 const nodes={'#pdfFrame':frame,'#noPdf':{},'#previewMessageText':{}};
 const sandbox={console,Uint8Array,Blob,AbortController,Promise,String,Math,Error,setTimeout,clearTimeout,
  URL:{createObjectURL:()=> 'blob:local/verified-pdf',revokeObjectURL(){}},
  lastPdf:0,pdfTicket:0,pdfAbort:null,pdfBlobUrl:'',previewLastError:'',pdfPages:0,prefs:{main:'report.tex'},state:{projectId:'project-test'},
  $:selector=>nodes[selector],themePdf(){},previewStatus(phase,message,detail){phases.push({phase,message,detail});events.push(phase);},
  logPreviewError(message){errors.push(message);},useNativePreview(){phases.push({phase:'native'});},
  async fetch(url,options){requests.push({url,options});return{ok:status===200,status,async arrayBuffer(){return Uint8Array.from(Buffer.from(body)).buffer;}};},
  deadline:promise=>promise,
 };
 vm.createContext(sandbox);vm.runInContext(setPdfCode,sandbox);
 return {sandbox,events,errors,phases,handlers,requests};
}

test('waits for pagesinit and a rendered page before showing the page count',async()=>{
 const f=fixture();await f.sandbox.setPdf(1);
 assert.equal(f.phases.at(-1).phase,'ready');assert.equal(f.phases.at(-1).message,'24 页');
 assert.ok(f.events.indexOf('pagesinit')<f.events.indexOf('scale'));
 assert.ok(f.events.indexOf('pagerendered')<f.events.indexOf('ready'));
 assert.equal(f.errors.length,0);assert.equal(f.handlers.get('pagesinit').size,0);
 assert.equal(f.requests[0].options.headers['X-Studio-Project'],'project-test');
 assert.equal(f.handlers.get('pagerendered').size,0);
});
test('a stale session shows an explicit recovery message instead of a blank viewer',async()=>{
 const f=fixture({status:401});await f.sandbox.setPdf(2);
 assert.equal(f.phases.at(-1).phase,'error');assert.match(f.phases.at(-1).detail,/会话/);
 assert.ok(!f.events.includes('open'));
});
test('rejects a successful HTTP response containing HTML instead of a PDF',async()=>{
 const f=fixture({body:'<html>error</html>'});await f.sandbox.setPdf(3);
 assert.equal(f.phases.at(-1).phase,'error');assert.match(f.phases.at(-1).detail,/有效的 PDF/);
});
test('offers the native reader only after the PDF bytes have been validated',async()=>{
 const f=fixture({missingViewer:true});await f.sandbox.setPdf(4);
 assert.equal(f.phases.at(-1).phase,'native');assert.equal(f.sandbox.pdfBlobUrl,'blob:local/verified-pdf');
 assert.equal(f.errors.length,1);
});
