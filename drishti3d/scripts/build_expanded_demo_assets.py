"""Prepare truthful, local source-code/document views for the extended demo.

Only whitelisted repository excerpts are shown. No fabricated editor actions,
terminal output, test-pass results, subtitles, or performance numbers.
"""
from pathlib import Path
import hashlib
import html
import json
import re
from pygments import highlight
from pygments.lexers import PythonLexer, TextLexer
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/demo/final_video/expanded_2026_10_02'
ASSETS = OUT / 'assets'
ASSETS.mkdir(parents=True, exist_ok=True)
manifest = []
formatter = HtmlFormatter(nowrap=True, style='github-dark')
syntax = formatter.get_style_defs('.code')
base = '''*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden}
body{font-family:Arial,sans-serif;color:#e9edf4;background:#0d141d}header{height:72px;display:flex;align-items:center;padding:0 34px;gap:22px;background:#121d28;border-bottom:1px solid #314254;font-size:17px;color:#b7c5d3}
.brand{font-size:25px;letter-spacing:-1px;font-weight:700;color:#f7f3ec}.brand span{color:#e87961}.tag{margin-left:auto;font-size:14px;letter-spacing:2px;color:#9cb0c3}
.layout{display:flex;height:calc(100% - 72px)}aside{width:300px;flex-shrink:0;padding:35px 22px;background:#111b25;border-right:1px solid #2a3948;font-family:monospace;font-size:18px;line-height:2.3;color:#a5b6c8}
.dir{color:#edf0f5}.active{color:#f7b49d;background:#25313c;border-radius:5px;padding-left:10px}.indent{padding-left:18px}.section{font:12px Arial;letter-spacing:2px;color:#7890a6;margin-bottom:18px}
main{flex:1;min-width:0;padding:32px 40px 24px}.path{color:#a2b2c3;font-size:17px;margin-bottom:25px}.path b{color:#f0eee7;font-weight:400}
.code{font:20px/33px 'DejaVu Sans Mono',monospace;margin:0;white-space:pre;tab-size:4}.line{display:flex;min-height:33px;border-radius:3px}.line.focus{background:#223944;box-shadow:inset 3px 0 #66d2aa}.ln{width:62px;flex-shrink:0;text-align:right;padding-right:24px;color:#596c80;user-select:none}.content{white-space:pre}.foot{position:absolute;bottom:0;left:300px;right:0;height:36px;background:#14222e;border-top:1px solid #2a3948;color:#93a8bc;padding:10px 35px;font-size:13px}
'''
tree = '''<div class="section">REPOSITORY</div><div class="dir">⌄ drishti3d</div>
<div class="indent">⌄ reconstruction</div><div class="indent">&nbsp; ⌄ drishti_recon</div>
<div class="indent">&nbsp; &nbsp; questions.py</div><div class="indent">&nbsp; &nbsp; refinement.py</div>
<div class="indent">› backend</div><div class="indent">› frontend</div><div class="indent">⌄ tests</div>
<div class="indent">&nbsp; test_questions.py</div><div class="indent">› scripts</div><div class="indent">› docs</div>'''

def source_page(name, relative, start, end, focus=(), python=True):
    path = ROOT / relative
    source = path.read_text()
    lines = source.splitlines()[start-1:end]
    rendered = highlight('\n'.join(lines), PythonLexer() if python else TextLexer(), formatter).splitlines()
    code = ''.join(f'<div class="line {"focus" if start+i in focus else ""}"><span class="ln">{start+i}</span><span class="content">{line or " "}</span></div>' for i, line in enumerate(rendered))
    doc = f'''<!doctype html><meta charset="utf-8"><title>{html.escape(relative)}</title><style>{base}{syntax}</style>
<header><div class="brand">drishti<span>3D</span></div><span>/</span><span>Repository</span><span class="tag">SOURCE VIEW</span></header>
<div class="layout"><aside>{tree}</aside><main><div class="path">drishti3d / <b>{html.escape(relative)}</b></div><div class="code">{code}</div></main></div>
<div class="foot">{html.escape(relative)} &nbsp; · &nbsp; UTF-8 &nbsp; · &nbsp; Read-only</div>'''
    (ASSETS / f'{name}.html').write_text(doc)
    manifest.append(dict(asset=name, source=relative, lines=[start,end], sha256=hashlib.sha256(source.encode()).hexdigest()))

