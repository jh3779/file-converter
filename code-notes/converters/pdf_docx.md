# pdf_docx.py — PDF → DOCX (줄 단위 절대 위치 재구성)

원본: `app/converters/pdf_docx.py` (322줄)

`pdf.py`가 제공하는 저수준 추출 함수(정렬 추정, run 서식, 도형 추출)를
가져다, **DOCX 고유의 출력 방식**(`w:framePr`로 절대 위치, `w:pBdr`로
테두리)을 구현하는 "작성 어댑터"다. 이 파일의 핵심 아이디어는 —
python-docx가 지원하지 않는 "자유 배치 도형"을, DOCX가 원래 다른
목적(신문 레이아웃 같은 텍스트 프레임)으로 갖고 있던 **레거시 기능
(`w:framePr`)을 전용해서** 흉내 낸다는 것.

---

## L1-6: 모듈 docstring

`pdf_pptx.py`와 대칭 구조라는 점, 그리고 2026-08 구조 감사에서
"공유 추출·DOCX 작성·PPTX 작성"이 원래 `pdf.py` 한 파일에 섞여 있던
걸 분리했다는 배경(`pdf.py`의 code-notes와 동일한 배경).

## L9-18: import — `pdf.py`에서 6개 함수를 가져옴

```python
from .pdf import (
    _container_to_runs, _detect_alignment, _iter_lines, _iter_visuals,
    _paragraph_candidates, _underline_candidates, _visual_to_dict,
)
```

전부 `pdf.py`의 code-notes에서 이미 설명한 함수들 — 이 파일은 "PDF를
읽는 방법"을 하나도 새로 만들지 않고, 오직 "읽어낸 결과를 DOCX로
쓰는 방법"만 구현한다.

## L21-137: `pdf_to_docx` — 메인 함수 (긴 docstring 먼저)

### 설계 배경(docstring L22-74)

- **핵심 아이디어(L22-29, DEC-037)**: 각 텍스트 **줄**을 PDF 원본과
  같은 절대 좌표에 고정해서 배치한다 — `pdf_to_pptx`(DEC-030)의
  "줄 단위 재구성"과 같은 원리를, DOCX의 `w:framePr`(문단을 페이지
  절대좌표에 고정하는 레거시 기능, Word·LibreOffice 둘 다 지원)로
  구현한다. 예전엔 문단을 순서대로 이어붙여 그냥 흐르는 문서로
  단순화했었는데(DEC-010), 지금은 원본과 시각적으로 훨씬 가까운
  결과를 낸다.
- **왜 pdf2docx(PyMuPDF)를 안 쓰는가(L31)**: AGPL 라이선스라 이
  프로젝트의 라이선스 원칙(DEC-007)에 어긋나 배제.
- **트레이드오프(L33-37, 사용자 확인 후 채택)**: 각 줄이 독립된
  프레임이므로, 결과 DOCX는 일반적인 "이어서 타이핑하면 자연스럽게
  흐르는" 문서가 **아니다** — 프레임 폭을 넘는 텍스트를 추가하면
  다음 줄과 자연스럽게 안 이어진다. "위치 정확도"와 "자유 편집
  가능성" 사이의 근본적 상충을 위치 정확도 쪽으로 택한 것.
- **이미지·도형(L39-46, DEC-036/DEC-054)**: python-docx엔 pptx의
  셰이프 API 같은 고수준 도형 삽입 기능이 없다 — 그래서 "빈 문단을
  절대 위치시키고, 그 문단 안/테두리에 내용을 채우는" 우회 방법을
  쓴다: 이미지는 문단 안에 그림 삽입, 사각형·직선은 문단 테두리
  (`w:pBdr`)로 표현.
- **밑줄 감지(L48-54)**: `pdf.py`의 `_underline_candidates`/
  `_char_is_underlined`로 텍스트 아래 벡터 선을 찾아 밑줄로 판정한다
  — 이미 밑줄로 쓰인 선은 표 테두리 도형으로 **다시 그리지 않도록
  제외**한다(중복 렌더링 방지, `pdf.py` 문서의 밑줄 섹션 참고).
