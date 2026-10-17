"""Build the public PDF guides from current UI captures and task source.

Requires ReportLab and Pillow. First run capture_manual.py on the private UI
desktop, then this script. Run verify_guides.py afterwards to redact fixture
paths from embedded pixels, render every page, and check PDF structure.
"""
from pathlib import Path
import html
import json
import math
import re
import sys
from urllib.parse import quote

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               Preformatted, KeepTogether)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from documentation.manual_tasks import TASKS
from note_organizer import __version__

CAPTURES = ROOT / '.test-tmp' / 'manual-captures'
OUT = ROOT / 'output' / 'pdf'
WORK = ROOT / '.test-tmp' / 'guides'
W, H = landscape(A4)
M = 32
INK, MUTED, BLUE = '#172E3F', '#536471', '#126AA3'
CALLOUT = ['#28C9FF', '#FFBE40', '#AEF095']
REDACTIONS = []
ANNOTATIONS = []


def register_fonts():
    for name, filename in [('Guide', 'arial.ttf'), ('GuideBold', 'arialbd.ttf'),
                           ('GuideItalic', 'ariali.ttf'), ('GuideMono', 'consola.ttf')]:
        pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + filename))
    pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold', italic='GuideItalic', boldItalic='GuideBold')


def paragraph(c, text, x, top, width, size=11, leading=None, color=INK, bold=False):
    style = ParagraphStyle('guide', fontName='GuideBold' if bold else 'Guide', fontSize=size,
        leading=leading or size*1.3, textColor=colors.HexColor(color))
    p = Paragraph(text, style)
    _, height = p.wrap(width, H)
    p.drawOn(c, x, top-height)
    return top-height


def chrome(c, title, page, section='USER MANUAL'):
    c.setFillColor(colors.HexColor(BLUE))
    c.rect(0, H-7, W, 7, fill=1, stroke=0)
    c.setFont('GuideBold', 9)
    c.drawString(M, H-27, f'NOTABLE {__version__}  /  {section}')
    paragraph(c, html.escape(title), M, H-43, W-2*M, 22, 25, bold=True)
    c.setFont('Guide', 8)
    c.setFillColor(colors.HexColor(MUTED))
    c.drawString(M, 15, 'October 17, 2026  •  Example library; no real account data')
    c.drawRightString(W-M, 15, str(page))


