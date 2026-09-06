# pdf_pptx.py — PDF → PPTX (python-pptx 셰이프 API로 재구성)

원본: `app/converters/pdf_pptx.py` (181줄)

`pdf_docx.py`와 완전히 같은 목적(PDF의 줄 단위 위치를 그대로 재현)을
가졌지만, PPTX(python-pptx)는 **자유 배치 도형 API를 정식으로 지원**
하므로 `pdf_docx.py`처럼 `w:framePr` 같은 레거시 기능을 우회로 쓸 필요가
없다 — 텍스트 상자·도형·커넥터를 모두 정상적인 고수준 API로 만든다.
이 파일을 `pdf_docx.py`와 나란히 읽으면, "같은 문제를 다른 포맷의
API 성숙도에 따라 어떻게 다르게 풀었는지"가 잘 보인다.

---

## L1-6: 모듈 docstring

`pdf_docx.py`와 대칭 구조라는 점, 2026-08 구조 감사에서 관심사가
분리된 배경 — `pdf.py`/`pdf_docx.py` 문서와 동일.

## L9-10: import — `pdf.py`에서 5개 함수

```python
from .pdf import _container_to_runs, _iter_lines, _iter_visuals, _paragraph_candidates, _visual_to_dict
```

`pdf_docx.py`가 가져온 7개 중 `_detect_alignment`와
`_underline_candidates`가 **빠져 있다** — 이 파일은 정렬 추정과
밑줄 감지를 하지 않는다(아래에서 왜인지 설명).

## L13-78: `pdf_to_pptx` — 메인 함수

### 설계 배경(docstring L14-33)

- **핵심 아이디어(L14-20, DEC-030)**: "한 페이지 = 한 이미지"로
  통째로 뭉개는 방식(가장 단순하지만 텍스트가 편집 불가능해짐)이
  아니라, 각 줄을 원본과 같은 위치·크기의 **개별 텍스트 상자**로
  복원한다. 굵게 판정은 `pdf_docx.py`와 완전히 같은 폰트 이름
  휴리스틱(`pdf.py`의 `_container_to_runs`)을 재사용한다. 이미지·
  사각형·직선·곡선도 원본 위치·크기로 재구성한다(DEC-036) — 표
  테두리는 대개 `LTLine`/`LTRect`로 그려지므로 이제 실제로 옮겨진다.
- **알려진 한계 5가지(L22-33)** — `pdf_docx.py`와 거의 같은 목록
  (아래는 겹치지 않는 부분만 강조):
  1. 곡선은 다각형으로 근사(정확한 곡률 재현 안 됨).
  2. z-순서 미보존 — 도형·이미지를 먼저 그리고 텍스트를 위에
     올리는 "배경 레이어" 방식.
  3. 디코딩 실패 이미지는 조용히 건너뜀.
  4. Noto Sans KR 강제로 인한 줄바꿈 밀림 가능성.
  5. 한글 글꼴 이탤릭 글리프 부재로 인한 기울임 미감지.
  - **`pdf_docx.py`에는 있지만 여기 없는 한계**: "밑줄 오판 가능성"
    — 이 파일은 애초에 밑줄을 감지하지 않으므로 이 문제 자체가
    없다.

### 함수 본문

```python
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.enum.text import MSO_ANCHOR

EMU_PER_PT = 12700
image_dir = tmpdir / "_pdf_pptx_images"
layout = _extract_pdf_layout(src, image_dir)
if not layout:
    raise ConversionError("err.corrupted", "페이지 없음")

prs = Presentation()
prs.slide_width = Emu(round(layout[0]["width"] * EMU_PER_PT))
prs.slide_height = Emu(round(layout[0]["height"] * EMU_PER_PT))
blank_layout = prs.slide_layouts[6]
```

- `Presentation()`으로 빈 프레젠테이션을 만들고, 슬라이드 크기를
  **첫 페이지의 PDF 크기**에 맞춘다 — PPTX는 DOCX의 "섹션"같은
  개념이 없어서, `pdf_docx.py`처럼 페이지마다 크기가 다를 때 크기를
  다시 조정하는 로직이 없다(모든 슬라이드가 같은 캔버스 크기를
  공유하는 PPTX의 근본적 제약 — 페이지 크기가 섞인 PDF는 이 함수
  에서는 첫 페이지 기준으로 통일된다는 뜻, 이건 docstring에
  명시되진 않았지만 코드 구조상 드러나는 사실).
- `prs.slide_layouts[6]`: PowerPoint의 표준 레이아웃 목록에서
  인덱스 6은 관례적으로 "빈 화면"(Blank) 레이아웃이다 — 제목·
  내용 placeholder가 전혀 없는 완전히 빈 슬라이드에서 시작해야
  이후 좌표를 마음대로 배치할 수 있다.