- **알려진 한계 6가지(L56-73)**:
  1. 곡선(LTCurve)은 정확한 다각형이 아니라 bounding box 사각형으로
     더 단순하게 근사(python-docx에 프리폼 곡선 API가 없어서).
  2. 도형·텍스트의 z-순서(어느 게 위에 그려지는지)가 완전히 보존
     안 됨 — 도형 먼저, 텍스트 나중에 그려 텍스트가 항상 위에 보임.
  3. 디코딩 실패 이미지는 조용히 건너뜀.
  4. 항상 Noto Sans KR을 쓰므로(DEC-015) 원본 폰트와 글자 폭이 달라
     드물게 줄바꿈이 살짝 밀릴 수 있음.
  5. 한글 글꼴은 이탤릭 글리프가 없는 경우가 흔해 기울임 감지가
     잘 안 됨(원본 자체의 한계).
  6. 밑줄 판정이 위치 근접성 휴리스틱이라, 우연히 텍스트 아래를
     지나가는 다른 용도의 선을 밑줄로 오판할 이론적 가능성이 있음
     — 실사용 중 문제가 나오면 임계값 상수를 조정할 것.

### 함수 본문

```python
from .docx_build import _align_map, _apply_run_style, _set_font

EMU_PER_PT = 12700
image_dir = tmpdir / "_pdf_docx_images"
layout = _extract_pdf_line_layout(src, image_dir)
if not layout:
    raise ConversionError("err.corrupted", "페이지 없음")

doc = Document()
```

- **L79**: `docx_build.py`의 3개 헬퍼(`_align_map`, `_apply_run_style`,
  `_set_font`)를 재사용한다 — 정렬 매핑·서식 적용·폰트 강제 지정
  로직을 여기서 또 만들지 않는다.
- **L83**: `_extract_pdf_line_layout`(이 파일 아래쪽에 정의, L274-322)
  로 PDF 전체를 "페이지별 줄·도형 목록"이라는 이 파일 전용 중간
  표현으로 미리 뽑아둔다.

### L89-95: 섹션 크기 설정 헬퍼

```python
def _size_section(section, page):
    section.page_width = Emu(round(page["width"] * EMU_PER_PT))
    section.page_height = Emu(round(page["height"] * EMU_PER_PT))
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, attr, Emu(0))

_size_section(doc.sections[0], layout[0])
current_size = (layout[0]["width"], layout[0]["height"])
```

- PDF 좌표(pt)를 DOCX가 요구하는 EMU로 변환(`EMU_PER_PT = 12700` —
  1pt = 12700 EMU, OOXML 표준 단위 환산).
- **모든 여백을 0으로 만든다** — 이게 핵심이다. `w:framePr`이
  "페이지 기준" 절대좌표(L157-158의 `hAnchor="page"`,
  `vAnchor="page"`)로 배치되므로, 만약 Word의 기본 여백(보통 상하좌우
  1인치)이 남아있으면 좌표 계산이 어긋난다. 여백을 0으로 만들어서
  "페이지 원점 = 프레임 좌표 원점"을 일치시킨다.
- `doc.sections[0]`(문서의 첫 섹션)을 첫 페이지 크기로 미리 맞춰둔다.

### L98-134: 페이지 순회 — 페이지 나눔과 크기 변경 처리

```python
for page_index, page in enumerate(layout):
    if page_index > 0:
        page_size = (page["width"], page["height"])
        if page_size == current_size:
            doc.add_page_break()
        else:
            section = doc.add_section(WD_SECTION.NEW_PAGE)
            _size_section(section, page)
            current_size = page_size
    ...
```

**재현된 버그 방지 코드(주석 L104-111)**: 스캔 첨부문서처럼 페이지마다
가로/세로가 섞인 PDF(예: 세로 페이지들 사이에 가로 스캔 페이지가
낀 경우)에서, 단순히 `add_page_break()`만 쓰면 **섹션의 page_width/
height가 첫 페이지 크기로 고정된 채로 남는다**. 그러면 아래
`page_h - y1`(y좌표를 "페이지 하단 기준"으로 뒤집는 계산, DOCX와
PDF의 y축 방향이 반대라서 필요)이 **실제 렌더링되는 페이지 높이와
다른 값**을 써서 텍스트가 밀려 보이는 버그가 있었다(PR 리뷰로 발견).
지금은 페이지 크기가 실제로 바뀔 때만(`page_size != current_size`)
새 섹션(`doc.add_section`)을 열어 그 페이지의 실제 크기로 다시
맞춘다 — 흔한 "같은 크기 페이지가 계속되는" 경우는 그냥 단순 페이지
나눔만 쓴다(불필요하게 매번 새 섹션을 만들지 않음).

### L115-133: 도형과 텍스트 줄 배치

