"""Configure paths after installation without copying or replacing user data."""
import argparse,json
from pathlib import Path
from studio_storage import read_json,write_json
from studio_version import VERSION

def configure(home):
    home=Path(home).resolve();app=home/'app'
    if not (app/'server.py').is_file():raise ValueError('应用文件不完整')
    value=read_json(app/'installation.json',{})
    value.update(home=str(home),version=VERSION,pythonExecutable=str(home/'python/pythonw.exe'))
    value.setdefault('defaultProject',str(home/'projects/我的文档'))
    write_json(app/'installation.json',value)
    for name in ['data','projects','cache']: (home/name).mkdir(exist_ok=True)
    legacy=home/'data/ai-usage.json'
    if legacy.is_file() and not legacy.is_symlink():legacy.unlink()
    print('Installation configured')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--home',required=True)
    configure(parser.parse_args().home)