### L50-74: 페이지→슬라이드 순회

```python
for page in layout:
    slide = prs.slides.add_slide(blank_layout)
    page_h = page["height"]
    for visual in page["visuals"]:
        _add_visual_to_slide(slide, visual, page_h, EMU_PER_PT)
    for line in page["lines"]:
        x0, y0, x1, y1 = line["bbox"]
        left = Emu(round(x0 * EMU_PER_PT))
        top = Emu(round((page_h - y1) * EMU_PER_PT))
        width = Emu(max(round((x1 - x0) * EMU_PER_PT), 1))
        height = Emu(max(round((y1 - y0) * EMU_PER_PT), 1))
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.TOP
        p = tf.paragraphs[0]
        for r in line["runs"]:
            run = p.add_run()
            run.text = r["text"]
            run.font.bold = r["bold"]
            run.font.italic = r["italic"]
            if r["size"]:
                run.font.size = Pt(r["size"])
            run.font.name = "Noto Sans KR"
```

- **한 페이지 = 한 슬라이드**(`prs.slides.add_slide(blank_layout)`).
- **도형이 텍스트보다 먼저** 그려진다(L53-54가 L55-74보다 앞) —
  `pdf_docx.py`와 같은 "배경 레이어" 순서.
- **좌표 변환은 `pdf_docx.py`와 동일한 원리**: `top = page_h - y1`
  (PDF의 "아래에서부터"와 PPTX의 "위에서부터" 좌표계 차이를 뒤집음),
  단위는 EMU(Emu 클래스는 python-pptx 전용이지만 `pdf_docx.py`의
  `docx.shared.Emu`와 같은 단위 체계 — 1pt=12700 EMU는 OOXML 공통
  표준).
- **PPTX는 python-docx보다 텍스트 상자 제어가 더 직접적이다**:
  `slide.shapes.add_textbox(left, top, width, height)`로 **정확히
  이 좌표에 이 크기의** 텍스트 상자를 만든다 — `pdf_docx.py`처럼
  "문단을 만들고 XML로 프레임 속성을 나중에 붙이는" 우회가 필요
  없다.
  - `tf.word_wrap = False`: 자동 줄바꿈 끔 — 이 앱은 이미 원본의
    각 줄을 정확한 위치·크기로 배치했으므로, PowerPoint가 자체
    판단으로 줄바꿈을 추가하면 위치가 어긋난다.
  - `margin_left/right/top/bottom = 0`: 텍스트 상자의 내부 여백을
    없애 텍스트가 상자 경계에 딱 맞게(원본 위치와 최대한 가깝게)
    배치되도록.
  - `vertical_anchor = MSO_ANCHOR.TOP`: 텍스트를 상자의 세로 중앙이
    아니라 **맨 위**에 붙인다 — 상자 높이가 정확히 원본 줄 높이로
    맞춰져 있으므로, 세로 정렬이 중앙이면 오히려 위치가 미묘하게
    어긋날 수 있다.
- **`pdf_docx.py`와 다른 점: `_apply_run_style`을 안 쓰고 직접
  설정**한다(L70-74) — `run.font.bold = r["bold"]`처럼 직접 대입.
  `pdf_docx.py`의 `_apply_run_style`은 `is not None` 체크로 구버전
  호환(값이 없으면 아무것도 안 건드림)까지 신경 썼는데, 이 파일은
  `_container_to_runs`가 항상 `bold`/`italic`을 `bool`로 채워서
  주므로(PDF 추출은 애초에 구버전 스키마가 없음 — PDF→PPTX는
  blocks JSON을 안 거치고 직접 만드는 경로) 그런 방어가 불필요하다.
  또한 **밑줄(`underline`)이나 색상(`color`)은 여기서 아예 설정
  안 함** — 이 함수가 `_container_to_runs`를 밑줄 세그먼트 없이
  호출하므로(`_extract_pdf_layout` L106) `underline`은 항상 False로
  오고, 애초에 반영할 코드도 없다.
  - `run.font.name = "Noto Sans KR"`: `docx_build.py`의 `_set_font`
    처럼 4개 OOXML 폰트 슬롯을 XML로 직접 건드리는 대신, python-pptx
    의 표준 API 한 줄로 끝난다 — PPTX(DrawingML)의 폰트 지정 방식이
    DOCX(WordprocessingML)보다 단순하다는 뜻(동아시아 폰트를 별도
    슬롯으로 구분하지 않음).

## L81-118: `_extract_pdf_layout` — 이 파일 전용 추출 (align/밑줄 없음)