```python
page_h = page["height"]
for visual in page["visuals"]:
    _add_visual_to_docx(doc, visual, page_h)
for line in page["lines"]:
    x0, y0, x1, y1 = line["bbox"]
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    for run_dict in line["runs"]:
        run = p.add_run(run_dict["text"])
        _set_font(run)
        _apply_run_style(run, run_dict)
    align = _align_map().get(line.get("align"))
    if align is not None:
        p.alignment = align
    _set_frame_pr(p, x_pt=x0, y_pt=page_h - y1,
                  w_pt=max(x1 - x0, 1), h_pt=_text_frame_height_pt(y0, y1))
```

- **도형을 먼저, 텍스트를 나중에**(L116-118 순서) — 위에서 설명한
  "z-순서는 텍스트가 항상 위" 트레이드오프를 여기서 구현한다.
- 각 줄마다 새 문단(`doc.add_paragraph()`)을 만들고,
  `space_before/after = 0`, `line_spacing = 1.0`으로 문단 자체의
  여백·줄간격을 최소화한다(프레임 크기를 정확히 계산했는데
  문단 스타일이 추가 여백을 넣으면 위치가 어긋나므로).
- 각 run에 텍스트 추가, 폰트·서식 적용은 `pdf.py`가 뽑아둔 정보
  그대로.
- **`y_pt=page_h - y1`**: PDF 좌표계는 원점이 **왼쪽 아래**이고 y축이
  위로 갈수록 커지는데, DOCX(`w:framePr`)는 원점이 **왼쪽 위**다 —
  그래서 `페이지 높이 - PDF의 y1(줄의 위쪽 끝)`으로 뒤집어야 DOCX
  좌표계의 "위에서부터의 거리"가 된다.

## L140-163: `_set_frame_pr` — `w:framePr`로 절대 위치 고정 (핵심 메커니즘)

```python
def _set_frame_pr(paragraph, x_pt, y_pt, w_pt, h_pt):
    TWIPS_PER_PT = 20
    pPr = paragraph._p.get_or_add_pPr()
    frame_pr = pPr.makeelement(qn("w:framePr"), {
        qn("w:w"): str(max(round(w_pt * TWIPS_PER_PT), 1)),
        qn("w:h"): str(max(round(h_pt * TWIPS_PER_PT), 1)),
        qn("w:hRule"): "exact",
        qn("w:hAnchor"): "page",
        qn("w:vAnchor"): "page",
        qn("w:x"): str(round(x_pt * TWIPS_PER_PT)),
        qn("w:y"): str(round(y_pt * TWIPS_PER_PT)),
        qn("w:wrap"): "none",
    })
    pPr.append(frame_pr)
```

이 함수가 이 파일 전체의 핵심 메커니즘이다. `docx_build.py`의
`_set_font`처럼 python-docx의 고수준 API로는 불가능해서(python-docx가
`w:framePr`을 지원 안 함) XML을 직접 조작한다.

- **왜 `w:framePr`인가(docstring L141-148)**: DrawingML(Word의
  최신 도형/텍스트박스 시스템)의 "플로팅 도형"보다 훨씬 단순한
  **레거시** 기능이지만, Word와 LibreOffice 둘 다 지원하고, "줄
  단위 위치 재현"이라는 이 용도에는 충분하다. 스파이크로 실측 검증:
  지정한 좌표와 LibreOffice로 렌더링한 PDF의 실제 텍스트 위치가
  **2pt 이내**로 일치함을 확인했다.
- `TWIPS_PER_PT = 20`: OOXML의 `w:framePr` 속성값은 twip(1/20 pt)
  단위를 쓴다 — 그래서 pt 값에 20을 곱한다.
- **속성 하나하나의 의미**:
  - `w:w`, `w:h`: 프레임의 너비·높이.
  - `w:hRule="exact"`: 높이를 "정확히 이 값으로 고정"(내용이 넘쳐도
    프레임이 자동으로 늘어나지 않음) — 아래 `_text_frame_height_pt`
    문서에서 이 선택의 이유가 자세히 나온다.
  - `w:hAnchor="page"`, `w:vAnchor="page"`: 가로·세로 위치 모두
    **페이지 기준**(문단이나 여백 기준이 아니라)으로 앵커.
  - `w:x`, `w:y`: 페이지 원점(왼쪽 위)에서부터의 절대 위치.
  - `w:wrap="none"`: 이 프레임 주변으로 다른 텍스트가 흘러들어오지
    않게(각 줄 프레임이 서로 독립적으로 겹치지 않게 배치).
