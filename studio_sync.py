"""Bidirectional SyncTeX point lookup against the exact last compiled sources."""
from pathlib import Path
import gzip, math, re
from studio_storage import project_id, read_json
from studio_page_edits import project_files,sha

def locate(root,data,pdf,query):
    root=Path(root).resolve();pdf=Path(pdf)
    base=Path(data)/'previews'/(project_id(root)+'.synctex.gz')
    meta=read_json(base.with_suffix('.json'),{})
    if not pdf.is_file() or not base.is_file() or meta.get('pdfVersion')!=str(pdf.stat().st_mtime_ns):
        raise ValueError('请先编译当前文档以建立定位信息')
    if meta.get('sources')!={p.relative_to(root).as_posix():sha(p) for p in project_files(root)}:
        raise ValueError('源码已变化，请重新编译后定位')
    from pypdf import PdfReader
    sizes=[(float(p.mediabox.width),float(p.mediabox.height)) for p in PdfReader(pdf).pages]
    inputs={};points=[];page=0;unit=1.;mag=1000.;ox=oy=0.
    for row in gzip.decompress(base.read_bytes()).decode('utf-8',errors='replace').splitlines():
        m=re.match(r'Input:(\d+):(.+)',row)
        if m:
            path=Path(m[2]);path=(root/path).resolve() if not path.is_absolute() else path.resolve()
            if path.is_relative_to(root) and not path.is_symlink() and path.suffix.lower()=='.tex' and path.is_file():inputs[int(m[1])]=path.relative_to(root).as_posix()
        elif row.startswith('Unit:'):unit=float(row.split(':')[1])
        elif row.startswith('Magnification:'):mag=float(row.split(':')[1])
        elif row.startswith('X Offset:'):ox=float(row.split(':')[1])
        elif row.startswith('Y Offset:'):oy=float(row.split(':')[1])
        elif re.fullmatch(r'\{\d+',row):page=int(row[1:])
        elif row.startswith('}'):page=0
        elif 0<page<=len(sizes):
            m=re.match(r'[gxkh](\d+),(\d+)(?:,\d+)?:(-?\d+),(-?\d+)',row)
            if m and int(m[1]) in inputs:
                factor=unit/65536*72/72.27*mag/1000
                x=(int(m[3])*factor+ox/65536*72/72.27)/sizes[page-1][0]
                y=(int(m[4])*factor+oy/65536*72/72.27)/sizes[page-1][1]
                if 0<=x<=1 and 0<=y<=1:points.append({'path':inputs[int(m[1])],'line':int(m[2]),'page':page,'x':x,'y':y})
    if query.get('direction')=='forward':
        path=str(query.get('path',''));line=int(query.get('line',1))
        choices=[p for p in points if p['path']==path]
        if not choices:raise ValueError('此文件没有可用的 PDF 定位信息')
        point=min(choices,key=lambda p:(abs(p['line']-line),p['page'],p['y']))
    else:
        page=int(query.get('page',0));x=float(query.get('x',0));y=float(query.get('y',0))
        if not math.isfinite(x+y) or not 0<=x<=1 or not 0<=y<=1:raise ValueError('页面坐标无效')
        choices=[p for p in points if p['page']==page]
        if not choices:raise ValueError('这一页没有可定位的源码')
        point=min(choices,key=lambda p:(p['y']-y)**2*4+(p['x']-x)**2)
    return {**point,'approximate':True,'projectId':project_id(root)}
