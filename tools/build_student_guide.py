"""Build the offline student handbook from the same chapters shown on GitHub."""
import argparse
from html import escape
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GUIDE = '수강생-시작가이드.html'
CHAPTERS = [('install','설치','STUDENT-INSTALL.md'),('setup','세팅','STUDENT-SETUP.md'),
            ('use','사용 실습','STUDENT-USE.md'),('custom','AI와 개인화','STUDENT-AI.md')]
INLINE = re.compile(r'(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?://[^\s)]+\))')


def inline(text):
    parts = []
    for i, fragment in enumerate(INLINE.split(text)):
        if i % 2 == 0:
            parts.append(escape(fragment))
        elif fragment.startswith('`'):
            parts.append('<code>'+escape(fragment[1:-1])+'</code>')
        elif fragment.startswith('**'):
            parts.append('<strong>'+inline(fragment[2:-2])+'</strong>')
        else:
            label, url = fragment[1:-1].split('](',1)
            parts.append(f'<a href="{escape(url,quote=True)}">{escape(label)}</a>')
    return ''.join(parts)


def chapter(key, source):
    lines = iter(source.splitlines())
    output = [f'<section class="chapter" id="{key}">']
    listing = None
    for line in lines:
        line = line.strip()
        kind = 'ul' if line.startswith('- ') else 'ol' if re.match(r'^\d+\. ',line) else None
        if listing and kind != listing:
            output.append(f'</{listing}>')
            listing = None
        if not line:
            continue
        if kind:
            if not listing:
                listing = kind
                output.append(f'<{kind}>')
            output.append('<li>'+inline(line.split(' ',1)[1])+'</li>')
        elif line.startswith('```'):
            language = line[3:].strip()
            code = []
            for content in lines:
                if content.strip() == '```':
                    break
                code.append(content)
            else:
                raise ValueError(f'Unclosed code block in {key}')
            label = {'powershell':'Windows PowerShell', 'bash':'터미널','sh':'터미널','text':'AI에게 보낼 질문'}.get(language,'복사할 내용')
            if language == 'text' and (not code or len('\n'.join(code))<40):
                label='입력 예시'
            output.append(f'<div class="example"><div><span>{escape(label)}</span><button class="copy" type="button">복사</button></div><pre><code>'+escape('\n'.join(code))+'</code></pre></div>')
        elif re.match(r'^#{1,3} ',line):
            heading, title=line.split(' ',1)
            tag='h'+str(len(heading)+1)
            output.append(f'<{tag}>{inline(title)}</{tag}>')
        else:
            output.append('<p>'+inline(line)+'</p>')
    if listing:
        output.append(f'</{listing}>')
    output.append('</section>')
    return '\n'.join(output)


def build(standalone=False):
    links = ''.join(f'<a href="#{key}">{label}</a>' for key,label,_ in CHAPTERS)
    chapters = '\n'.join(chapter(key,(ROOT/'docs'/file).read_text('utf8')) for key,_,file in CHAPTERS)
    style = '<link rel="stylesheet" href="static/student-guide.css">'
    script = '<script defer src="static/student-guide.js"></script>'
    if standalone:
        style = '<style>'+ (ROOT/'static/student-guide.css').read_text('utf8')+'</style>'
        script = '<script>'+ (ROOT/'static/student-guide.js').read_text('utf8')+'</script>'
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hyperpass 수강생 가이드</title>{style}</head>
<body><a class="skip" href="#install">본문으로 이동</a><div class="layout"><nav aria-label="가이드 목차"><a class="brand" href="#top">H↗ HYPERPASS</a><p>수강생 가이드</p>{links}<button type="button" id="print">인쇄 · PDF 저장</button></nav>
<main><header id="top"><h1>Hyperpass 수강생 가이드</h1><p>내 컴퓨터에서 첫 종목을 조회하고, AI 팀에 질문하고, 내 분석 방법으로 바꾸는 과정을 따라 해보세요.</p></header>
{chapters}<footer><a href="#top">맨 위로 ↑</a></footer></main></div><span id="copy-status" aria-live="polite"></span>{script}</body></html>
"""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--standalone', type=Path, help='also create a single-file handout with embedded assets')
    args = parser.parse_args()
    (ROOT/GUIDE).write_bytes(build().encode('utf8'))
    if args.standalone:
        args.standalone.write_bytes(build(standalone=True).encode('utf8'))