- `max(round(w_pt * TWIPS_PER_PT), 1)`: 너비·높이가 0 이하가 되지
  않도록 최소 1을 보장(0이면 렌더러가 이상하게 처리할 수 있음).

## L166-190: 텍스트 프레임 높이 보정 — 폰트 메트릭 기반 (실제 렌더링 버그 수정)

```python
_NOTO_SANS_KR_LINE_HEIGHT_RATIO = 1.448

def _text_frame_height_pt(y0: float, y1: float) -> float:
    font_size = max(y1 - y0, 1)
    return font_size * _NOTO_SANS_KR_LINE_HEIGHT_RATIO
```

**이 상수와 함수가 존재하는 이유(docstring L173-190)는 실제 발견된
시각적 결함의 수정이다**:

- **원인**: PDF 원문 폰트가 무엇이었든, 이 프로젝트의 렌더링은
  항상 Noto Sans KR로 대체된다(DEC-015). Noto Sans KR의 **실제
  줄 높이**(폰트 디자인상 필요한 위아래 공간, ascent+descent)가
  pdfminer가 준 원본 bbox 높이(`y1-y0`, 원본 폰트 기준이라 대개 더
  작음)보다 크다. 그런데 `h_pt`(프레임 높이)로 원본 bbox 높이를
  그대로 쓰고 `hRule="exact"`로 고정하면, Noto Sans KR로 렌더링될
  때 초과분이 **프레임 밖으로 잘려** 글자 대부분(특히 g/p처럼 아래로
  내려가는 디센더가 있는 글자)이 안 보이는 결함이 있었다 — 글꼴
  크기나 서식과 무관하게 재현됐고, DEC-055 검증 중 처음으로 실제
  LibreOffice 렌더링을 육안으로 확인해서 발견했다.
- **1.448이라는 정확한 값의 출처(L166-169)**: Noto Sans KR(Regular·
  Bold 둘 다 동일)의 실제 줄 높이 계산식 — `(hhea/OS-2 usWin ascent
  + descent) / unitsPerEm = (1160+288)/1000 = 1.448`. 이건
  fontTools(폰트 파일을 직접 파싱하는 라이브러리)로 실측한 값이다
  — 즉 "대충 여유를 준" 게 아니라 폰트 파일 자체의 메트릭 데이터를
  근거로 정확히 계산됐다.
- **왜 `hRule="atLeast"`(자동으로 늘어나는 프레임)를 안 썼는가
  (L181-186)**: 이것도 시도했지만, 원본 PDF의 줄 간격이 원래
  폰트 기준으로 촘촘한 경우(흔함)에는 늘어난 프레임이 **바로 다음
  줄과 겹쳐서** 텍스트가 뒤섞여 보이는 **새로운 문제**가 생기는 걸
  직접 렌더링 비교로 확인했다. 그래서 대신 "필요한 높이를 미리
  계산해서 `hRule="exact"`인 채로 정확히 그만큼만 키우는" 지금의
  방식을 택했다 — 오버랩도 클리핑도 없음을 3줄짜리 촘촘한 간격
  샘플로 직접 확인.
- **이미지·도형은 이 함수를 안 거친다(L186-188)**: 이미지/도형은
  폰트 메트릭과 무관한 내용이라(그림은 그림 그대로의 크기가 맞음)
  원래 bbox 크기를 그대로 쓴다 — `_add_visual_to_docx`를 보면
  실제로 `_text_frame_height_pt`를 호출하지 않는다.

## L193-238: `_add_visual_to_docx` — 이미지/도형 하나를 배치

```python
def _add_visual_to_docx(doc, visual: dict, page_h: float):
    x0, y0, x1, y1 = visual["bbox"]
    w_pt, h_pt = max(x1 - x0, 1), max(y1 - y0, 1)
    top_pt = page_h - y1

    if visual["kind"] == "image":
        p = doc.add_paragraph()
        ...
        try:
            p.add_run().add_picture(visual["path"], width=Pt(w_pt), height=Pt(h_pt))
        except Exception:
            p._p.getparent().remove(p._p)
            return
        _set_frame_pr(p, x_pt=x0, y_pt=top_pt, w_pt=w_pt, h_pt=h_pt)
        return

    p = doc.add_paragraph()
    ...
    linewidth_pt = max(visual.get("linewidth") or 0.75, 0.25)
    if visual["kind"] == "line":
        lx0, ly0 = visual["p0"]
        lx1, ly1 = visual["p1"]
        sides = ["right"] if abs(ly1 - ly0) > abs(lx1 - lx0) else ["bottom"]
    else:
        sides = ["top", "bottom", "left", "right"]
    if visual.get("stroke"):
        _set_paragraph_borders(p, sides, visual["stroke"], linewidth_pt)
    if visual.get("fill"):
        _set_paragraph_shading(p, visual["fill"])
    _set_frame_pr(p, x_pt=x0, y_pt=top_pt, w_pt=w_pt, h_pt=h_pt)
```