readme = (ROOT / 'README.md').read_text().splitlines()
architecture = next(i+1 for i,l in enumerate(readme) if l.strip()=='drishti3d/')
source_page('code-architecture', 'README.md', architecture, architecture+9, python=False)
q = (ROOT/'reconstruction/drishti_recon/questions.py').read_text().splitlines()
start = next(i+1 for i,l in enumerate(q) if l.strip()=='if tol is None:')
source_page('code-questions', 'reconstruction/drishti_recon/questions.py', start-2, start+16, range(start+5,start+7))
r = (ROOT/'reconstruction/drishti_recon/refinement.py').read_text().splitlines()
start = next(i+1 for i,l in enumerate(r) if 'for c in batch:' in l)
source_page('code-refinement', 'reconstruction/drishti_recon/refinement.py', start, start+20, range(start+4,start+6))
start2 = next(i+1 for i,l in enumerate(r) if 'refit = self._local_bundle' in l)
source_page('code-refinement-result', 'reconstruction/drishti_recon/refinement.py', start2, start2+18, (start2,start2+9))
t = (ROOT/'tests/test_questions.py').read_text().splitlines()
start = next(i+1 for i,l in enumerate(t) if l.startswith('def test_uncalibrated_system'))
source_page('code-tests', 'tests/test_questions.py', start, start+14, range(start+9,start+14))

def inline(s):
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
    return re.sub(r'\*([^*]+)\*',r'<em>\1</em>',s)

source=(ROOT/'docs/VIDEO_ACCURACY_MARS_LVIG.md').read_text()
excerpt=source.split('## 2. Why this reference')[0]
blocks=excerpt.split('\n\n')
rendered=[]
for block in blocks:
    if block.startswith('# '): rendered.append('<h1>'+inline(block[2:])+'</h1>')
    elif block.startswith('## '): rendered.append('<h2>'+inline(block[3:])+'</h2>')
    elif block.startswith('|'):
        rows=block.splitlines()
        table='<table><thead><tr>'+''.join('<th>'+inline(c.strip())+'</th>' for c in rows[0].strip('|').split('|'))+'</tr></thead><tbody>'
        for row in rows[2:]:
            table+='<tr>'+''.join('<td>'+inline(c.strip())+'</td>' for c in row.strip('|').split('|'))+'</tr>'
        rendered.append(table+'</tbody></table>')
    elif block.strip(): rendered.append('<p>'+inline(' '.join(block.splitlines()))+'</p>')
doccss='''html,body{margin:0;background:#f1eee7;color:#242925;font-family:Arial,sans-serif}header{position:sticky;top:0;background:#e9e4da;border-bottom:1px solid #cfc5b5;padding:22px 70px;color:#6d6b62;font:17px monospace}article{max-width:1700px;margin:35px auto;padding:0 40px 70px}h1{font-size:38px;letter-spacing:-1px;line-height:1.15;margin:18px 0 25px}h2{font-size:25px;margin:28px 0 14px}p{font-size:22px;line-height:1.45;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:23px;margin:24px 0}th,td{text-align:left;padding:15px 23px;border-bottom:1px solid #d1c7b7}th{background:#dfe8e0;font-size:21px}td:first-child{width:45%}td:nth-child(2){background:#e8eee6}strong{font-weight:700}code{font-size:.9em;color:#964b3d}'''
(ASSETS/'validation.html').write_text('<!doctype html><meta charset="utf-8"><style>'+doccss+'</style><header>drishti3d / docs / VIDEO_ACCURACY_MARS_LVIG.md</header><article>'+''.join(rendered)+'</article>')
manifest.append(dict(asset='validation',source='docs/VIDEO_ACCURACY_MARS_LVIG.md',sha256=hashlib.sha256(source.encode()).hexdigest(),excerpt='Document beginning through section 1, verbatim'))

# Logo paths reused from frontend/src/App.tsx. Brand only: not subtitle text.
mark='<svg viewBox="0 0 32 36" fill="none"><path d="M16 2 30 10v16L16 34 2 26V10L16 2Z" stroke="currentColor" stroke-width="1.5"/><path d="m2 10 14 8 14-8M16 18v16M9 14v8l7 4 7-4v-8" stroke="currentColor" stroke-width="1.5"/></svg>'
hero=f'''<!doctype html><meta charset="utf-8"><style>*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;background:transparent;overflow:hidden}}.veil{{position:absolute;inset:0;background:linear-gradient(90deg,#0b151f 0%,#0b151f 27%,#0b151f99 40%,transparent 56%)}}.brand{{position:absolute;left:82px;top:357px;color:#f2ede5;font-family:Arial,sans-serif}}svg{{width:70px;height:80px;color:#e07c62;margin-bottom:32px}}h1{{font-size:94px;font-weight:500;letter-spacing:-5px;margin:0}}h1 span{{color:#e07c62}}.line{{height:2px;width:125px;background:#e07c62;margin-top:40px}}.corners{{position:absolute;inset:54px;border:1px solid #7791a31a}}.dot{{position:absolute;left:84px;bottom:100px;width:8px;height:8px;background:#65bca0;border-radius:50%}}</style><div class="veil"></div><div class="corners"></div><div class="brand">{mark}<h1>drishti<span>3D</span></h1><div class="line"></div></div><div class="dot"></div>'''
(ASSETS/'brand-overlay.html').write_text(hero)
(OUT/'source-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Built',len(manifest),'source views and the transparent brand layer',flush=True)
