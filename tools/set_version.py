"""Prepare a strictly newer stable version before building a release."""
import argparse,json,re
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('version');parser.add_argument('--build',required=True)
    args=parser.parse_args();path=Path(__file__).resolve().parents[1]/'version.json';old=json.loads(path.read_text('utf8'))
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version) or tuple(map(int,args.version.split('.')))<=tuple(map(int,old['version'].split('.'))):raise ValueError('Use a newer stable semantic version')
    if not re.fullmatch(r'studio-\d+',args.build):raise ValueError('Use a studio-N build identifier')
    old.update(version=args.version,build=args.build)
    path.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Version prepared; update CHANGELOG.md, build, audit, test, commit and tag v'+args.version)
if __name__=='__main__':main()
