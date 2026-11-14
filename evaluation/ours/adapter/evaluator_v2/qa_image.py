"""Read-only QA contact sheet. Never used as the policy's input image."""
from PIL import Image,ImageDraw
from pathlib import Path
import io,json,hashlib

def qa_image(main, wrist, atlas_directory):
    canvas=Image.new('RGB',(1024,768),'white');draw=ImageDraw.Draw(canvas)
    for i,(name,data) in enumerate([('CURRENT MAIN',main),('CURRENT WRIST',wrist)]):
        draw.text((i*512+12,8),name,fill='black')
        if data:
            im=Image.open(io.BytesIO(data)).convert('RGB');im.thumbnail((500,500));im=im.resize((500,500))
            canvas.paste(im,(i*512+6,28))
        else:draw.text((i*512+12,100),'VIEW UNAVAILABLE - NOT AN EMPTY SCENE',fill='black')
    draw.text((12,536),'REFERENCE ONLY: OBJECT IDENTITY - NOT CURRENT POSITIONS OR CONTENTS',fill='black')
    atlas_directory=Path(atlas_directory)
    manifest=json.loads((atlas_directory/'atlas.json').read_text())
    for i,o in enumerate(manifest['objects']):
        data=(atlas_directory/o['reference']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=o['reference_sha256']:raise ValueError('atlas_hash_mismatch')
        im=Image.open(io.BytesIO(data)).convert('RGB');im.thumbnail((140,185));x=i*146+3
        canvas.paste(im,(x,574));draw.text((x,556),o['id'],fill='black')
    buf=io.BytesIO();canvas.save(buf,format='JPEG',quality=92);return buf.getvalue()