```python
def _extract_pdf_layout(src, image_dir) -> list[dict]:
    ...
    for page in extract_pages(str(src)):
        lines = []
        for container in _paragraph_candidates(page):
            for line in _iter_lines(container):
                runs = _container_to_runs(line)
                if runs:
                    lines.append({"bbox": line.bbox, "runs": runs})
        visuals = [v for item in _iter_visuals(page)
                   if (v := _visual_to_dict(item, writer, image_dir)) is not None]
        pages.append({"width": page.width, "height": page.height, "lines": lines, "visuals": visuals})
    ...
```

- **`pdf_docx.py`의 `_extract_pdf_line_layout`과 비교하면 무엇이
  빠졌는가**: `_detect_alignment` 호출이 없고(정렬을 아예 계산 안
  함), `_underline_candidates`/`underline_segments` 전달이 없다
  (`_container_to_runs(line)`을 두 번째 인자 없이 호출 — 기본값
  `None`이라 항상 `underline=False`).
- **왜 정렬·밑줄을 다루지 않는가(docstring L89-91)**: "pdf_to_docx는
  정렬·밑줄까지 다뤄야 해서 이 함수 대신 `pdf_docx.py`의
  `_extract_pdf_line_layout()`을 쓴다" — 즉 **PPTX 텍스트 상자는
  이미 각 줄이 원본과 같은 위치에 있으므로, 정렬 정보가 굳이 필요
  없다**(정렬은 원래 "여러 줄이 흐를 때 어디에 맞출지"를 위한
  정보인데, 여기서는 이미 줄마다 위치가 확정돼 있어 무의미). 밑줄도
  PPTX 텍스트 상자 API에서 이 프로젝트가 아직 구현하지 않은 부분
  (범위 밖으로 남겨둔 것으로 보임).
- **왜 문단 단위로 합치는 `_extract_pdf_blocks_by_page`(pdf.py,
  HWP용)와도 다른가(docstring L82-84)**: 이 함수는 **줄 단위 위치
  (bbox)**가 꼭 필요하다(각 줄을 독립된 텍스트 상자로 만들어야
  하므로) — HWP용 함수는 흐르는 문서를 만들 뿐이라 줄 위치가 필요
  없이 문단 텍스트만 이어붙인다. 서식 판정 로직(`_container_to_runs`)
  자체는 셋 다 공유하지만, "결과를 어떻게 묶는지"가 소비자마다
  다르다.

## L121-182: `_add_visual_to_slide` — 도형 종류별 python-pptx API 사용

```python
def _add_visual_to_slide(slide, visual, page_h, emu_per_pt):
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Emu, Pt

    kind = visual["kind"]
    x0, y0, x1, y1 = visual["bbox"]

    if kind == "image":
        ...
        try:
            slide.shapes.add_picture(visual["path"], left, top, width, height)
        except Exception:
            pass
        return
    ...
```

- **이미지(L129-138)**: `slide.shapes.add_picture(...)`로 바로
  삽입. 실패하면(`except Exception: pass`) **아무것도 안 하고
  조용히 넘어간다** — `pdf_docx.py`가 "빈 문단을 만들었다가 실패
  시 지우는" 2단계 과정을 거쳤던 것과 달리, PPTX는 애초에 빈 셰이프를
  먼저 만들 필요가 없어(`add_picture`가 성공하면 그 자체로 완성된
  셰이프를 반환) 실패 시 지울 것 자체가 없다 — 더 단순한 처리가
  가능한 이유.

- **직선(L142-153) — `add_connector`(pdf_docx.py에 없는 개념)**:
  ```python
  conn = slide.shapes.add_connector(
      MSO_CONNECTOR.STRAIGHT,
      Emu(round(lx0 * emu_per_pt)), Emu(round((page_h - ly0) * emu_per_pt)),
      Emu(round(lx1 * emu_per_pt)), Emu(round((page_h - ly1) * emu_per_pt)),
  )
  if visual["stroke"]:
      conn.line.color.rgb = RGBColor(*visual["stroke"])
  conn.line.width = Pt(linewidth)
  ```
  PPTX는 "커넥터"(원래는 도형과 도형을 잇는 선을 위한 전용 셰이프
  타입)라는 API가 있어서, 시작점·끝점 좌표를 직접 지정해 진짜 직선
  하나를 만들 수 있다 — `pdf_docx.py`가 "문단 테두리로 선 하나를
  흉내 낸" 것과 달리, PPTX에서는 **선이 진짜 선 객체**로 표현된다.
  `RGBColor(*visual["stroke"])`: `stroke`가 `(r,g,b)` 튜플이므로
  `*`로 풀어서 `RGBColor(r, g, b)` 형태로 전달.

