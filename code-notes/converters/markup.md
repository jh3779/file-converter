# markup.py — TXT/MD/HTML 6방향 상호 변환

원본: `app/converters/markup.py` (157줄)

DEC-061에서 확정된 기능. TXT·MD·HTML 세 포맷이 서로 모두 변환 가능하게
(3×2=6개 함수) 구현돼 있다. 이 파일은 "허용적 라이선스만, 가능하면 순수
Python만" 이라는 이 프로젝트의 의존성 선택 원칙을 가장 잘 보여주는 예다 —
docstring 자체가 후보 라이브러리를 왜 골랐고 왜 뺐는지 설명하는 미니
결정 기록이다.

---

## L1-16: 모듈 docstring — 라이브러리 선택 근거

- **MD→HTML**: `Markdown`(Python-Markdown, BSD-3-Clause). `extensions=["extra"]`
  옵션으로 표·펜스 코드블록·각주 같은 GFM(GitHub Flavored Markdown) 핵심
  문법을 추가 설치 없이 지원한다.
- **HTML→MD**: `markdownify`(MIT). 내부적으로 BeautifulSoup4를 쓰지만
  기본 파서가 이미 `html.parser`(파이썬 표준 라이브러리, lxml 같은 C
  확장이 필요 없는 순수 Python)라 문제없다.
- **HTML→TXT**: 같은 BeautifulSoup4를 재사용 — **신규 의존성이 하나도
  추가되지 않는다**(MD→HTML/HTML→MD에서 이미 끌어온 라이브러리를
  그대로 씀).
- **TXT→MD, TXT→HTML**: 라이브러리 자체가 필요 없다 — TXT는 마크업
  문법이 없으므로 "특수문자를 이스케이프해서 원본 그대로 보이게"
  만드는 게 전부다.
- **명시적으로 배제한 후보**: `html2text`는 GPL-3.0-or-later라서 이
  프로젝트의 "GPL 계열 명시적 배제" 원칙(pyhwp AGPL, libx264 GPL과
  같은 이유)에 걸려 제외됐다.

## L17-26: import와 HTML 템플릿

```python
import html
import re
from pathlib import Path

from .base import read_text_auto_encoding

_HTML_DOC_TEMPLATE = (
    "<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"></head>\n"
    "<body>\n{body}\n</body>\n</html>\n"
)
```

- `html`(표준 라이브러리)은 `html.escape()`만 쓴다(특수문자 이스케이프).
  markdown/markdownify/bs4처럼 무거운 서드파티는 이 파일에서도 각 함수
  안에서 지역 import(L73, L90, L112, L146-147)로 지연 로딩한다.
- `_HTML_DOC_TEMPLATE`: TXT→HTML, MD→HTML 두 함수가 공유하는 최소한의
  HTML 뼈대(DOCTYPE·charset meta·body). `{body}` 자리에 실제 변환된
  내용을 채워 넣는다 — 완전한 HTML 문서를 만들어야 브라우저나 다른
  도구가 인코딩을 올바르게 인식한다(`meta charset="utf-8"`이 없으면
  한글이 깨질 수 있음).

## L29-43: `txt_to_html`

```python
def txt_to_html(src: Path, tmpdir: Path) -> Path:
    text = read_text_auto_encoding(src)
    blocks = re.split(r"\n\s*\n", text.strip())
    body = "\n".join(
        f"<p>{html.escape(block).replace(chr(10), '<br>' + chr(10))}</p>"
        for block in blocks if block.strip()
    )
    out = tmpdir / (src.stem + ".html")
    out.write_text(_HTML_DOC_TEMPLATE.format(body=body), encoding="utf-8")
    return out
```

- **L36**: `re.split(r"\n\s*\n", text.strip())` — "빈 줄(공백만 있어도
  됨)로 구분된 덩어리"를 문단으로 나눈다. `\n\s*\n`은 개행 하나, 그
  사이에 공백 문자(스페이스·탭 포함 가능), 다시 개행 — 즉 "완전히
  빈 줄"뿐 아니라 "공백만 있는 줄"도 문단 구분자로 인정한다.