def screenshot(c, info, callouts, top, bottom, page, crop=None):
    image = Image.open(CAPTURES / info['file']).convert('RGB')
    areas={'folders','papers','results','viewer','copies','findings','incoming','mappings','attention'}
    def focus(key):
        rect=list(info['targets'][key])
        if key in areas:
            rect[3]=min(rect[3],210)
        return rect
    if crop is None and callouts and (image.width >= 1100 or image.height >= 950):
        boxes=[focus(key) for key,_ in callouts]
        left=max(0,min(b[0] for b in boxes)-80)
        right=min(image.width,max(b[0]+b[2] for b in boxes)+80)
        upper=max(0,min(b[1] for b in boxes)-65)
        lower=min(image.height,max(b[1]+b[3] for b in boxes)+65)
        if right-left<760:
            center=(right+left)/2
            left=max(0,min(image.width-760,center-380))
            right=min(image.width,left+760)
        if lower-upper<290:
            upper=max(0,min(image.height-290,(upper+lower)/2-145))
            lower=min(image.height,upper+290)
        crop=[int(left),int(upper),int(right),int(lower)]
    crop = crop or [0, 0, image.width, image.height]
    image = image.crop(crop)
    iw, ih = image.size
    # Small menu/dialog captures stay at a useful size rather than being blown up.
    scale = min((W-2*M)/iw, (top-bottom)/ih, 1.05)
    dw, dh = iw*scale, ih*scale
    x, y = (W-dw)/2, top-dh
    c.setFillColor(colors.HexColor('#ECF1F4'))
    c.roundRect(x-4, y-4, dw+8, dh+8, 3, stroke=0, fill=1)
    c.drawImage(ImageReader(image), x, y, dw, dh)
    def transform(rect):
        a,b,width,height = rect
        return x+(a-crop[0])*scale, top-(b-crop[1]+height)*scale, width*scale, height*scale
    # The verifier removes the underlying pixels as well as covering them.
    for mask in info.get('masks', []):
        a,b,width,height = transform(mask['rect'])
        if a+width < x or b+height < y or a > x+dw or b > top:
            continue
        a2,b2 = max(x,a), max(y,b)
        width,height = min(x+dw,a+width)-a2, min(top,b+height)-b2
        if width <= 0 or height <= 0:
            continue
        text = mask['text']
        if len(text) > 95:
            text = 'Example library (sample files)'
        REDACTIONS.append({'page':page-1,'rect':[a2,H-b2-height,a2+width,H-b2], 'text':text,
                           'size':max(5.5,min(8,14*scale))})
    for n,(key,label) in enumerate(callouts, 1):
        if key not in info['targets']:
            raise ValueError(f'Missing callout {key!r} in {info["file"]}')
        a,b,width,height = transform(focus(key))
        if a < x-2 or b < y-2 or a+width > x+dw+2 or b+height > top+2:
            raise ValueError(f'Callout {key!r} is outside screenshot crop')
        color = colors.HexColor(CALLOUT[(n-1)%len(CALLOUT)])
        c.setStrokeColor(colors.HexColor('#101E29'))
        c.setLineWidth(3.5)
        c.rect(a,b,width,height,fill=0,stroke=1)
        c.setStrokeColor(color)
        c.setLineWidth(1.5)
        c.rect(a,b,width,height,fill=0,stroke=1)
        # Number sits on the target's corner; its text stays readable.
        bx, by = max(x+8,a+4), min(top-7,b+height-1)
        ANNOTATIONS.append({'page':page-1,'rect':[a,H-b-height,a+width,H-b],
            'badge':[bx,H-by],'number':n,'color':CALLOUT[(n-1)%len(CALLOUT)]})
        c.setFillColor(colors.HexColor('#102A3E'))
        c.setStrokeColor(color)
        c.circle(bx,by,8.5,fill=1,stroke=1)
        c.setFillColor(colors.white)
        c.setFont('GuideBold',9)
        c.drawCentredString(bx,by-3,str(n))
    return y