- **사각형(L155-160)**:
  ```python
  shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
  ```
  PowerPoint의 표준 도형 라이브러리에서 사각형 프리셋을 직접
  사용 — `pdf_docx.py`가 "문단 테두리 4변"으로 사각형을 흉내
  냈던 것과 달리, 여기서는 **진짜 사각형 셰이프**다.

- **곡선(L161-169) — `build_freeform`(자유형 도형)**:
  ```python
  pts = visual["pts"]
  if len(pts) < 2:
      return
  start_x, start_y = pts[0][0] * emu_per_pt, (page_h - pts[0][1]) * emu_per_pt
  fb = slide.shapes.build_freeform(start_x=start_x, start_y=start_y, scale=1.0)
  fb.add_line_segments(
      [(px * emu_per_pt, (page_h - py) * emu_per_pt) for px, py in pts[1:]], close=True)
  shape = fb.convert_to_shape()
  ```
  python-pptx의 `build_freeform`은 **임의의 다각형(자유형 도형)을
  점들을 이어서 만드는** API다 — 이게 바로 `pdf_docx.py`가 못 가진
  기능이다("pdf_docx.py의 알려진 한계 (1)"에서 언급된, python-docx엔
  이런 프리폼 API가 없어서 bounding box 사각형으로 더 단순하게
  근사할 수밖에 없었던 이유). 여기서는 원본 곡선의 제어점(`pts`)을
  순서대로 이어 **실제 다각형 모양**을 만든다(여전히 진짜 베지어
  곡선은 아니고 직선으로 이은 근사지만, `pdf_docx.py`의 bounding
  box보다는 원본에 훨씬 가깝다).
  - `first point`로 시작점을 지정하고, 나머지 점들을
    `add_line_segments(..., close=True)`로 이어 붙인 뒤 도형을
    닫는다(`close=True` — 마지막 점에서 시작점으로 자동으로
    이어져 닫힌 도형이 됨).
  - `fb.convert_to_shape()`로 빌더 객체를 실제 슬라이드 셰이프로
    확정.
  - `if len(pts) < 2: return`: 점이 1개 이하면 도형을 만들 수 없으므로
    그냥 건너뜀(방어적 처리).

- **L171-181: 채움·테두리 공통 적용(사각형·곡선만 해당, 직선은
  이미 return됨)**:
  ```python
  if visual.get("fill"):
      shape.fill.solid()
      shape.fill.fore_color.rgb = RGBColor(*visual["fill"])
  else:
      shape.fill.background()

  if visual.get("stroke"):
      shape.line.color.rgb = RGBColor(*visual["stroke"])
      shape.line.width = Pt(linewidth)
  else:
      shape.line.fill.background()
  ```
  - 채움 색이 있으면 `fill.solid()`로 단색 채움 모드를 켠 뒤 색을
    지정, 없으면 `fill.background()`로 **투명**(배경이 비쳐 보임)
    처리.
  - 테두리도 마찬가지 — 있으면 색·굵기 지정, 없으면
    `line.fill.background()`로 테두리 자체를 투명(안 보이게).
  - 이 "명시적으로 없음을 지정"하는 패턴이 중요한 이유: PowerPoint
    도형은 기본적으로 파란 테두리+채움 같은 **기본 스타일**을
    갖고 생성되므로, 원본 PDF에 채움/테두리가 없었다면 명시적으로
    꺼줘야 원본과 같은 모습이 된다(그냥 아무것도 안 하면 기본
    스타일이 남아 원본에 없던 색이 나타남).

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `pdf_docx.py`와 이 파일이 정확히 같은 문제(줄 단위 위치 재현)를
  풀면서도, 도형 표현 방식이 근본적으로 다른 이유는 무엇인가?
  (python-docx와 python-pptx의 API 차이와 연결해서 설명)
- `_extract_pdf_layout`이 정렬(align)과 밑줄을 다루지 않는 이유를,
  PPTX 텍스트 상자와 DOCX 흐르는 문단의 구조적 차이로 설명할 수
  있는가?
- `build_freeform`이 있는 PPTX와 없는 DOCX에서, 곡선(LTCurve)을
  각각 어떻게 다르게 근사하는가?
- 이미지 삽입 실패 시 `pdf_docx.py`는 "빈 문단을 만들고 실패하면
  지우는" 2단계를 거치는데, 이 파일은 왜 그럴 필요가 없는가?
- `shape.fill.background()`/`shape.line.fill.background()`를 명시적
  으로 호출하지 않으면 어떤 시각적 문제가 생기는가?
