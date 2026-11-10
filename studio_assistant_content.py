"""Bounded text windows and image evidence shared by Studio capabilities."""
import base64,io

TEXT={'.tex','.bib','.sty','.cls','.txt','.md','.csv','.json','.bbl','.cfg','.def'}

def bounded_int(value,low,high):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('参数范围无效')
    return value

def window(text,start=1,lines=100):
    start=bounded_int(start,1,1000000);lines=bounded_int(lines,1,160)
    rows=text.splitlines();body='\n'.join(f'{i+1}: {row[:1600]}' for i,row in enumerate(rows[start-1:start-1+lines],start-1))
    return {'text':body[:12000],'totalLines':len(rows),'start':start,'nextLine':start+lines if start+lines<=len(rows) else None}

def image_payload(path):
    from PIL import Image
    with Image.open(path) as image:
        image.thumbnail((1600,1600))
        if image.mode in {'RGBA','LA'}:
            background=Image.new('RGB',image.size,'white');background.paste(image,mask=image.getchannel('A'));image=background
        else:image=image.convert('RGB')
        buffer=io.BytesIO();image.save(buffer,'JPEG',quality=85,optimize=True)
    return 'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()
