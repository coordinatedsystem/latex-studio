"""Regenerate the blue LT Windows brand icon (development only, Pillow required)."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def main():
    assets=Path(__file__).resolve().parents[1]/'assets'
    image=Image.new('RGBA',(1024,1024),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((35,45,989,999),radius=235,fill=(37,99,235,28))
    draw.rounded_rectangle((35,25,989,979),radius=235,fill='#2563eb')
    draw.rounded_rectangle((64,53,960,950),radius=207,outline='#76a4ff',width=4)
    font=Path('C:/Windows/Fonts/georgiai.ttf')
    if not font.is_file():font=Path('C:/Windows/Fonts/timesi.ttf')
    draw.text((150,-30),'L',font=ImageFont.truetype(str(font),760),fill='white',stroke_width=1)
    draw.text((540,400),'T',font=ImageFont.truetype(str(font),370),fill='#e9f1ff')
    image.resize((256,256),Image.Resampling.LANCZOS).save(assets/'studio.png')
    image.save(assets/'studio-blue.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print('Blue brand icon generated')

if __name__=='__main__':main()
