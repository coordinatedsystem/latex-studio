"""Maintain release artifacts and known developer caches; report-only unless --clean.

Never rewrites Git history. Runtime data/preview caches are excluded. Cached project
and settings snapshots are backed up and byte-verified before any cache is removed.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,stat,subprocess,time,urllib.error,urllib.parse,urllib.request,zipfile

CACHE_NAMES=('deepseek-harness-source','assistant-ui-160','release-1.6.0','terms-ui-1.4.1')

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def junction(path):
    try:return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError,AttributeError):return False

def files(path):
    for current,dirs,names in os.walk(path,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(current)/d).is_symlink() and not junction(Path(current)/d)]
        for name in names:
            p=Path(current)/name
            if not p.is_symlink():yield p

def size(path):return sum(p.stat().st_size for p in files(path))

def git(repo,*args):return subprocess.check_output(['git',*args],cwd=repo,stderr=subprocess.DEVNULL).decode().strip()

def installer_plan(repo,latest):
    result=[]
    for path in sorted((repo/'distribution').glob('LaTeX-Studio-*-win64-Setup.exe')):
        match=re.fullmatch(r'LaTeX-Studio-(\d+\.\d+\.\d+)-win64-Setup[.]exe',path.name)
        if not match or path.name==Path(latest['file']).name:continue
        relative=path.relative_to(repo).as_posix();tag='v'+match[1]
        try:
            unchanged=subprocess.run(['git','diff','--quiet','HEAD','--',relative],cwd=repo,stderr=subprocess.DEVNULL).returncode==0
            recoverable=git(repo,'rev-parse','--verify',tag+':'+relative)==git(repo,'hash-object',str(path)) and unchanged
        except subprocess.CalledProcessError:recoverable=False
        result.append({'path':relative,'tag':tag,'bytes':path.stat().st_size,'recoverable':recoverable})
    return result

def guard(path,cache):
    path=Path(path);cache=Path(cache).resolve()
    if path.name not in CACHE_NAMES or path.is_symlink() or junction(path) or path.resolve().parent!=cache:raise ValueError('Unexpected cache cleanup path')
    return path.resolve()

def protected(base):
    result={}
    for folder in ('data','projects'):
        for path in files(base/folder):
            if path.name!='runtime.json':result[str(path.relative_to(base))]=sha(path)
    return result

def backup_state(path,archive):
    selected=[]
    for relative in ('data','projects','installed/data','installed/projects'):
        folder=path/relative
        if folder.is_symlink() or junction(folder):raise ValueError('Linked cached state must be preserved manually')
        if folder.is_dir():selected.extend(files(folder))
    if not selected:return None
    archive.mkdir(parents=True,exist_ok=True);target=archive/(path.name+'-state.zip')
    if target.exists():raise ValueError('State archive already exists')
    hashes={p.relative_to(path).as_posix():sha(p) for p in selected}
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
        for p in selected:output.write(p,p.relative_to(path).as_posix())
    with zipfile.ZipFile(target) as saved:
        for name,value in hashes.items():
            if hashlib.sha256(saved.read(name)).hexdigest()!=value:raise ValueError('Cache state backup failed verification')
    return {'path':str(target),'files':len(hashes),'bytes':target.stat().st_size}

def verify_application(base,repo):
    manifest=json.loads((repo/'build-manifest.json').read_text('utf8'));checked=0
    for entry in manifest['files']:
        if not entry['path'].startswith('app/'):continue
        path=(base/entry['path']).resolve()
        if not path.is_relative_to((base/'app').resolve()) or not path.is_file() or sha(path)!=entry['sha256']:raise ValueError('Installed application integrity mismatch: '+entry['path'])
        checked+=1
    return checked

def runtime_idle(base):
    path=base/'data/runtime.json'
    if not path.is_file():return 'not-running'
    info=json.loads(path.read_text('utf-8-sig'));parts=urllib.parse.urlsplit(info.get('url',''))
    if parts.hostname not in {'127.0.0.1','localhost'}:raise ValueError('Unexpected runtime origin')
    token=urllib.parse.parse_qs(parts.query).get('token',[''])[0]
    request=urllib.request.Request('http://127.0.0.1:'+str(info['port'])+'/api/state',headers={'Cookie':'studio_token='+token})
    try:
        with urllib.request.urlopen(request,timeout=5) as response:state=json.load(response)
    except urllib.error.HTTPError:raise ValueError('Runtime answered but its state could not be verified') from None
    except OSError:return 'not-connected'
    if any(state.get(key) for key in ('running','aiBusy','packageBusy','pagePreviewBusy')):raise ValueError('Studio has active work; maintenance was not started')
    return 'idle'

def remove_readonly(function,path,error):
    os.chmod(path,stat.S_IWRITE);function(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--clean',action='store_true');args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1];base=repo.parent;cache=base/'cache'
    latest=json.loads((repo/'updates/latest.json').read_text('utf8'));setup=(repo/latest['file']).resolve()
    if setup.parent!=(repo/'distribution').resolve() or not setup.is_file() or setup.stat().st_size!=latest['size'] or sha(setup)!=latest['sha256']:raise ValueError('Current installer is missing or changed; no files removed')
    installed=(base/'app/installation.json').is_file() and repo.name=='repository'
    candidates=[guard(cache/name,cache) for name in CACHE_NAMES if installed and (cache/name).is_dir()]
    plan=installer_plan(repo,latest);report={'at':time.strftime('%Y-%m-%d %H:%M:%S'),'version':latest['version'],'installerVerified':True,'mode':'clean' if args.clean else 'report','workspaceBytesBefore':size(base) if installed else None,'oldInstallers':plan,'developerCaches':[{'path':str(p),'bytes':size(p)} for p in candidates]}
    if args.clean:
        if not installed:raise ValueError('Cleanup is restricted to the installed workspace')
        report['runtime']=runtime_idle(base);report['appFilesVerified']=verify_application(base,repo);before=protected(base);refs=git(repo,'show-ref','--heads','--tags')
        archive=base/'archive'/('maintenance-'+time.strftime('%Y%m%d-%H%M%S'));report['backups']=[]
        for path in candidates:
            target=guard(path,cache)
            if target.name=='deepseek-harness-source':
                pinned=cache/'deepseek-harness-pinned'
                if not pinned.is_dir() or git(target,'status','--porcelain') or git(target,'rev-parse','HEAD')!=git(pinned,'rev-parse','HEAD'):raise ValueError('Developer source differs from its retained reference; cache preserved')
            for test_root in (target,target/'installed'):
                if (test_root/'data/runtime.json').is_file() and runtime_idle(test_root)=='idle':raise ValueError('Close the temporary developer server before removing its cache')
            backup=backup_state(target,archive)
            if backup:report['backups'].append(backup)
            shutil.rmtree(target,onerror=remove_readonly)
        recoverable=[item['path'] for item in plan if item['recoverable']]
        if recoverable:subprocess.run(['git','rm','--',*recoverable],cwd=repo,check=True,stdout=subprocess.DEVNULL)
        report['protectedDataUnchanged']=before==protected(base);report['gitReferencesUnchanged']=refs==git(repo,'show-ref','--heads','--tags')
        if not report['protectedDataUnchanged'] or not report['gitReferencesUnchanged']:raise ValueError('Protected data or Git refs changed during maintenance; inspect concurrent activity')
        report['workspaceBytesAfter']=size(base);report['reclaimedBytes']=report['workspaceBytesBefore']-report['workspaceBytesAfter']
    output=base/'release-verification'/('maintenance-'+time.strftime('%Y%m%d-%H%M%S')+'.json') if installed else None
    if output:output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
