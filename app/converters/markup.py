"""TXT/MD/HTML 상호 변환(REQ-F, "Could" 항목이었던 것을 DEC-061로 확정) —
6개 방향(TXT↔MD, TXT↔HTML, MD↔HTML) 전부 지원. 신규 의존성은 순수 Python
+ 허용적 라이선스만 채택(GPL 계열은 이 프로젝트 전체 관례상 명시적으로
배제 — html2text는 GPL-3.0-or-later라 후보에서 제외):

- MD→HTML: `Markdown`(Python-Markdown, BSD-3-Clause) — `extensions=["extra"]`
  로 표·펜스 코드블록·각주 등 GFM 핵심 문법을 추가 설치 없이 지원.
- HTML→MD: `markdownify`(MIT) — 내부적으로 BeautifulSoup4(MIT)를 쓰는데,
  기본값 자체가 이미 순수 Python 파서(`bs4_options="html.parser"`)라
  lxml 등 추가 파서가 필요 없다(이 프로젝트가 python-docx/pptx를 통해
  이미 lxml을 간접 의존하고 있지만, 순수성 원칙을 지키려 명시적으로
  고정한다).
- HTML→TXT: 같은 BeautifulSoup4를 재사용(신규 의존성 추가 없음).
- TXT→MD·TXT→HTML: 별도 라이브러리 불요 — 각 마크업 언어의 특수 문자를
  이스케이프해 "원본 그대로 보이게" 만드는 것만으로 충분하다.
"""
import html
import re
from pathlib import Path

from .base import read_text_auto_encoding

_HTML_DOC_TEMPLATE = (
    "<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"></head>\n"
    "<body>\n{body}\n</body>\n</html>\n"
)


def txt_to_html(src: Path, tmpdir: Path) -> Path:
    """TXT → HTML. 빈 줄로 나뉜 덩어리를 문단(`<p>`)으로, 문단 안의 단일
    줄바꿈은 `<br>`로 바꾼다 — TXT는 문단 구조 자체가 없어 이 휴리스틱으로
    근사한다(빈 줄 = 문단 경계라는 일반적인 텍스트 관행). `html.escape()`로
    `<`·`&` 등을 이스케이프해, 원본에 우연히 `<script>`처럼 보이는 텍스트가
    있어도 실행 가능한 HTML로 잘못 해석되지 않는다."""
    text = read_text_auto_encoding(src)
    blocks = re.split(r"\n\s*\n", text.strip())
    body = "\n".join(
        f"<p>{html.escape(block).replace(chr(10), '<br>' + chr(10))}</p>"
        for block in blocks if block.strip()
    )
    out = tmpdir / (src.stem + ".html")
    out.write_text(_HTML_DOC_TEMPLATE.format(body=body), encoding="utf-8")
    return out


# 마크다운에서 의미를 갖는 특수문자 전부 — 어디에 나타나든 이스케이프한다
# (문단 맨 앞의 "#"·"*"·숫자+"." 뿐 아니라, 문장 중간의 "*"·"_"·"["도 강조·
# 링크로 오인될 수 있어 위치를 가리지 않고 안전하게 전부 이스케이프하는
# 쪽을 택했다 — 과잉 이스케이프로 살짝 지저분해 보일 수 있지만, 반대로
# 놓쳤을 때 원본 텍스트의 의미가 실제로 바뀌는 것(예: "# 안내"가 진짜
# 제목으로 렌더링됨)보다는 안전하다는 원칙, DEC-027의 "서식 불명 시
# 안전한 기본값"과 같은 태도).
_MD_SPECIAL = r"\`*_{}[]()#+-.!|>~"
_MD_ESCAPE_RE = re.compile(f"([{re.escape(_MD_SPECIAL)}])")


def txt_to_md(src: Path, tmpdir: Path) -> Path:
    """TXT → MD. 마크다운 특수문자를 백슬래시로 이스케이프해, 렌더링해도
    원본과 똑같은 평문으로 보이게 한다(로컬에서 `#`·`*`·`1.`·`[각주]`
    등으로 시작/포함하는 텍스트를 실제로 렌더링해 제목·목록·링크로
    오인되지 않음을 직접 확인)."""
    text = read_text_auto_encoding(src)
    escaped = _MD_ESCAPE_RE.sub(r"\\\1", text)
    out = tmpdir / (src.stem + ".md")
    out.write_text(escaped, encoding="utf-8")
    return out


