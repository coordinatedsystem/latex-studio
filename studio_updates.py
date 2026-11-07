"""Explicit, hash-verified updates from the fixed GitHub repository."""
from pathlib import Path
import hashlib,json,re,subprocess,threading,urllib.request,urllib.error
from studio_storage import read_json,write_json
from studio_ai import seal,NoRedirect
from studio_version import VERSION,BUILD,REPOSITORY

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('版本号无效')
    return tuple(map(int,value.split('.')))

def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

class Updates:
    def __init__(self,store):
        self.store=store;self.path=store.data/'update-settings.json';self.lock=threading.RLock();self.release=None
        self.job={'running':False,'stage':'尚未检查','downloaded':0,'size':0};self.installer=None
    def status(self):
        with self.lock:
            config=read_json(self.path,{})
            return {'version':VERSION,'build':BUILD,'repository':REPOSITORY,'channel':'stable',
                    'automatic':bool(config.get('automatic',False)),'configured':bool(config.get('githubToken')),
                    'release':self.release,'job':dict(self.job),'ready':bool(self.installer and self.installer.is_file())}
    def configure(self,data):
        with self.lock:
            if self.job['running']:raise ValueError('请等待当前更新任务结束')
            config=read_json(self.path,{})
            if 'automatic' in data:config['automatic']=bool(data['automatic'])
            if data.get('clearToken'):config.pop('githubToken',None)
            elif data.get('token'):
                token=str(data['token']).strip()
                if len(token)>1000 or any(ord(c)<33 for c in token):raise ValueError('GitHub 凭据格式无效')
                config['githubToken']=seal(token)
            write_json(self.path,config);return self.status()
    def token(self):
        value=read_json(self.path,{}).get('githubToken')
        if not value:return ''
        return seal(value,True)
    def open(self,path,raw=False):
        # No arbitrary URLs and no cross-origin credential forwarding.
        url='https://api.github.com/repos/'+REPOSITORY+'/'+path
        headers={'Accept':'application/vnd.github.raw+json' if raw else 'application/vnd.github+json','User-Agent':'LaTeXStudio/'+VERSION}
        token=self.token()
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(url,headers=headers)
        try:return urllib.request.build_opener(NoRedirect).open(request,timeout=45)
        except urllib.error.HTTPError as e:
            raise ValueError({401:'GitHub 凭据已失效',403:'GitHub 权限不足或请求受限',404:'尚无发布版本，或凭据没有此私有仓库的读取权限'}.get(e.code,'GitHub 更新服务暂不可用')) from None
        except urllib.error.URLError:raise ValueError('无法连接 GitHub，请稍后重试') from None
    def json(self,path,raw=False):
        with self.open(path,raw) as response:data=response.read(200001)
        if len(data)>200000:raise ValueError('版本清单过大')
        return json.loads(data)
    def validate(self,value,commit):
        version=value.get('version');version_tuple(version)
        name=f'LaTeX-Studio-{version}-win64-Setup.exe'
        if value.get('file')!='distribution/'+name or not re.fullmatch(r'[0-9a-f]{64}',str(value.get('sha256',''))):raise ValueError('更新清单的文件或 SHA256 无效')
        if not isinstance(value.get('size'),int) or not 0<value['size']<100*1024*1024:raise ValueError('安装包大小无效')
        if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('发布提交无效')
        return {'version':version,'file':value['file'],'sha256':value['sha256'],'size':value['size'],'commit':commit,
                'notes':str(value.get('notes',''))[:4000],'available':version_tuple(version)>version_tuple(VERSION),
                'url':'https://github.com/'+REPOSITORY+'/blob/'+commit+'/'+value['file']}
    def check(self):
        with self.lock:
            if self.job['running']:raise ValueError('已有更新任务正在进行')
            self.job.update(running=True,stage='正在检查',error=None)
        try:
            commit=self.json('git/ref/heads/main')['object']['sha']
            release=self.validate(self.json('contents/updates/latest.json?ref='+commit,True),commit)
            with self.lock:self.release=release;self.installer=None;self.job.update(stage='发现新版本' if release['available'] else '已是最新版本')
        except Exception as e:
            with self.lock:self.job.update(stage='检查未完成',error=str(e) if isinstance(e,ValueError) else '版本服务响应无效')
            raise ValueError(self.job['error']) from None
        finally:
            with self.lock:self.job['running']=False
        return self.status()
    def download(self):
        with self.lock:
            if self.job['running']:raise ValueError('已有更新任务正在进行')
            if not self.release or not self.release['available']:raise ValueError('请先检查新版本')
            release=dict(self.release);self.job={'running':True,'stage':'正在下载','downloaded':0,'size':release['size']}
            threading.Thread(target=self.fetch,args=(release,),daemon=True).start();return self.status()
    def fetch(self,release):
        folder=self.store.cache/'updates'/'downloads';folder.mkdir(parents=True,exist_ok=True)
        target=folder/Path(release['file']).name;partial=target.with_suffix('.part')
        try:
            with self.open('contents/'+release['file']+'?ref='+release['commit'],True) as source,partial.open('wb') as out:
                count=0
                for block in iter(lambda:source.read(1024*1024),b''):
                    count+=len(block)
                    if count>release['size']:raise ValueError('下载大小超过版本清单')
                    out.write(block)
                    with self.lock:self.job['downloaded']=count
            if count!=release['size'] or file_sha(partial)!=release['sha256']:raise ValueError('安装包 SHA256 校验失败，已拒绝运行')
            if partial.read_bytes()[:2]!=b'MZ':raise ValueError('下载内容不是 Windows 安装程序')
            partial.replace(target)
            with self.lock:self.installer=target;self.job.update(stage='已下载并通过 SHA256 校验',error=None)
        except Exception as e:
            partial.unlink(missing_ok=True)
            with self.lock:self.installer=None;self.job.update(stage='下载未完成',error=str(e) if isinstance(e,ValueError) else '下载失败，请重新检查版本')
        finally:
            with self.lock:self.job['running']=False
    def install(self):
        with self.lock:
            if self.job['running'] or not self.installer or not self.release:raise ValueError('请先下载并验证安装包')
            allowed=(self.store.cache/'updates'/'downloads').resolve();target=self.installer.resolve()
            if target.parent!=allowed or target.is_symlink() or file_sha(target)!=self.release['sha256']:raise ValueError('安装文件已变化，已拒绝运行')
            # Explicit user action opens the normal installation wizard.
            subprocess.Popen([str(target),'/DIR='+str(self.store.home)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return {'started':True}

_instances={}
def updates_for(store):
    key=str(store.data)
    if key not in _instances:_instances[key]=Updates(store)
    return _instances[key]