- **이미지 처리(L207-218)**: 빈 문단을 만들고 `add_run().add_picture(...)`
  로 이미지를 넣는다. **실패 시 처리(L212-216)가 중요**: 이미지
  삽입이 실패하면(디코딩 문제 등), `p._p.getparent().remove(p._p)`
  로 **방금 만든 빈 문단 자체를 문서에서 제거**한다 — 그냥
  `return`만 하면 내용 없는 빈 프레임 문단이 남아 이상하게 보일 수
  있으므로, 실패 시 흔적을 깨끗이 지운다.
- **도형(선/사각형/곡선) 처리(L220-238)**:
  - `linewidth_pt = max(visual.get("linewidth") or 0.75, 0.25)`:
    선 굵기 정보가 없으면 0.75pt를 기본값으로, 최소 0.25pt는
    보장(너무 얇아서 안 보이는 선 방지).
  - **`kind == "line"`(직선)일 때 변 선택(L225-231, 실제 재현된
    버그 수정)**: 처음엔 "위/아래 두 변"(가로선의 경우) 또는
    "좌/우 두 변"을 다 그려서 표현하려 했는데, 실제 LibreOffice
    렌더링에서 **얇은 프레임 안에 겹쳐 보여야 할 두 선이 육안으로
    갈라져(이중선처럼) 보이는** 문제를 발견했다 — 그래서
    지금은 **변 하나만** 쓴다. `abs(ly1-ly0) > abs(lx1-lx0)`
    (세로 변화가 가로 변화보다 크면 = 세로선)이면 오른쪽 변
    (`"right"`)만, 아니면(가로선) 아래쪽 변(`"bottom"`)만 사용.
  - `kind`가 `"rect"`나 `"curve"`(사각형이나 근사된 곡선)면 4변
    전부(`"top","bottom","left","right"`) 사용.
  - `stroke`(선 색)가 있으면 `_set_paragraph_borders`로 테두리,
    `fill`(채움 색)이 있으면 `_set_paragraph_shading`으로 배경
    채움을 적용.

## L241-259: `_set_paragraph_borders` — 문단 테두리 XML 조작

```python
def _set_paragraph_borders(paragraph, sides, color_rgb, width_pt):
    EIGHTHS_PER_PT = 8
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = pPr.makeelement(qn("w:pBdr"), {})
    sz = str(max(round(width_pt * EIGHTHS_PER_PT), 2))
    color = "%02X%02X%02X" % color_rgb
    for side in sides:
        pBdr.append(pBdr.makeelement(qn(f"w:{side}"), {
            qn("w:val"): "single",
            qn("w:sz"): sz,
            qn("w:space"): "0",
            qn("w:color"): color,
        }))
    pPr.append(pBdr)
```

python-docx엔 **표 셀** 테두리 API는 있어도 **일반 문단** 테두리
API가 없어서(주석 L242-243) raw XML로 직접 만든다. `w:sz`(선 굵기)는
1/8pt 단위를 쓰므로 `EIGHTHS_PER_PT = 8`. `for side in sides:`로
호출자가 선택한 변에만(예: `["bottom"]`, 또는 4변 전부)
`w:top`/`w:bottom`/`w:left`/`w:right` 요소를 개별로 추가한다.

## L262-271: `_set_paragraph_shading` — 배경 채움

`w:shd`(문단 배경) XML을 직접 만든다 — `LTRect`의 채움색(fill)을
표현하는 용도.

## L274-322: `_extract_pdf_line_layout` — 이 파일 전용 PDF 추출 파이프라인

