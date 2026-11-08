const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(saved={}){
 const elements=new Map(),storage=new Map(Object.entries(saved)),frames=new Map();let next=0;
 function element(id){if(elements.has(id))return elements.get(id);const classes=new Set(),handlers=new Map(),properties=new Map(),attrs=new Map();let capture=null;
  const node={id,clientWidth:id==='#editorAiPanel'?1200:1000,clientHeight:600,title:'',style:{setProperty:(k,v)=>properties.set(k,v)},properties,attrs,
   classList:{add:(...names)=>names.forEach(n=>classes.add(n)),remove:(...names)=>names.forEach(n=>classes.delete(n)),contains:n=>classes.has(n)},
   setAttribute:(k,v)=>attrs.set(k,v),prepend(n){elements.set('#'+n.id,n);},after(n){elements.set('#'+n.id,n);},querySelector(){return element('figure');},
   addEventListener(k,f){handlers.set(k,f);},fire(k,e={}){handlers.get(k)?.({button:0,pointerId:1,preventDefault(){},...e});},
   setPointerCapture:n=>capture=n,hasPointerCapture:n=>capture===n,releasePointerCapture(){capture=null;node.fire('lostpointercapture');},
   getBoundingClientRect:()=>({left:100,right:1300,top:100,bottom:700,width:1200,height:600})};elements.set(id,node);return node;
 }
 const context=vm.createContext({$:element,document:{body:element('body'),createElement:()=>element('new'+(++next))},localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)},
  editor:{layout(){}},editorAiDiffEditor:null,editorAiExpand(){},ResizeObserver:class{observe(){}},window:{addEventListener(){}},
  requestAnimationFrame:f=>{frames.set(++next,f);return next;},cancelAnimationFrame:id=>frames.delete(id)});
 vm.runInContext(fs.readFileSync(__dirname+'/web/editor-dock-resize.js','utf8'),context);
 return {element,storage,flush(){for(const [id,f] of frames){frames.delete(id);f();}}};
}
test('dock drag retains final pointer position even before next animation frame; height is bounded and saved',()=>{
 const {element,storage}=setup(),handle=element('#editorDockHeightResize'),workspace=element('#workspace');
 handle.fire('pointerdown');handle.fire('pointermove',{clientY:300});handle.fire('pointerup');
 assert.equal(workspace.properties.get('--studio-dock-height'),'400px');assert.ok(Number(storage.get('studio.editorDockHeight'))>.66);
 assert.equal(element('body').classList.contains('dragging'),false);
 handle.fire('pointerdown');handle.fire('pointermove',{clientY:-1000});handle.fire('pointerup');assert.equal(workspace.properties.get('--studio-dock-height'),'500px');
});
test('AI column and PDF comparison have independent widths, keyboard reset and persistence',()=>{
 const {element,storage}=setup(),column=element('#editorAiColumnResize'),comparison=element('#editorAiCompareResize');
 column.fire('pointerdown');column.fire('pointermove',{clientX:480});column.fire('pointerup');assert.equal(element('#editorAiPanel').properties.get('--studio-ai-compose-width'),'380px');
 comparison.fire('keydown',{key:'ArrowRight'});assert.equal(storage.get('studio.editorAiCompareRatio'),'52');
 column.fire('dblclick');assert.equal(storage.get('studio.editorAiComposeWidth'),'260');comparison.fire('keydown',{key:'Home'});assert.equal(storage.get('studio.editorAiCompareRatio'),'50');
});
test('saved height restores after workspace resize and cancellation clears drag state',()=>{
 const {element}=setup({'studio.editorDockHeight':'.5'}),handle=element('#editorDockHeightResize');
 handle.fire('keydown',{key:'ArrowUp'});assert.equal(element('#workspace').properties.get('--studio-dock-height'),'316px');
 handle.fire('pointerdown');handle.fire('pointercancel');assert.equal(element('body').classList.contains('editor-dock-dragging'),false);
});