- **L37-40**: 각 블록(문단)에 대해:
  - `html.escape(block)`으로 `<`, `>`, `&` 등을 HTML 엔티티로
    이스케이프한다 — 원본 텍스트에 우연히 `<script>alert(1)</script>`
    같은 문자열이 있어도, 이스케이프하지 않으면 실행 가능한 HTML로
    잘못 해석될 위험이 있다(TXT는 원래 "그냥 텍스트"인데 그대로
    HTML에 박으면 의미가 바뀌어버림 — 이스케이프가 그걸 막는다).
  - `.replace(chr(10), '<br>' + chr(10))`: 이스케이프된 문단 **안**의
    단일 줄바꿈(`\n`, `chr(10)`)을 `<br>\n`으로 바꾼다 — 문단 경계는
    이미 `<p>`로 나눴으니, 문단 **내부의** 줄바꿈만 `<br>`(줄바꿈 태그)로
    표현한다.
  - `if block.strip()`: 빈 블록(공백만 있는 덩어리)은 건너뛴다.
- 왜 이런 휴리스틱이 필요한가(docstring L30-32): TXT는 "문단"이라는
  구조 자체가 없는 순수 텍스트다. "빈 줄 = 문단 경계"라는 일반적인
  텍스트 작성 관행에 기대어 HTML의 문단 구조로 근사하는 것이다.

## L46-54: 마크다운 이스케이프 규칙 (`txt_to_md`가 쓰는 정규식)

```python
_MD_SPECIAL = r"\`*_{}[]()#+-.!|>~"
_MD_ESCAPE_RE = re.compile(f"([{re.escape(_MD_SPECIAL)}])")
```

- `_MD_SPECIAL`: 마크다운에서 의미를 갖는 모든 특수문자 — 백틱(코드),
  별표/언더스코어(강조), 중괄호/대괄호/괄호(링크·이미지), `#`(제목),
  `+`/`-`(목록), `.`(번호 목록), `!`(이미지), `|`(표), `>`(인용),
  `~`(취소선) 전부.
- 설계 판단(주석 L46-52)이 중요하다: 마크다운 표준 문법은 보통 "줄
  맨 앞에서만" 제목/목록으로 해석되지만(예: 문장 중간의 `#`은 그냥
  글자), 이 코드는 **위치를 가리지 않고 전부 이스케이프**한다.
  이유: 문장 중간의 `*`나 `_`, `[`도 강조·링크로 오인될 수 있어서다.
  다소 과잉 이스케이프가 되어(원본에 없던 백슬래시가 많이 붙어) 살짝
  지저분해 보일 수 있지만, "놓쳐서 원본 의미가 실제로 바뀌는 것"
  (예: `"# 안내"`가 진짜 제목으로 렌더링됨)보다는 안전하다는 원칙 —
  이 프로젝트의 다른 곳(DEC-027, "서식 불명 시 안전한 기본값")과
  같은 태도라고 명시돼 있다.