```python
def _extract_pdf_line_layout(src, image_dir) -> list[dict]:
    ...
    for page in extract_pages(str(src)):
        visuals = [v for item in _iter_visuals(page)
                   if (v := _visual_to_dict(item, writer, image_dir)) is not None]
        underline_segments = _underline_candidates(visuals)
        lines = []
        for container in _paragraph_candidates(page):
            align = _detect_alignment(container, page.width)
            for line in _iter_lines(container):
                runs = _container_to_runs(line, underline_segments=underline_segments)
                if runs:
                    entry = {"bbox": line.bbox, "runs": runs}
                    if align:
                        entry["align"] = align
                    lines.append(entry)
        visuals = [v for v in visuals if not v.get("_used_as_underline")]
        pages.append({"width": page.width, "height": page.height, "lines": lines, "visuals": visuals})
    ...
```

- **`pdf_pptx.py`의 대응 함수와 왜 통합하지 않았는가(docstring
  L276-287)**: 이미지·도형 추출 로직(`_iter_visuals`/`_visual_to_dict`
  자체)은 이미 `pdf.py`의 공유 헬퍼로 완전히 같다. 두 함수
  (`_extract_pdf_line_layout`와 `pdf_pptx.py`의 대응 함수)가 여전히
  분리된 이유는 딱 두 가지 차이 때문 — `"align"`(문단 단위 정렬,
  PPTX 쪽은 안 씀)과 밑줄 감지(마찬가지로 PPTX는 안 씀). 이 두
  차이만 빼면 완전히 같은 함수라, 통합할 수도 있지만 지금은 두
  버전을 유지한다고 명시(과도한 파라미터화보다 약간의 중복을
  택한 판단으로 읽힌다).
- **L299-301: walrus 연산자(`:=`) 사용**: `(v := _visual_to_dict(...))`
  는 파이썬 3.8+의 "할당 표현식" — `_visual_to_dict`의 결과를
  `v`에 저장하면서 **동시에** 그 값으로 `is not None` 조건을
  평가한다. 리스트 컴프리헨션 안에서 "함수를 한 번만 호출하면서
  결과를 필터링과 값 생성 둘 다에 쓰는" 관용구.
- **L303**: `underline_segments`를 **줄을 순회하기 전에 먼저**
  계산해둔다(주석 L281-283) — 각 줄의 `_container_to_runs` 호출에
  넘겨줘야 하므로, 밑줄 후보가 먼저 준비돼 있어야 한다.
- **L305-313: 정렬은 문단 단위, run은 줄 단위**: `_detect_alignment`
  는 **컨테이너(원본 문단) 단위로 한 번만** 판정하고(L306), 그
  문단에 속한 **모든 줄에 같은 정렬값을 붙인다**(L311-312). 왜
  이렇게 나뉘는가(주석 L284-287): 최종적으로 각 줄은 독립된 프레임
  으로 배치되지만(`pdf_to_docx`), 정렬이 왼쪽/가운데/오른쪽/양쪽인지
  판정하려면 **여러 줄을 함께 봐야 하는 문단 단위 신호**이기
  때문이다(`pdf.py`의 `_classify_alignment` 참고 — 한 줄만으로는
  판정이 어려운 이유).
- **L316**: 밑줄로 실제 쓰인 선(`_used_as_underline` 표시가 붙은
  것)은 최종 `visuals` 목록에서 제외한다 — 이미 텍스트 run의
  `underline=True`로 반영됐으니, 표 테두리 도형으로 다시 그리면
  겹쳐 보이기 때문(위에서 설명한 중복 렌더링 방지의 실제 구현
  지점).

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_set_frame_pr`의 `y_pt` 계산에서 `page_h - y1`을 쓰는 이유는?
  PDF와 DOCX(OOXML)의 좌표계가 어떻게 다른가?
- `_text_frame_height_pt`의 1.448이라는 상수가 어디서 나왔고, 이
  값을 안 쓰고 원본 bbox 높이를 그대로 썼다면 어떤 시각적 결함이
  생기는가?
- `hRule="exact"`와 `hRule="atLeast"`를 각각 썼을 때 어떤 문제가
  생기는지 설명할 수 있는가? 이 함수가 왜 결국 "높이를 미리 계산"
  하는 세 번째 방법을 택했는가?
- 직선(line) 도형에서 "변 하나만" 그리는 이유를 실제 렌더링 결함과
  연결해서 설명할 수 있는가?
- `_extract_pdf_line_layout`과 `pdf_pptx.py`의 대응 함수가 분리된
  이유가 정확히 무엇인가? (완전한 중복이 아니라는 것을 어떻게
  알 수 있는가?)