def md_to_html(src: Path, tmpdir: Path) -> Path:
    """MD → HTML. `extensions=["extra"]`로 표·펜스 코드블록·각주 등을
    함께 렌더링한다(로컬에서 표·코드블록·굵게/기울임·목록 조합으로 직접
    렌더링 확인)."""
    import markdown

    text = read_text_auto_encoding(src)
    body = markdown.markdown(text, extensions=["extra"])
    out = tmpdir / (src.stem + ".html")
    out.write_text(_HTML_DOC_TEMPLATE.format(body=body), encoding="utf-8")
    return out


def md_to_txt(src: Path, tmpdir: Path) -> Path:
    """MD → TXT. 마크다운 문법 기호만 정규식으로 벗겨내는 대신, 이미
    검증된 MD→HTML(markdown 라이브러리)로 먼저 렌더링한 뒤 HTML→TXT와
    같은 방식(_html_to_txt_body)으로 텍스트만 뽑는다 — 두 개의 반쯤
    검증된 변환기를 따로 만드는 대신 이미 검증된 파이프라인 하나를
    재사용(HwpToJson/JsonToHwp가 blocks 스키마를 공유하는 것과 같은
    원칙). **알려진 한계**: 표는 셀마다 줄바꿈으로 풀려 열 정렬이
    사라진다(TXT 자체가 표를 표현할 수단이 없어 근본적인 제약)."""
    import markdown

    text = read_text_auto_encoding(src)
    html_body = markdown.markdown(text, extensions=["extra"])
    plain = _html_to_txt_body(html_body)
    out = tmpdir / (src.stem + ".txt")
    out.write_text(plain + "\n", encoding="utf-8")
    return out


_BLOCK_TAGS = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "pre")


def _html_to_txt_body(html_text: str) -> str:
    """HTML 문자열에서 화면에 보이는 텍스트만 뽑는다 — `<head>`(제목
    태그 포함, 본문이 아님)·`<script>`·`<style>`은 통째로 버린다.
    블록 요소(`<p>`·`<li>`·`<br>` 등) 뒤에만 줄바꿈을 끼워 넣고
    `get_text()`엔 구분자를 안 줘서, `<b>`·`<span>` 같은 인라인
    요소가 문장 중간에서 줄을 갈라놓는 문제를 피한다(로컬에서
    `bs4.get_text(separator="\\n")`을 직접 써봤다가 인라인 태그마다
    줄이 갈라지는 문제를 발견해 이 방식으로 바꿈)."""
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html_text, features="html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after(NavigableString("\n"))
    root = soup.body or soup
    text = root.get_text()
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_txt(src: Path, tmpdir: Path) -> Path:
    """HTML → TXT."""
    text = read_text_auto_encoding(src)
    plain = _html_to_txt_body(text)
    out = tmpdir / (src.stem + ".txt")
    out.write_text(plain + "\n", encoding="utf-8")
    return out


def html_to_md(src: Path, tmpdir: Path) -> Path:
    """HTML → MD. 제목은 레벨 무관하게 전부 ATX(`#`·`##`…) 스타일로
    통일한다 — markdownify 기본값(1·2단계는 밑줄, 3단계부터 ATX)은
    레벨에 따라 문법이 달라져 일관성이 떨어진다. `bs4_options`은
    markdownify 기본값이 이미 `"html.parser"`(순수 Python)라 굳이
    바꿀 필요는 없지만, 향후 버전이 기본값을 바꾸더라도 이 프로젝트의
    순수 Python 원칙이 깨지지 않도록 명시적으로 고정해둔다.

    markdownify는 `<head>`(그 안의 `<title>` 포함)를 본문과 구분 없이
    그대로 변환한다 — `<title>텍스트`가 실제 본문 맨 앞에 새는 것을
    직접 렌더링해 확인했다(_html_to_txt_body가 겪은 것과 같은 문제).
    변환 전에 직접 `<head>`를 잘라낸다."""
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    text = read_text_auto_encoding(src)
    soup = BeautifulSoup(text, features="html.parser")
    if soup.head:
        soup.head.decompose()
    body_html = str(soup.body or soup)
    md = markdownify(body_html, heading_style="atx", bs4_options="html.parser")
    out = tmpdir / (src.stem + ".md")
    out.write_text(md.strip() + "\n", encoding="utf-8")
    return out
