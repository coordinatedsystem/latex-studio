/* Loaded before PDF.js modules to report startup/worker failures to our host. */
(() => {
  if (new URLSearchParams(location.search).get('studio') !== '1') return;
  const report = message => parent.postMessage({type:'studio-pdf-error',message:String(message||'PDF 阅读器启动失败')},location.origin);
  addEventListener('error', event => report(event.message || event.error?.message));
  addEventListener('unhandledrejection', event => report(event.reason?.message || event.reason));
})();
