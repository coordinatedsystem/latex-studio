"""Build only reviewed app files, standalone runtime and official bundle resources."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
from audit_release import audit

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_app(repo, app):
    """Check every shipped module and frontend asset against its source."""
    repo,app=Path(repo),Path(app)
    expected={p.relative_to(repo) for folder in ('web','vendor','assets') for p in (repo/folder).rglob('*') if p.is_file()}
    expected.update(Path(p.name) for p in repo.glob('studio_*.py'))
    expected.update(map(Path, ('server.py','bootstrap_install.py','launch.ps1','Launch.vbs','version.json','README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md')))
    bad=[str(p) for p in sorted(expected) if not (app/p).is_file() or sha(repo/p)!=sha(app/p)]
    bad.extend(str(p.relative_to(app))+' (unexpected)' for p in app.rglob('*') if p.is_file() and p.relative_to(app) not in expected)
    if bad:raise ValueError('Application payload missing or changed: '+', '.join(bad))
    return len(expected)
def verify_python(payload):
    required=['python.exe','pythonw.exe','python313.dll','python313.zip','python313._pth',
              'Lib/site-packages/pypdf/__init__.py','Lib/site-packages/pypdfium2/__init__.py',
              'Lib/site-packages/pdfplumber/__init__.py','Lib/site-packages/PIL/__init__.py']
    missing=[name for name in required if not (Path(payload)/'python'/name).is_file()]
    if missing:raise ValueError('Standalone Python payload missing: '+', '.join(missing))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True);parser.add_argument('--tex-cache',required=True);parser.add_argument('--payload',required=True);parser.add_argument('--iscc',required=True)
    args=parser.parse_args();repo=Path(__file__).resolve().parents[1];payload=Path(args.payload).resolve();runtime=Path(args.runtime).resolve();cache=Path(args.tex_cache).resolve()
    info=json.loads((repo/'version.json').read_text('utf8'));version=info['version']
    audit(repo)
    verify_python(payload)
    app=payload/'app';app.mkdir(parents=True,exist_ok=True)
    for folder in ['web','vendor','assets']:shutil.copytree(repo/folder,app/folder,dirs_exist_ok=True)
    names=['server.py','studio_version.py','bootstrap_install.py','launch.ps1','Launch.vbs','version.json','README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md']
    names+= [p.name for p in repo.glob('studio_*.py') if p.name not in names]
    for name in names:shutil.copy2(repo/name,app/name)
    verify_app(repo,app)
    shutil.copy2(repo/'Launch.vbs',payload/'Launch.vbs')
    compiler=payload/'runtime/bin';compiler.mkdir(parents=True,exist_ok=True)
    shutil.copy2(runtime/'bin/tectonic.exe',compiler/'tectonic.exe');shutil.copy2(runtime/'release.json',payload/'runtime/release.json')
    # Only canonical public bundle names; never copy local format caches or project data.
    indices=list((cache/'bundles/data').glob('*.index'))
    if len(indices)!=1:raise ValueError('Expected one pinned TeX resource index')
    index=indices[0];dest=payload/'cache/tectonic/bundles/data';dest.mkdir(parents=True,exist_ok=True);shutil.copy2(index,dest/index.name)
    allowed={}
    for line in index.read_text('utf8').splitlines():
        parts=line.rsplit(' ',2)
        if len(parts)==3:allowed[parts[0]]=int(parts[2])
    resources=cache/'bundles/data'/index.stem;target=dest/index.stem;target.mkdir(exist_ok=True)
    for p in resources.iterdir():
        if not p.is_file() or p.name not in allowed or p.stat().st_size!=allowed[p.name]:continue
        shutil.copy2(p,target/p.name)
    if (cache/'bundles/hashes').is_dir():shutil.copytree(cache/'bundles/hashes',payload/'cache/tectonic/bundles/hashes',dirs_exist_ok=True)
    audit(app)
    manifest=[{'path':p.relative_to(payload).as_posix(),'size':p.stat().st_size,'sha256':sha(p)} for p in payload.rglob('*') if p.is_file()]
    (repo/'build-manifest.json').write_text(json.dumps({'version':version,'files':manifest},ensure_ascii=False,indent=2),'utf8')
    output=repo/'distribution';output.mkdir(exist_ok=True)
    subprocess.run([args.iscc,'/Qp','/DPayload='+str(payload),'/DOutput='+str(output),'/DAppVersion='+version,str(repo/'installer/LaTeXStudio.iss')],check=True)
    setup=output/f'LaTeX-Studio-{version}-win64-Setup.exe'
    if setup.stat().st_size>=100*1024*1024:raise ValueError('Installer exceeds repository publication limit; use release assets instead')
    checksum=sha(setup);(output/'SHA256SUMS.txt').write_text(checksum+'  '+setup.name+'\n','utf8')
    updates=repo/'updates';updates.mkdir(exist_ok=True)
    (updates/'latest.json').write_text(json.dumps({'version':version,'file':'distribution/'+setup.name,'size':setup.stat().st_size,'sha256':checksum,'notes':'LaTeX Studio '+version+'：本地编辑、PDF、宏包管理、AI 审阅与安全更新。'},ensure_ascii=False,indent=2),'utf8')
    audit(repo);print('Installer ready:',setup.name,setup.stat().st_size,'bytes',flush=True)
if __name__=='__main__':main()
