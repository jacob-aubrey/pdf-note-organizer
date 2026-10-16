"""Remove fixture path pixels, validate the guides, and render all pages with Poppler."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'.test-tmp'/'guides'
OUT = ROOT/'output'/'pdf'


def redact_fixture_paths():
    path=OUT/'Notable-User-Manual.pdf'
    redactions=json.loads((WORK/'redactions.json').read_text(encoding='utf-8'))
    annotations=json.loads((WORK/'annotations.json').read_text(encoding='utf-8'))
    with pymupdf.open(path) as doc:
        for index in sorted({r['page'] for r in redactions}):
            page=doc[index]
            rows=[r for r in redactions if r['page']==index]
            for row in rows:
                page.add_redact_annot(pymupdf.Rect(row['rect']),fill=(52/255,54/255,56/255),cross_out=False)
            page.apply_redactions(images=2,graphics=0,text=1)
            for row in rows:
                box=pymupdf.Rect(row['rect'])
                text=row['text']
                size=min(row['size'],box.height*.65)
                while text and pymupdf.get_text_length(text,fontname='helv',fontsize=size)>box.width-6:
                    text=text[:-1]
                page.insert_text((box.x0+3,box.y0+box.height*.75),text,fontsize=size,fontname='helv',color=(.86,.89,.93))
            # Put callouts above the anonymized fields so redaction fills never
            # obscure the corner badge or the control's highlighted outline.
            for item in (a for a in annotations if a['page']==index):
                color=tuple(int(item['color'][i:i+2],16)/255 for i in (1,3,5))
                page.draw_rect(pymupdf.Rect(item['rect']),color=(.06,.12,.16),width=3.5)
                page.draw_rect(pymupdf.Rect(item['rect']),color=color,width=1.5)
                x,y=item['badge']
                page.draw_circle((x,y),8.5,color=color,fill=(.06,.16,.24),width=1)
                page.insert_text((x-2.5,y+3),str(item['number']),fontname='hebo',fontsize=9,color=(1,1,1))
        cleaned=WORK/'Notable-User-Manual-redacted.pdf'
        doc.save(cleaned,garbage=4,deflate=True)
    cleaned.replace(path)


def main():
    redact_fixture_paths()
    poppler=shutil.which('pdftoppm')
    if not poppler:
        raise SystemExit('Poppler pdftoppm is required for guide layout verification.')
    result={}
    for name in ('Notable-User-Manual','Notable-README'):
        path=OUT/(name+'.pdf')
        folder=WORK/name
        folder.mkdir(parents=True,exist_ok=True)
        with pymupdf.open(path) as doc:
            for i,page in enumerate(doc):
                text=page.get_text()
                if not text.strip():
                    raise AssertionError(f'{name} page {i+1} is empty')
                for block in page.get_text('dict')['blocks']:
                    if block['type']:
                        continue
                    for line in block['lines']:
                        if not page.rect.contains(pymupdf.Rect(line['bbox'])):
                            raise AssertionError(f'Clipped PDF text in {name} page {i+1}: {line}')
                if 'C:\\Users\\jdaub' in text or '\ufffd' in text:
                    raise AssertionError(f'Private path or replacement character in {name} page {i+1}')
            result[name]={'pages':len(doc),'bytes':path.stat().st_size,'bookmarks':len(doc.get_toc())}
        subprocess.run([poppler,'-r','80','-png',str(path),str(folder/'page')],check=True,capture_output=True)
        pages=sorted(folder.glob('page-*.png'))
        for start in range(0,len(pages),12):
            contact=Image.new('RGB',(1050,4*290),'#DDE4E9')
            draw=ImageDraw.Draw(contact)
            for offset,file in enumerate(pages[start:start+12]):
                image=Image.open(file).convert('RGB')
                image.thumbnail((338,265))
                x=(offset%3)*350+(350-image.width)//2
                y=(offset//3)*290+20
                contact.paste(image,(x,y))
                draw.text(((offset%3)*350+10,y-16),f'Page {start+offset+1}',fill='#172E3F')
            contact.save(folder/f'contact-{start//12+1:02d}.png')
        print(name,result[name],flush=True)
    (WORK/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
