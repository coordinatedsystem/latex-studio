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
const toggleCode=source.slice(source.indexOf('async function toggleNativePreview'),source.indexOf('async function setPdf'));
test('system preview toggles back to the built-in reader and preserves a candidate PDF',async()=>{
 const calls=[];const c=vm.createContext({pdfPhase:'native',lastPdf:5,state:{pdfVersion:5},editorAiPreview:{id:'candidate',project:'project',version:5},encodeURIComponent,useNativePreview:()=>calls.push('native'),setPdf:(...args)=>calls.push(args)});
 vm.runInContext(toggleCode,c);await c.toggleNativePreview();assert.equal(calls[0][1],true);assert.equal(calls[0][2],false);assert.match(calls[0][4],/candidate/);
 c.pdfPhase='ready';await c.toggleNativePreview();assert.equal(calls[1],'native');
});
test('source navigation recovers from an inaccessible system PDF frame',async()=>{
 const navigation=fs.readFileSync(__dirname+'/web/reference-navigation.js','utf8');const code=navigation.slice(navigation.indexOf('async function studioPdfApplication'),navigation.indexOf('async function studioHighlightPdf'));
 let recovered=false;const viewer={pdfDocument:{}};const frame={get contentWindow(){if(!recovered)throw new Error('cross-origin system reader');return {PDFViewerApplication:viewer};}};
 const c=vm.createContext({editorAiPreview:null,state:{hasPdf:true,pdfVersion:3},$:()=>frame,setPdf:async()=>{recovered=true;}});vm.runInContext(code,c);assert.equal(await c.studioPdfApplication(),viewer);
});

test('removing the duplicate locator does not prevent PDF navigation binding',()=>{
 const code=fs.readFileSync(__dirname+'/web/reference-navigation.js','utf8');const start=code.indexOf('function referenceInstallNavigation'),end=code.lastIndexOf('referenceInstallBrowser();');const nodes=new Map();let bound=0;
 const $=selector=>{if(selector==='#workflowLocate')return null;if(!nodes.has(selector))nodes.set(selector,{classList:{toggle(){}},insertAdjacentHTML(){},addEventListener(name,fn){this[name]=fn;}});return nodes.get(selector);};
 const c=vm.createContext({$,document:{addEventListener(){}},studioLocatePdf:async()=>{},studioPdfApplication:async()=>({}),studioBindPdfNavigation:()=>bound++,studioPickMode(){},sourceNavigation:{pick:false},editorToolOpen(){},toast(){}});vm.runInContext(code.slice(start,end),c);c.referenceInstallNavigation();assert.equal(typeof $('#syncInverse').onclick,'function');assert.equal(typeof $('#pdfFrame').load,'function');assert.equal(bound,1);
});
