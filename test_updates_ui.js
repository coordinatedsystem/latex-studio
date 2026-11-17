const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function loadReleaseText(){
 const source=fs.readFileSync(__dirname+'/web/updates.js','utf8');
 const cut=source.slice(0,source.indexOf('async function showUpdates'));
 const context=vm.createContext({});
 vm.runInContext(cut+';this.releaseText=updateReleaseText;',context);
 return context.releaseText;
}
test('release text distinguishes updates, equal versions and a newer local build',()=>{
 const text=loadReleaseText();
 assert.equal(text({version:'1.9.0',relation:'newer',notes:''},'1.8.3'),'可更新至 v1.9.0');
 assert.equal(text({version:'1.8.3',relation:'same',notes:''},'1.8.3'),'最新版本 v1.8.3');
 assert.equal(text({version:'1.8.0',relation:'older',notes:''},'1.8.3'),'已发布 v1.8.0，本机 v1.8.3 更高');
 assert.match(text({version:'1.8.3',relation:'same',notes:'说明'},'1.8.3'),/说明/);
});