- `re.compile(f"([{re.escape(_MD_SPECIAL)}])")`: `_MD_SPECIAL`의 각
  문자를 정규식 문자 클래스(`[...]`) 안에 넣되, `re.escape()`로
  정규식 자체에서 특별한 의미를 갖는 문자(`[`, `]`, `\` 등)를 다시
  이스케이프한다 — "마크다운 특수문자"와 "정규식 특수문자"가 겹치는
  부분(`*`, `+`, `.`, `(`, `)`, `[`, `]` 등)이 있어 이중 이스케이프가
  필요하다. 바깥 괄호 `(...)`는 캡처 그룹 — 아래 `sub`에서
  `\1`(매치된 그 문자 자체)로 다시 참조하기 위해서다.

## L57-66: `txt_to_md`

```python
def txt_to_md(src: Path, tmpdir: Path) -> Path:
    text = read_text_auto_encoding(src)
    escaped = _MD_ESCAPE_RE.sub(r"\\\1", text)
    out = tmpdir / (src.stem + ".md")
    out.write_text(escaped, encoding="utf-8")
    return out
```

- `_MD_ESCAPE_RE.sub(r"\\\1", text)`: 매치된 각 특수문자(`\1`) 앞에
  백슬래시(`\\`)를 붙인다. `r"\\\1"`은 raw 문자열이므로 실제로는
  "백슬래시 문자 하나 + 캡처 그룹 1"을 의미한다 — 예를 들어 `*`가
  매치되면 `\*`로 치환된다. 마크다운 렌더러는 `\*`를 강조 기호가
  아니라 글자 그대로의 `*`로 해석하므로, 렌더링해도 원본과 똑같이
  보인다(docstring이 "실제로 렌더링해 확인했다"고 명시).

## L69-79: `md_to_html`

```python
def md_to_html(src: Path, tmpdir: Path) -> Path:
    import markdown
    text = read_text_auto_encoding(src)
    body = markdown.markdown(text, extensions=["extra"])
    out = tmpdir / (src.stem + ".html")
    out.write_text(_HTML_DOC_TEMPLATE.format(body=body), encoding="utf-8")
    return out
```

`markdown.markdown(text, extensions=["extra"])` 한 줄이 실제 변환의
전부다 — Python-Markdown 라이브러리가 마크다운 텍스트를 HTML 문자열로
바꿔주고, `"extra"` 확장이 표·펜스 코드블록·각주 등을 추가로 지원한다.
결과를 `_HTML_DOC_TEMPLATE`에 끼워 완전한 HTML 문서로 만든다.

## L82-97: `md_to_txt` — "이미 검증된 파이프라인 재사용" 패턴

```python
def md_to_txt(src: Path, tmpdir: Path) -> Path:
    import markdown
    text = read_text_auto_encoding(src)
    html_body = markdown.markdown(text, extensions=["extra"])
    plain = _html_to_txt_body(html_body)
    out = tmpdir / (src.stem + ".txt")
    out.write_text(plain + "\n", encoding="utf-8")
    return out
```

- 이 함수의 설계가 이 파일에서 가장 흥미로운 지점이다: MD→TXT를 직접
  구현(마크다운 문법 기호를 정규식으로 벗겨내는 별도 파서를 짜는 것)
  하는 대신, **이미 검증된 MD→HTML(L76의 `markdown.markdown`)로 먼저
  변환한 뒤, 이미 검증된 HTML→TXT 로직(`_html_to_txt_body`, 아래
  L104-122)을 재사용**한다.
- docstring(L85-87)이 이 설계를 명시적으로 정당화한다: "두 개의
  반쯤 검증된 변환기를 따로 만드는 대신 이미 검증된 파이프라인
  하나를 재사용" — 이건 이 프로젝트의 다른 곳(HWP의
  `HwpToJson`/`JsonToHwp`가 blocks 스키마를 공유하는 것)과 같은
  원칙이다: 새 변환 경로가 필요할 때, 완전히 새로 짜기보다 이미
  검증된 중간 표현(여기서는 HTML)을 경유하는 쪽을 택한다.
- **알려진 한계(docstring L88-89)**: 표는 마크다운 렌더링을 거치면
  HTML `<table>`이 되고, 그걸 다시 TXT로 뽑으면 셀마다 줄바꿈으로
  풀려서 **열 정렬(칸 맞춤)이 사라진다** — TXT 자체가 표를 표현할
  수단이 없다는 근본적 제약이라고 명시돼 있다.

## L100-101: `_BLOCK_TAGS`

```python
_BLOCK_TAGS = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "pre")
```

"줄바꿈으로 취급해야 하는 HTML 태그" 목록 — 문단, 목록 항목, 표 행,
제목, 인용문, 코드블록 등. `<b>`, `<span>`, `<a>` 같은 **인라인** 태그는
이 목록에 없다(문장 중간에 등장하므로 줄을 끊으면 안 됨).

## L104-122: `_html_to_txt_body` — HTML→TXT 추출의 핵심 로직

```python
def _html_to_txt_body(html_text: str) -> str:
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
```

- **L114**: `BeautifulSoup(html_text, features="html.parser")` —
  파서를 명시적으로 `"html.parser"`(파이썬 표준 라이브러리 내장)로
  고정한다. bs4는 lxml이 설치돼 있으면 그걸 기본으로 쓸 수도 있는데,
  이 프로젝트는 순수 Python 원칙을 지키려 명시적으로 고정했다.
- **L115-116**: `soup(["script", "style", "head"])`로 스크립트·스타일·
  head 태그를 찾아 `.decompose()`(트리에서 완전히 제거)한다. 이게
  발견된 실제 버그를 고친 코드다(docstring L105-106): `<head>` 안의
  `<title>텍스트</title>`를 제거하지 않으면, 그 텍스트가 "본문이
  아닌데도" 나중에 `get_text()`로 뽑힐 때 본문 맨 앞에 섞여 나오는
  문제가 있었다.
- **L117-118**: `_BLOCK_TAGS`에 속하는 모든 태그를 찾아서, 그 태그
  **바로 뒤에** 줄바꿈 문자(`NavigableString("\n")`, bs4가 다루는
  "순수 텍스트 노드")를 삽입한다. 이게 두 번째로 고친 실제 버그다
  (docstring L107-111): `bs4.get_text(separator="\n")`처럼 `get_text`
  자체에 구분자를 주면, **모든** 태그 경계(인라인 태그 포함)마다
  줄바꿈이 들어가 버려서, 예를 들어 `"이것은 <b>굵은</b> 글자"`가
  `"이것은 \n굵은\n 글자"`처럼 문장 중간에서 줄이 갈라진다. 그래서
  대신 "블록 태그 뒤에만 수동으로 개행 마커를 심어두고, `get_text()`
  자체는 구분자 없이(`text = root.get_text()`, L120) 호출"하는 방식
  으로 바꿨다 — 인라인 태그는 줄을 안 끊고, 블록 태그만 끊는다.
- **L119**: `soup.body`가 있으면(완전한 HTML 문서라면) 그 안쪽만,
  없으면(단편적인 HTML 조각이라면) `soup` 전체를 대상으로 삼는다.
- **L121**: `re.sub(r"[ \t]+\n", "\n", text)` — 줄 끝의 트레일링
  공백/탭을 제거한다(줄바꿈 직전의 공백·탭 뭉치를 그냥 줄바꿈으로).
- **L122**: `re.sub(r"\n{3,}", "\n\n", text)` — 연속된 빈 줄이 3개
  이상이면 2개(빈 줄 하나)로 축소한다. 블록 태그마다 개행을 넣다
  보면 중첩된 구조(예: `<div><p>...</p></div>`)에서 개행이
  여러 번 겹쳐 생기는데, 이걸 정리하는 마무리 단계. `.strip()`으로
  앞뒤 여백도 제거한다.

## L125-131: `html_to_txt`

`_html_to_txt_body`를 그대로 호출하는 3줄짜리 얇은 래퍼 — 실제 로직은
전부 위 헬퍼에 있다.

## L134-157: `html_to_md`

```python
def html_to_md(src: Path, tmpdir: Path) -> Path:
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
```

- **L151-152**: `_html_to_txt_body`와 같은 이유(docstring L142-144)로,
  `markdownify`에 넘기기 **전에** 직접 `<head>`를 잘라낸다 —
  `markdownify` 라이브러리 자체가 head/title을 본문과 구분하지
  않고 그대로 변환해버려서, `<title>텍스트`가 실제 마크다운 본문
  맨 앞에 새는 걸 직접 렌더링해서 확인했다고 명시돼 있다. 즉
  `_html_to_txt_body`가 bs4로 직접 처리한 문제를, 여기서는
  `markdownify` 호출 전에 미리 정리해서 우회한다(라이브러리마다
  같은 종류의 문제가 반복해서 나타났다는 걸 보여준다).
- **L154**: `heading_style="atx"` — HTML `<h1>`~`<h6>`을 마크다운으로
  바꿀 때, markdownify의 기본값은 1·2단계 제목은 밑줄 스타일
  (`제목\n===`), 3단계부터는 ATX 스타일(`### 제목`)을 섞어 쓴다.
  이 코드는 **레벨과 무관하게 전부 ATX 스타일**(`#`, `##`, `###`...)
  로 통일해 일관성을 유지한다(docstring L135-137).
- `bs4_options="html.parser"`: markdownify 기본값이 이미 이거지만,
  주석(L137-140)에 "향후 라이브러리 버전이 기본값을 바꾸더라도 이
  프로젝트의 순수 Python 원칙이 깨지지 않도록 명시적으로 고정"한다고
  적혀 있다 — 즉 "지금은 필요 없지만 미래를 위한 방어적 코드"라는
  의도를 남겨둔 사례.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `md_to_txt`가 별도 MD 파서를 짜지 않고 왜 MD→HTML→TXT 경로를 택했는가?
  이 설계가 이 프로젝트의 다른 어떤 부분과 같은 원칙을 따르는가?
- `_html_to_txt_body`에서 `get_text(separator="\n")`을 안 쓰고
  `insert_after(NavigableString("\n"))`을 직접 쓴 이유는?
- `txt_to_md`의 이스케이프가 "줄 맨 앞"이 아니라 "위치 무관 전부"를
  택한 트레이드오프는 무엇인가?
- `html_to_md`와 `_html_to_txt_body`가 각각 `<head>`/`<title>` 문제를
  어떻게(같은 방식? 다른 방식?) 해결했는가?
