"""Fail closed for private local state and likely credentials in publication files."""
from pathlib import Path
import re,sys
BLOCK={'data','storage','projects','.ssh','.aws','.codex','.agents','__pycache__'}
NAMES={'installation.json','runtime.json','session-token','ai-settings.json','update-settings.json','settings.json','locations.json','ai-usage.json'}
PATTERNS=[re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----'),
          re.compile(rb'(?:ghp_|github_pat_)[A-Za-z0-9_]{25,}'),re.compile(rb'\bsk-[A-Za-z0-9]{24,}'),
          re.compile(rb'AQAAANCM'+rb'nd8BFdERjHoAwE/Cl'),re.compile(rb'[A-Za-z0-9._%+-]+@(?:qq[.]com|163[.]com)')]
def audit(root):
    root=Path(root);problems=[];count=0
    for p in root.rglob('*'):
        parts=p.relative_to(root).parts
        if '.git' in parts:continue
        if p.is_symlink():problems.append(str(p.relative_to(root))+': symlink');continue
        if not p.is_file():continue
        count+=1
        if set(parts)&BLOCK or p.name in NAMES or p.suffix.lower() in {'.pem','.key','.pfx','.log'}:problems.append(str(p.relative_to(root))+': private state path')
        if p.suffix.lower() in {'.py','.js','.html','.css','.json','.md','.txt','.ps1','.vbs','.yml','.yaml','.toml','.iss'}:
            raw=p.read_bytes()
            for pattern in PATTERNS:
                if pattern.search(raw):problems.append(str(p.relative_to(root))+': credential or personal marker');break
    if problems:raise ValueError('Release audit failed:\n'+'\n'.join(problems))
    return count
if __name__=='__main__':print('Audit passed:',audit(Path(sys.argv[1] if len(sys.argv)>1 else '.')),'files')