def build_manual():
    manifest = json.loads((CAPTURES/'manifest.json').read_text(encoding='utf-8'))
    for info in manifest.values():
        im=Image.open(CAPTURES/info['file'])
        if im.width>=1100:
            info['targets']['window-close']=[im.width-46,0,46,38]
    # Resolve all screenshots/targets before replacing a previously usable guide.
    for _, _, steps in TASKS:
        for step in steps:
            info = manifest[step['screen']]
            for key,_ in step['callouts']:
                if key not in info['targets']:
                    raise ValueError(f'Missing screenshot target: {step["screen"]}/{key}')
    c = canvas.Canvas(str(OUT/'Notable-User-Manual.pdf'), pagesize=(W,H), pageCompression=1)
    c.setTitle(f'Notable {__version__} — Task-by-task user manual')
    c.setAuthor('Notable')
    c.setSubject('Procedural guide with current annotated screenshots and expected results')
    contents_pages = math.ceil(len(TASKS)/19)
    page = 1
    chrome(c, 'From first launch to a backed-up research library', page, 'ILLUSTRATED TASK GUIDE')
    paragraph(c, 'Click the highlighted control. Check what appears. Continue to the next step.', M, H-86, W-2*M, 15, 20, bold=True)
    paragraph(c, 'Each task starts with its prerequisites, then uses one numbered action per screenshot. '
        'Colored numbered boxes identify controls to use or results worth checking. The task index and PDF bookmarks jump directly to procedures.', M, H-122, W-2*M, 12, 16)
    info = manifest['library-selected']
    screenshot(c, info, [('folders','Watched folders'),('papers','Papers in the selected folder')], H-180, 125, page)
    paragraph(c, '<b>Before you begin:</b> This guide uses generated example PDFs and an offline tablet catalog. '
        'Paths are anonymized. Your document names and results will differ. Windows file choosers and external apps vary by PC; their choices are described beside the in-app screens.', M, 100, W-2*M, 10, 13)
    c.showPage()
    page += 1
    start_page = 2 + contents_pages
    page_numbers = []
    cursor = start_page
    for title, pre, steps in TASKS:
        page_numbers.append(cursor)
        cursor += len(steps)
    for start in range(0,len(TASKS),19):
        chrome(c, 'Choose a task', page, 'CLICKABLE TASK INDEX')
        yy = H-94
        for n in range(start,min(start+19,len(TASKS))):
            title = TASKS[n][0]
            c.setFont('Guide',11)
            c.setFillColor(colors.HexColor(INK))
            c.drawString(M+4,yy,f'{n+1:02d}  {title}')
            c.drawRightString(W-M-4,yy,str(page_numbers[n]))
            c.linkRect('', 'task'+str(n), (M,yy-5,W-M,yy+13), relative=0, thickness=0)
            c.setStrokeColor(colors.HexColor('#DDE5EA'))
            c.line(M,yy-9,W-M,yy-9)
            yy -= 23
        c.showPage()
        page += 1
    index = []
    for n,(title,prerequisite,steps) in enumerate(TASKS):
        for number, step in enumerate(steps,1):
            if number == 1:
                c.bookmarkPage('task'+str(n))
                c.addOutlineEntry(title,'task'+str(n),level=0,closed=False)
            chrome(c,title,page,f'TASK {n+1:02d}  •  STEP {number} OF {len(steps)}')
            action_bottom = paragraph(c, '<b>'+str(number)+'.</b> '+html.escape(step['action']),M,H-83,W-2*M,12,15)
            if number == 1:
                action_bottom = paragraph(c, '<b>Start here:</b> '+html.escape(prerequisite),M,action_bottom-7,W-2*M,9,12,color=MUTED)
            top = action_bottom-14
            screenshot(c, manifest[step['screen']], step['callouts'], top, 118, page, step['crop'])
            labels = '    '.join(f'<b>{i+1}.</b> {html.escape(label)}' for i,(_,label) in enumerate(step['callouts']))
            paragraph(c, labels, M, 103, W-2*M, 9, 12, color=BLUE)
            bottom = paragraph(c, '<b>What to expect:</b> '+html.escape(step['result']), M, 77, W-2*M,10,13)
            if bottom < 30:
                raise ValueError(f'Expected-result text exceeds footer space: task {n+1} step {number}')
            index.append({'page':page,'task':title,'step':number,'screen':step['screen']})
            c.showPage()
            page += 1
    chrome(c,'Keyboard and mouse reference',page,'QUICK REFERENCE')
    rows = [('Where','Gesture','Action'),
        ('Main app','Ctrl+F','Focus the main Reader search'),
        ('Inside the PDF','Ctrl+F','Open Find in PDF for this document'),
        ('Reader results','Previous / Next match','Visit main-search occurrences across results and papers'),
        ('PDF Find','Enter / Shift+Enter','Next / previous PDF-only occurrence'),
        ('PDF or image','Ctrl+wheel / Ctrl+drag','Zoom / pan'),
        ('Inside the PDF','Ctrl+0 / Ctrl+double-click','Default mode zoom / default zoom and current-page start'),
        ('Images','Ctrl+double-click','Opening zoom and top-left position'),
        ('Main app','F5 / Ctrl+comma','Sync local PDFs / open Settings'),
        ('Main app','Ctrl+Shift+S / Ctrl+Shift+T','Saved searches / tags and collections'),
        ('File/folder lists','Double-click / Enter','Open the clicked/focused item; Library papers open in Reader'),
        ('Review copies','Ctrl-click / Shift-click','Toggle individual copies / select a range'),
        ('Search field or dialog','Escape','Clear the main query / follow Cancel or Close')]
    style = ParagraphStyle('cell',fontName='Guide',fontSize=10,leading=13)
    table = Table([[Paragraph(html.escape(x),style) for x in row] for row in rows],colWidths=[145,205,W-2*M-350])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DBEAF3')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F5F8')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    tw,th = table.wrap(W-2*M,H-110)
    table.drawOn(c,M,H-86-th)
    c.save()
    (WORK/'manual-pages.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
    (WORK/'redactions.json').write_text(json.dumps(REDACTIONS,indent=2),encoding='utf-8')
    (WORK/'annotations.json').write_text(json.dumps(ANNOTATIONS,indent=2),encoding='utf-8')
    print('Manual:',len(TASKS),'procedures;',page,'pages')


def inline(text):
    text = html.escape(text)
    def link(match):
        href=html.unescape(match[2])
        if href.startswith('#'):
            href='https://github.com/jacob-aubrey/pdf-note-organizer/blob/main/README.md'+href
        elif not re.match(r'^[a-zA-Z]+:',href):
            href='https://github.com/jacob-aubrey/pdf-note-organizer/blob/main/'+quote(href,safe='/#')
        return '<link href="'+html.escape(href,quote=True)+'" color="#126AA3">'+match[1]+'</link>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,text)
    text = re.sub(r'`([^`]+)`',r'<font name="GuideMono">\1</font>',text)
    text = re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return text


def build_readme():
    styles = getSampleStyleSheet()
    body = ParagraphStyle('body',fontName='Guide',fontSize=10,leading=14,spaceAfter=7)
    headings = {level:ParagraphStyle('h'+str(level),parent=body,fontName='GuideBold',fontSize=22-3*level,
               leading=26-3*level,spaceBefore=15,spaceAfter=8,keepWithNext=True) for level in range(1,5)}
    bullet = ParagraphStyle('bullet',parent=body,leftIndent=15,firstLineIndent=-10)
    code_style = ParagraphStyle('code',fontName='GuideMono',fontSize=7.5,leading=10,spaceAfter=10,
                                backColor=colors.HexColor('#EDF2F5'),borderPadding=7)
    elements, pending, code, in_code, table_rows = [], [], [], False, []
    def flush():
        if pending:
            elements.append(Paragraph(inline(' '.join(pending)),body))
            pending.clear()
    def flush_table():
        if not table_rows:
            return
        rows = [[Paragraph(inline(cell),body) for cell in row] for row in table_rows]
        cols = len(rows[0])
        tab = Table(rows,colWidths=[(A4[0]-72)/cols]*cols,repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DBEAF3')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F2F5F7')]),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.3,colors.HexColor('#CBD9E2')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
        elements.extend([tab,Spacer(1,10)])
        table_rows.clear()
    for line in (ROOT/'README.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            flush(); flush_table()
            if in_code:
                # Wrap long shell lines at whitespace without losing text.
                import textwrap
                wrapped='\n'.join('\n'.join(textwrap.wrap(x,105,replace_whitespace=False,drop_whitespace=False)) or '' for x in code)
                elements.append(Preformatted(wrapped,code_style))
                code=[]
            in_code=not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if line.startswith('|'):
            flush()
            cells=[s.strip() for s in line.strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?',s) for s in cells):
                table_rows.append(cells)
            continue
        flush_table()
        if not line.strip():
            flush()
            continue
        match=re.match(r'^(#{1,4}) (.*)',line)
        if match:
            flush()
            elements.append(Paragraph(inline(match[2]),headings[len(match[1])]))
        elif re.match(r'^(?:- |\d+\. )',line):
            flush()
            text=re.sub(r'^- ','• ',line)
            elements.append(Paragraph(inline(text),bullet))
        else:
            pending.append(line.strip())
    flush(); flush_table()
    def footer(c,doc):
        c.setFont('Guide',8)
        c.setFillColor(colors.HexColor(MUTED))
        c.drawString(36,20,f'Notable {__version__} README  •  October 17, 2026')
        c.drawRightString(A4[0]-36,20,str(doc.page))
    doc=SimpleDocTemplate(str(OUT/'Notable-README.pdf'),pagesize=A4,rightMargin=36,leftMargin=36,
        topMargin=36,bottomMargin=39,title=f'Notable {__version__} README',author='Notable')
    doc.build(elements,onFirstPage=footer,onLaterPages=footer)
    print('README PDF generated from README.md')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=True)
    register_fonts()
    build_manual()
    build_readme()


if __name__ == '__main__':
    main()
