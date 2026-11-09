/* Synchronize the embedded PDF canvas and selectable text after pane resizing. */
(()=>{
 const frame=document.getElementById('pdfFrame');if(!frame)return;
 let timer=null,lastWidth=0,lastHeight=0;
 const sync=()=>{
  timer=null;if(frame.clientWidth<=0||frame.clientHeight<=0)return;
  try{
   const app=frame.contentWindow?.PDFViewerApplication;
   if(!app?.pdfDocument||!app.pdfViewer||!app.eventBus)return;
   // Let PDF.js update both layers together and preserve its zoom/scroll anchor.
   app.eventBus.dispatch('resize',{source:frame.contentWindow});
  }catch{/* The native PDF fallback is not a same-origin PDF.js frame. */}
 };
 const schedule=()=>{
  clearTimeout(timer);timer=setTimeout(sync,120);
 };
 new ResizeObserver(()=>{
  const width=frame.clientWidth,height=frame.clientHeight;
  if(width===lastWidth&&height===lastHeight)return;
  lastWidth=width;lastHeight=height;schedule();
 }).observe(frame);
 frame.addEventListener('load',schedule);
 window.addEventListener('pointerup',schedule);
 window.addEventListener('pointercancel',schedule);
})();
