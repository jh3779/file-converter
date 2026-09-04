# pdf.py — PDF 읽기 공유 프리미티브 + PDF→TXT/이미지

원본: `app/converters/pdf.py` (478줄, 가장 큰 컨버터 파일)

이 파일은 두 가지 역할을 겸한다: (1) `pdf_to_txt`·`pdf_to_images`처럼
그 자체로 완결된 변환 함수, (2) `pdf_docx.py`·`pdf_pptx.py`·`hwp.py`가
공유해서 쓰는 **저수준 PDF 파싱 함수 모음**(정렬 추정, 서식 감지, 도형
추출 등). 이 파일의 "밑줄로 시작하는" 함수들(`_iter_lines`,
`_container_to_runs` 등)이 사실상 이 프로젝트의 "PDF 텍스트 레이아웃
분석 엔진"이다.

---

## L1-10: 모듈 docstring — 이 파일의 역할 경계

"세 관심사가 원래 pdf.py 한 파일에 섞여 있었다"(L7)는 문구가 핵심 —
**2026-08 구조 감사**에서 PDF 저수준 파싱, DOCX 작성, PPTX 작성이 한
파일에 뒤섞여 있던 걸 발견하고 분리했다. 지금은:
- `pdf.py`: 저수준 추출(pdfminer 레이아웃 트리를 걷는 로직) + PDF→TXT/
  이미지처럼 이 파일 스스로 완결되는 변환.
- `pdf_docx.py`, `pdf_pptx.py`: 이 파일의 함수를 가져다 DOCX/PPTX
  고유의 출력 방식만 구현하는 "작성 어댑터".
- `_extract_pdf_blocks_by_page`(HWP 전용)도 세 번째 소비자로 이 파일에
  남는다 — DOCX/PPTX 어느 쪽에도 속하지 않기 때문.

이건 이 프로젝트의 구조 원칙(공유 로직은 한 곳에, 소비자별 차이만
각자 구현)을 pdf 계열 파일들이 어떻게 실현했는지 보여주는 사례다.

## L16-29: `pdf_to_txt`

```python
def pdf_to_txt(src: Path, tmpdir: Path) -> Path:
    from pdfminer.high_level import extract_text
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.psparser import PSException
    try:
        text = extract_text(str(src))
    except PDFPasswordIncorrect:
        raise ConversionError("err.password")
    except (PSException, ValueError, OSError) as e:
        raise ConversionError("err.corrupted", str(e))
    text = _fix_symbol_font_pua(text)
    out = tmpdir / (src.stem + ".txt")
    out.write_text(text, encoding="utf-8")
    return out
```

`pdfminer.high_level.extract_text`(pdfminer가 제공하는 가장 고수준의
"그냥 텍스트만 다오" API) 한 줄로 끝난다 — 이후 파일 전체에서 다루는
복잡한 레이아웃 분석은 **이 함수에는 필요 없다**(정렬·서식·페이지
경계가 전혀 중요하지 않은 단순 TXT 추출이므로). `PDFPasswordIncorrect`
(암호로 잠긴 PDF)는 `err.password`로, 나머지 파싱 오류는
`err.corrupted`로 나뉜다. `_fix_symbol_font_pua`(L345-349, 아래에서
설명)로 특수 기호 깨짐을 보정한다.

## L32-43: `_iter_lines(container)` — 컨테이너 → 줄 목록

```python
def _iter_lines(container):
    from pdfminer.layout import LTTextLine
    found_line = False
    for item in container:
        if isinstance(item, LTTextLine):
            found_line = True
            yield item
    if not found_line:
        yield container
```

- pdfminer의 레이아웃 트리에서, 일반적인 문단(`LTTextContainer`)은
  안에 `LTTextLine`(줄) 여러 개를 직계 자식으로 갖는다.
- 하지만 (아래 `_paragraph_candidates`가 설명하듯) 일부 컨테이너는
  줄로 안 묶이고 글자(`LTChar`)를 바로 담고 있다 — 이 경우
  `found_line`이 끝까지 `False`로 남고, **컨테이너 자체를 "줄 하나"
  처럼 취급**해서 넘겨준다(L42-43) — 호출자가 "이 컨테이너는 항상
  1개 이상의 줄을 낸다"고 가정할 수 있게 하는 방어적 설계.

## L46-134: 정렬 추정 — `_detect_alignment` + `_classify_alignment`

이 파일에서 가장 정교한 로직이다. PDF는 "이 문단은 가운데 정렬"이라는
정보를 담지 않는다 — 글자마다 절대 좌표만 있으므로, **좌표 패턴에서
정렬을 역산**해야 한다.

### L46: 허용 오차

```python
_ALIGN_TOL = 3.0  # pt — 글자 위치 반올림오차 허용치
```

좌표 비교를 완전히 정확하게(`==`) 하지 않고 3pt 오차를 허용한다 —
렌더링 과정의 반올림 오차를 감안한 값.

### L49-54: `_detect_alignment` — pdfminer 객체를 순수 데이터로 변환

```python
def _detect_alignment(container, page_width: float) -> str | None:
    boxes = [line.bbox for line in _iter_lines(container)]
    return _classify_alignment(boxes, page_width)
```

이 함수는 얇은 어댑터일 뿐이다 — pdfminer 컨테이너에서 줄별 `bbox`
(x0,y0,x1,y1 튜플)만 뽑아서, **실제 판정 로직인 `_classify_alignment`
(pdfminer에 전혀 의존하지 않는 순수 함수)에 넘긴다**. 이렇게 분리한
이유(L50-52)는 명확하다 — `_classify_alignment`는 손으로 만든
bbox 리스트로 직접 단위 테스트할 수 있다(실제 PDF 파일 없이도).

### L57-134: `_classify_alignment` — 순수 판정 로직 (재현된 버그 2건 포함)

**핵심 원칙(L63-67)**: 판단 근거가 약하면(짧은 문단, 애매한 여백)
**`None`을 반환해 정렬 정보 자체를 생략**한다 — 잘못 추정해서 원래
의도와 다른 정렬로 억지로 맞추는 것보다, "아무것도 안 해서 문서 기본
정렬을 유지"하는 게 안전하다는 원칙. 이 프로젝트 전체를 관통하는
"서식 불명 시 안전한 기본값"(DEC-027) 태도가 정렬 추정에도 적용된
것.

**한 줄짜리 문단(L99-107)**:
```python
if len(boxes) == 1:
    x0, _, x1, _ = boxes[0]
    left_margin = x0
    right_margin = page_width - x1
    if left_margin <= _ALIGN_TOL:
        return None
    if abs(left_margin - right_margin) <= _ALIGN_TOL * 2:
        return "center"
    return None
```
- 왼쪽 여백이 거의 없으면(페이지 왼쪽 끝에 붙어 있으면) 판단 근거
  부족으로 `None`.
- 좌우 여백이 거의 같으면(페이지 중심 기준 대칭) `"center"` — 이건
  **문서의 실제 여백 폭을 몰라도** 판단 가능한 유일한 케이스다
  (페이지 폭 중심만 알면 됨).
- **왜 오른쪽/왼쪽 정렬은 한 줄로는 절대 확정하지 않는가(주석
  L69-84, 실제 재현된 버그)**: "오른쪽 여백이 작다"는 사실이
  "문서의 실제 여백이 원래 좁아서"인지 "진짜 오른쪽 정렬이라서"
  인지 한 줄만 봐서는 구분할 수 없다. 처음엔 "오른쪽 확정 안 하니
  왼쪽으로 명시하자"로 짰었는데, 이러면 **한 줄짜리 진짜 오른쪽
  정렬**(날짜, 서명, 짧은 제목처럼 실사용 문서에 흔함)을 "left"로
  잘못 확정해버리는 반대 방향 오분류가 생겼다 — 이걸 자동 코드
  리뷰가 지적했고, `_classify_alignment([(400,700,540,712)], 612)`
  (왼쪽 여백 400, 오른쪽 여백 72 — 명백히 오른쪽에 가까운데도
  "left"가 나옴)로 재현까지 확인해서 지금의 "그냥 None(판단 보류)"
  으로 되돌렸다.

**여러 줄 문단(L109-134)**:
```python
lefts = [b[0] for b in boxes]
rights_body = [b[2] for b in boxes[:-1]]  # 마지막 줄 제외
left_consistent = (max(lefts) - min(lefts)) <= _ALIGN_TOL
right_consistent = len(rights_body) >= 2 and (max(rights_body) - min(rights_body)) <= _ALIGN_TOL

if left_consistent and right_consistent:
    return "justify"
if left_consistent:
    return "left"
if right_consistent:
    return "right"
centers = [(b[0] + b[2]) / 2 for b in boxes]
if max(centers) - min(centers) <= _ALIGN_TOL:
    return "center"
return None
```
- `rights_body = boxes[:-1]`(**마지막 줄 제외**) — 양쪽 정렬 문단도
  마지막 줄은 보통 짧다(문장이 거기서 끝나므로), 그래서 마지막 줄의
  오른쪽 끝은 정렬 판단에서 뺀다.
- `left_consistent`: 모든 줄의 왼쪽 끝이 오차범위 안에서 일치하는가.
- **`right_consistent`에 `len(rights_body) >= 2` 조건이 붙는 이유
  (또 다른 재현된 버그, L85-90)**: 2줄짜리 문단이면 `rights_body`가
  1개뿐이다 — "자기 자신과 비교"하면 항상 참(`max==min`)이 되어버려,
  평범한 2줄 왼쪽 정렬 문단이 "justify"(양쪽 정렬)로 잘못 분류되는
  버그가 있었다. `_classify_alignment([(72,700,300,712),
  (72,680,500,692)], 612)`(2줄, 왼쪽만 일치, 오른쪽 끝은 다름)로
  재현해서 확인했다 — 지금은 본문 줄이 2개 이상 있어야만 오른쪽/
  양쪽 판정을 시도하고, 부족하면 왼쪽/가운데만 확인한다("부족한
  근거로 확정하지 않는다"는 기본 원칙과 일관).
- 최종 판정 순서: 좌우 다 일치 → `"justify"`, 왼쪽만 일치 →
  `"left"`(명시적으로 반환하는 이유는 생략하면 HWP 기본값인 "양쪽
  정렬"로 해석되기 때문 — L128), 오른쪽만 일치 → `"right"`, 어느
  쪽도 아니면 각 줄의 중심(centers)이 일치하는지로 가운데 정렬만
  추가 확인.
- **알려진 한계(L118-125, 의도적으로 안 고침)**: 모든 줄의 폭이
  우연히 똑같은 가운데 정렬 문단은 좌우 끝이 둘 다 일치해버려
  `"justify"`로 잘못 나올 수 있다. "좌우 여백이 페이지 중심 기준
  대칭인지"를 추가 신호로 쓰면 이걸 고칠 수 있어 보이지만, 실제로
  검토해보니 **좌우 여백이 똑같은 흔한 진짜 양쪽 정렬 문서**(예:
  표준 1인치 여백)까지 가운데로 잘못 판정하는 더 나쁜 회귀가 생기는
  걸 확인해서 채택하지 않았다 — "희귀한 엣지 케이스 하나보다 흔한
  케이스를 안 깨뜨리는 쪽"을 명시적으로 택한 트레이드오프.

## L137-152: `_iter_visuals` — 이미지·벡터 도형 추출

```python
def _iter_visuals(container):
    from pdfminer.layout import LTContainer, LTCurve, LTImage
    for item in container:
        if isinstance(item, LTImage):
            yield item
        elif isinstance(item, LTCurve):
            yield item
        if isinstance(item, LTContainer):
            yield from _iter_visuals(item)
```

텍스트 추출(`_paragraph_candidates`)과는 **별개의 트리 순회**다.
`LTRect`·`LTLine`도 `LTCurve`의 하위 클래스라 `isinstance(item, LTCurve)`
하나로 셋 다 잡힌다. 왜 텍스트 순회와 합치지 않았는지(L138-142):
이미지는 보통 `LTFigure`(중첩된 컨테이너) 안에 있고, 선/사각형은
페이지 최상위에 바로 있는 경우가 많다는 걸 스파이크로 확인했다 —
"목적에 맞게 같은 트리를 두 번 걷는 게, 하나로 합쳐서 조건 분기를
복잡하게 만드는 것보다 단순하다"는 판단.

## L154-177: `_pdf_color_to_rgb` — PDF 색상값 → RGB 튜플

```python
def _pdf_color_to_rgb(color) -> tuple[int, int, int] | None:
    if color is None:
        return None
    try:
        if isinstance(color, (int, float)):
            v = round(color * 255)
            return (v, v, v)
        if isinstance(color, (list, tuple)):
            if len(color) == 3:
                return tuple(round(c * 255) for c in color)
            if len(color) == 4:
                c, m, y, k = color
                return (
                    round(255 * (1 - c) * (1 - k)),
                    round(255 * (1 - m) * (1 - k)),
                    round(255 * (1 - y) * (1 - k)),
                )
    except (TypeError, ValueError):
        pass
    return None
```

PDF는 색상을 3가지 방식으로 표현할 수 있다:
- **그레이스케일**(단일 float 0~1): 같은 값을 R=G=B로 복제 →
  회색조.
- **RGB**(3개 요소 0~1): 각각 255를 곱해 정수화.
- **CMYK**(4개 요소 0~1): 표준 CMYK→RGB 변환 공식
  (`R = 255×(1-C)×(1-K)` 등)을 적용.
- 이름 있는 색상(문자열)은 처리하지 않는다(주석 L156) — 실사용
  중 그런 경우를 못 봐서 범위 밖으로 뒀다. 어떤 이유로든 실패하면
  (타입이 예상과 다름 등) `None`을 반환하고, **호출자가 이걸
  "색상 정보 없음"(선/채움 없음 기본값)으로 처리**한다 — 색상 하나
  못 읽었다고 도형 자체가 유실되지는 않는다(방어적 설계).

## L180-200: `_visual_to_dict` — 도형 객체를 dict로 직렬화

```python
def _visual_to_dict(item, writer, image_dir: Path) -> dict | None:
    from pdfminer.layout import LTImage, LTLine, LTRect
    if isinstance(item, LTImage):
        try:
            name = writer.export_image(item)
        except Exception:
            return None
        return {"kind": "image", "bbox": item.bbox, "path": str(image_dir / name)}

    stroke = _pdf_color_to_rgb(item.stroking_color) if item.stroke else None
    fill = _pdf_color_to_rgb(item.non_stroking_color) if item.fill else None
    if isinstance(item, LTRect):
        return {"kind": "rect", "bbox": item.bbox, "stroke": stroke, "fill": fill,
                "linewidth": item.linewidth}
    if isinstance(item, LTLine):
        return {"kind": "line", "bbox": item.bbox, "p0": item.pts[0], "p1": item.pts[1],
                "stroke": stroke, "linewidth": item.linewidth}
    return {"kind": "curve", "bbox": item.bbox, "pts": list(item.pts),
            "stroke": stroke, "fill": fill, "linewidth": item.linewidth}
```

- `LTImage`(이미지)는 `writer.export_image(item)`(pdfminer의 이미지
  라이터, `pdf_docx.py`/`pdf_pptx.py`가 전달)로 실제 파일을 디스크에
  저장하고, 그 결과 파일명으로 경로를 만든다. 디코딩 실패(드문
  필터·손상 데이터)는 `None`을 반환해 **조용히 그 이미지 하나만
  건너뛴다**(전체 변환을 실패시키지 않음).
- `LTRect`(사각형): 선 색·채움 색·bbox·선 굵기.
- `LTLine`(직선): 시작점·끝점(`pts[0]`, `pts[1]`) + 색·굵기.
- 그 외 `LTCurve`(일반 곡선 — 사각형도 직선도 아닌 도형): 제어점
  전체(`pts`)를 담아 **직선으로 이은 다각형으로 근사**한다(주석
  L198) — 진짜 베지어 곡선을 그대로 재현하지는 않는다는 뜻.

## L203-248: `_extract_pdf_blocks_by_page` — HWP 전용, 페이지 경계 보존

```python
def _extract_pdf_blocks_by_page(src: Path) -> list[dict]:
    ...
    blocks = []
    try:
        for page_index, page in enumerate(extract_pages(str(src))):
            first_on_page = True
            for container in _paragraph_candidates(page):
                text = "".join(r["text"] for r in _container_to_runs(container))
                if not text.strip():
                    continue
                block = {"type": "p", "text": text}
                if page_index > 0 and first_on_page:
                    block["pageBreakBefore"] = True
                align = _detect_alignment(container, page.width)
                if align:
                    block["align"] = align
                blocks.append(block)
                first_on_page = False
    except PDFPasswordIncorrect:
        raise ConversionError("err.password")
    except (PSException, ValueError, OSError) as e:
        raise ConversionError("err.corrupted", str(e))
    return blocks
```

- **왜 이 함수가 필요한가(docstring L207-215)**: 예전엔 `pdf_to_txt`
  (`extract_text()`, 문서 전체를 한 문자열로)를 재사용해서 빈 줄
  기준으로만 문단을 나눴는데, `extract_text()`가 페이지 경계를
  표시하지 않아 **여러 페이지가 HWP 안에서 한 페이지처럼 이어붙어
  보였다**(외부 QA가 재현). 그래서 `extract_pages()`(페이지 단위
  제너레이터)로 직접 순회하도록 바뀌었다.
- **L223-243: 페이지·문단 이중 루프**:
  - `enumerate(extract_pages(...))`로 페이지 인덱스와 페이지 객체를
    얻는다.
  - `first_on_page = True`: 이 페이지에서 아직 "의미 있는 첫 문단"을
    못 만났다는 플래그.
  - 각 문단 후보(`_paragraph_candidates(page)`)에 대해:
    - `_container_to_runs`로 run들을 뽑아 텍스트만 이어붙인다(서식은
      이 경로에서 필요 없음).
    - **L227-235 (재현된 버그 방지)**: `if not text.strip(): continue`
      — 공백뿐인 컨테이너는 건너뛴다. 왜 중요한가: Java 쪽
      (`JsonToHwp.java`)도 `text.trim().isEmpty()`인 문단을 버리는데,
      만약 파이썬 쪽에서 공백뿐인 컨테이너를 "의미 있는 첫 문단"으로
      잘못 인정해서 `pageBreakBefore`를 거기 붙이면, 그 문단이 Java
      쪽에서 통째로 버려지면서 **실제 첫 문단에는 쪽 나눔이 반영
      안 되는 버그**가 생긴다(자동 코드 리뷰가 발견) — 그래서 두
      언어가 **같은 기준**(strip 후 빈 문자열인지)으로 걸러야 한다는
      게 중요.
    - `if page_index > 0 and first_on_page:` — 첫 페이지(index 0)는
      쪽 나눔이 필요 없다(이미 문서 첫 페이지니까). 두 번째 페이지
      부터, 그 페이지의 (공백 아닌) 첫 문단에만 `pageBreakBefore`
      마커를 붙인다.
    - `_detect_alignment`로 정렬도 함께 추정해서 있으면 붙인다.
    - `first_on_page = False`로 갱신해 같은 페이지의 다음 문단들은
      더 이상 마커를 안 받게 한다.

## L251-272: `_paragraph_candidates` — 숨겨진 텍스트까지 찾는 재귀 순회

```python
def _paragraph_candidates(obj):
    from pdfminer.layout import LTAnno, LTChar, LTContainer, LTTextContainer
    if isinstance(obj, LTTextContainer):
        yield obj
        return
    if isinstance(obj, LTContainer):
        if any(isinstance(c, (LTChar, LTAnno)) for c in obj):
            yield obj
        for child in obj:
            if not isinstance(child, (LTChar, LTAnno)):
                yield from _paragraph_candidates(child)
```

**해결하는 문제(docstring L254-260)**: 페이지 최상위 텍스트는
pdfminer가 이미 `LTTextContainer`(문단)로 잘 묶어준다. 하지만
`LTFigure`(Form XObject — 벡터 그래픽 등을 감싸는 컨테이너, 일부
PDF 생성기가 텍스트 박스를 이렇게 감싸기도 함) **내부**는 이 자동
묶음이 적용 안 돼서 `LTChar`가 그대로 흩어져 있다 — `extract_text()`
는 이 텍스트를 정상적으로 잡아내는데, `LTTextContainer`만 훑는 순회는
**조용히 놓친다**(코드 리뷰로 발견된 버그).

- **L264-266**: 이미 `LTTextContainer`(정상적으로 묶인 문단)면 그냥
  yield하고 끝 — 더 파고들지 않는다.
- **L267-269**: `LTContainer`(더 일반적인 컨테이너, `LTFigure` 포함)
  이면서 자식 중에 글자(`LTChar`/`LTAnno`)가 직접 있으면, **그
  컨테이너 자체를 "줄로 안 묶인 문단"으로 인정**해서 yield한다.
- **L270-272**: 글자가 아닌 자식들에 대해서는 재귀적으로 더 파고든다
  — 중첩된 `LTFigure` 안에 또 다른 `LTFigure`가 있어도 결국 텍스트를
  다 찾아낸다.

## L275-329: 밑줄 감지 — `_underline_candidates` + `_char_is_underlined`

밑줄은 PDF에서 **폰트 속성이 아니라 별도의 벡터 선(그림)**으로 그려지는
경우가 흔해서, 굵게/기울임처럼 폰트 이름 휴리스틱으로는 판별할 수 없다.
이 두 함수가 "텍스트 아래 그려진 선을 찾아서 밑줄로 인정"하는 로직이다.

### L275-277: 판정 상수

```python
_UNDERLINE_MAX_SLOPE_PT = 2.0  # 기울기 허용치
_UNDERLINE_MAX_GAP_PT = 4.0    # 글자 bbox와의 최대 거리
_UNDERLINE_MIN_OVERLAP_RATIO = 0.4  # 최소 겹침 비율
```

### L280-302: `_underline_candidates` — 밑줄 "후보" 선 추출

```python
def _underline_candidates(visuals: list[dict]) -> list[dict]:
    out = []
    for v in visuals:
        if v["kind"] != "line":
            continue
        (lx0, ly0), (lx1, ly1) = v["p0"], v["p1"]
        if abs(ly1 - ly0) > _UNDERLINE_MAX_SLOPE_PT:
            continue
        out.append({"x0": min(lx0, lx1), "x1": max(lx0, lx1), "y": (ly0 + ly1) / 2, "visual": v})
    return out
```

- `visuals`는 이미 `_visual_to_dict`로 뽑아둔 도형 목록(재사용 —
  이미지·표 테두리 개선 작업에서 만들어진 것).
- 선(`"line"`)만 보고, 거의 수평인 것만 후보로 삼는다(`abs(ly1-ly0)
  <= 2.0pt`) — 표 테두리의 대각선이나 다른 각도의 선은 애초에
  밑줄일 수 없으므로 제외.
- **아직 이 단계에서는 "표 테두리인지 진짜 밑줄인지" 구분하지
  않는다**(주석 L283-284) — 수평선이면 일단 다 후보에 넣고, 실제
  판정은 다음 함수(`_char_is_underlined`)에서 "텍스트 바로 아래에
  있는지"로 한 번 더 거른다.
- **`"visual": v`를 그대로 담아두는 이유(L286-289)**: 실제로 밑줄로
  "채택된" 선은, 원본 visual dict에 표시를 남겨서(아래 L327
  `seg["visual"]["_used_as_underline"] = True`) `pdf_docx.py`가
  나중에 그 선을 **표 테두리 도형으로 중복 렌더링하지 않게**
  한다 — 밑줄은 이미 run의 `underline=True`로 반영되므로, 같은
  선을 도형으로도 또 그리면 겹쳐 보인다.
- **왜 이 DOCX 전용 로직이 `pdf.py`에 있는가(L290-293)**: 실제
  호출자는 `pdf_docx.py`뿐이지만, `_char_is_underlined`를 직접
  호출하는 `_container_to_runs`(이 파일)와 짝을 이루므로, 순환
  import(`pdf_docx.py`가 `pdf.py`를 import하고, `pdf.py`가 다시
  `pdf_docx.py`를 import하는 것)를 피하려고 이 공유 모듈에 뒀다.

### L305-329: `_char_is_underlined` — 글자 하나가 밑줄 위에 있는지 판정

```python
def _char_is_underlined(ch, segments: list[dict]) -> bool:
    x0, y0, x1, y1 = ch.bbox
    mid_y = (y0 + y1) / 2
    for seg in segments:
        seg_x0, seg_x1, seg_y = seg["x0"], seg["x1"], seg["y"]
        if seg_y > mid_y:
            continue
        if y0 - seg_y > _UNDERLINE_MAX_GAP_PT:
            continue
        overlap = min(x1, seg_x1) - max(x0, seg_x0)
        if overlap > 0 and overlap >= (x1 - x0) * _UNDERLINE_MIN_OVERLAP_RATIO:
            seg["visual"]["_used_as_underline"] = True
            return True
    return False
```

- **기준점이 bbox 중간이 아니라 아래쪽 끝(y0)인 이유(docstring
  L307-311)**: pdfminer가 표준 14 폰트(Helvetica 등)의 glyph bbox를
  **실제 잉크(글자가 실제로 차지하는 픽셀) 범위가 아니라 폰트
  자체의 ascent/descent(글꼴 디자인상의 상하 여백)로 균일하게
  매긴다**는 걸 직접 검증해서 확인했다 — 그래서 `y0`가 대략
  "폰트 디센트 라인"(베이스라인보다 살짝 아래)과 비슷한 위치가
  된다. 실제 밑줄은 베이스라인 바로 아래에 그려지므로, `y0` 근방
  (살짝 위아래 허용)에 있는 선을 찾는 게 맞다.
- **L321-322**: 선의 y좌표가 글자 세로 중앙(`mid_y`)보다 **위**에
  있으면 건너뛴다 — 그건 밑줄이 아니라 취소선(strikethrough)일
  가능성이 높다.
- **L323-324**: 글자 bbox 아래쪽 끝(`y0`)에서 선까지의 거리가
  4pt(`_UNDERLINE_MAX_GAP_PT`)를 넘으면, 너무 멀리 떨어진(다른
  용도의) 선으로 보고 건너뛴다.
- **L325-326**: 가로 방향 겹침(`overlap`)을 계산해서, 글자 폭의
  40%(`_UNDERLINE_MIN_OVERLAP_RATIO`) 이상 겹쳐야 진짜 밑줄로
  인정한다 — 완전히 안 겹치거나 살짝만 스치는 선은 제외.
- **L327-328**: 조건을 통과하면 그 선의 원본 dict에
  `"_used_as_underline"` 표시를 남기고(위에서 설명한 중복 렌더링
  방지용) `True`를 반환.

## L332-349: 심볼 폰트 PUA(사설 영역) 보정

```python
_SYMBOL_FONT_PUA_MAP = {
    "": "•",
}

def _fix_symbol_font_pua(text: str) -> str:
    for pua, real in _SYMBOL_FONT_PUA_MAP.items():
        if pua in text:
            text = text.replace(pua, real)
    return text
```

**아주 구체적인 실무 버그 보정(주석 L332-339)**: LibreOffice/Word가
목록 기호(불릿)를 그릴 때 "Symbol" 글꼴을 쓰고, 그 서브셋 폰트가
"Microsoft Symbol" cmap 관례를 따라 문자 코드를 `0xF000+원래코드`
(유니코드 사설 영역, PUA)로 인코딩하는 경우가 실제로 관찰됐다 — 예:
Word의 "List Bullet" 스타일이 서브셋 폰트의 `0xB7`(bullet 기호)을
`U+F0B7`로 PDF에 내보낸다. pdfminer는 이 PUA 코드를 그대로 넘기는데,
원본 폰트가 없는 뷰어(Word/Google Docs 등)에서는 이게 빈 네모(tofu)로
보인다. Adobe Symbol 인코딩은 어느 환경에서도 동일한 표준이므로,
알려진 코드만 안전하게 원래 유니코드 기호(`•`)로 되돌린다.
`pdf_to_txt`와 `_container_to_runs`(아래) 둘 다 이 보정을 쓴다.

## L352-363: `_iter_chars` — 줄/컨테이너에서 글자를 순서대로 뽑기

`_iter_lines`와 비슷하지만, 이번엔 "줄(LTTextLine) 안의 글자들"까지
파고든다. `LTTextLine`을 만나면 재귀 호출로 더 들어가고, 글자
(`LTChar`/`LTAnno`)를 만나면 바로 yield한다 — 문단이든 줄로 안 묶인
컨테이너든 최종적으로 모든 글자를 순서대로 얻을 수 있다.

## L365-435: `_container_to_runs` — 서식이 바뀌는 지점마다 run 분리 (핵심 로직)

이 파일에서 `pdf_docx.py`/`pdf_pptx.py`가 가장 많이 의존하는 함수다.
"컨테이너(문단)를 글자 단위로 훑어서, 굵게/기울임/크기/밑줄 중 **하나
라도** 바뀌면 새 run을 시작"한다.

**서식 감지의 근본적 한계(docstring L369-380)**: PDF에 "이 글자가
굵다"는 명시적 플래그가 없다 — pdfminer가 알려주는 폰트 리소스
이름(`LTChar.fontname`, 예: `"Caladea-Bold"`)에 `"Bold"`/`"Italic"`/
`"Oblique"` 문자열이 포함되는지 보는 **휴리스틱**일 뿐이다. 검증
결과:
- 이 휴리스틱은 **굵기별로 폰트 파일이 실제로 분리돼 있을 때만**
  정확하다(한글 폰트 포함 — `NotoSansKR-Bold`, `AppleSDGothicNeo-Bold`
  등, 실사용 문서 대부분이 이런 식으로 폰트를 씀).
- 한계 (1): 문서에 동아시아 글꼴을 명시하지 않아 렌더러가 임의의
  대체 글꼴 하나로 뭉뚱그려 그리면, 애초에 굵기 정보 자체가 사라져
  감지 불가.
- 한계 (2): 기울임은 한글 글꼴 대부분에 별도 이탤릭 글리프가 없어서
  (CJK 타이포그래피 관행) 렌더러가 아예 반영을 안 하는 경우가 흔함
  — 이건 우리 휴리스틱의 실패가 아니라 **원본 자체에 감지할 서식이
  없는** 것.

**밑줄 감지의 별도 경로(L382-392)**: 밑줄은 폰트 이름 휴리스틱으로
원천적으로 판별 불가(별도 벡터 선이니까) — `underline_segments`
파라미터(호출자가 `_underline_candidates`로 미리 만들어 넘김)가
있을 때만 `_char_is_underlined`로 판정한다. 넘기지 않으면(기본값
`None`, `pdf_pptx.py`나 `pdf_to_hwp` 등 밑줄 판정이 필요 없는 호출자)
**항상 `underline=False`**로 처리해 매 글자마다 선 목록을 대조하는
비용을 아낀다.

### 함수 본문 상세

```python
def _container_to_runs(container, underline_segments=None) -> list[dict]:
    from pdfminer.layout import LTChar
    runs = []
    cur_text = []
    cur_style = (False, False, None, False)

    def flush():
        if cur_text:
            bold, italic, size, underline = cur_style
            runs.append({"text": "".join(cur_text), "bold": bool(bold),
                         "italic": bool(italic), "underline": bool(underline),
                         "size": size, "color": None})

    for ch in _iter_chars(container):
        if isinstance(ch, LTChar):
            fontname = ch.fontname.lower()
            underline = (_char_is_underlined(ch, underline_segments)
                         if underline_segments else False)
            style = ("bold" in fontname, "italic" in fontname or "oblique" in fontname,
                     round(ch.size, 1), underline)
            text = _fix_symbol_font_pua(ch.get_text())
        else:
            text = ch.get_text()
            text = " " if text == "\n" else text
            style = cur_style

        if style != cur_style and cur_text:
            flush()
            cur_text = []
        cur_style = style
        cur_text.append(text)
    flush()

    if runs:
        runs[0]["text"] = runs[0]["text"].lstrip()
        runs[-1]["text"] = runs[-1]["text"].rstrip()
        runs = [r for r in runs if r["text"]]
    return runs
```

- **L398**: `cur_style = (bold, italic, size, underline)` 튜플 — 이
  4개 값 **중 하나라도 바뀌면** 새 run을 시작한다는 게 이 함수의
  핵심 알고리즘.
- **L400-405: `flush()` 클로저**: 지금까지 모은 텍스트(`cur_text`)를
  하나의 run으로 확정해 `runs` 리스트에 추가한다. 클로저로 정의된
  이유는 `cur_text`, `cur_style`(바깥 함수의 지역 변수)를 캡처해서
  쓰기 때문 — 파이썬에서 흔한 "누적하다가 조건에 따라 커밋" 패턴.
- **L407-422: 글자별 순회, 두 갈래**:
  - `LTChar`(실제 폰트 정보가 있는 글자)면: 폰트 이름에서 굵게/
    기울임을 감지하고, 밑줄 세그먼트가 주어졌으면 판정하고, 글자
    크기를 소수점 1자리로 반올림해서 스타일 튜플을 만든다.
    텍스트는 심볼 폰트 PUA 보정을 거친다.
  - 그 외(`LTAnno` — 가상 문자, 줄바꿈·자간 보정용, 폰트 정보 없음)
    면: **현재 스타일을 그대로 유지**(`style = cur_style`, 서식
    전환을 트리거하지 않음)한다. PDF의 줄바꿈은 문단 내부 개행일
    뿐이므로(문단 경계는 이미 컨테이너 단위로 나뉨) `"\n"`을 공백
    하나로 정규화한다(L421).
- **L424-428**: 스타일이 바뀌었고 지금까지 모은 텍스트가 있으면
  `flush()`로 확정하고 새로 시작. 매 글자마다 이 비교를 하므로,
  스타일이 안 바뀌는 한 계속 같은 run에 텍스트가 누적된다.
- **L429**: 루프가 끝난 뒤 마지막으로 남은 텍스트도 `flush()`.
- **L431-434: 후처리**: 첫 run의 텍스트 앞쪽 공백을 지우고
  (`lstrip()`), 마지막 run의 뒤쪽 공백을 지우고(`rstrip()`), 그
  결과 빈 문자열이 된 run은 걸러낸다 — 문단 시작·끝의 불필요한
  공백을 정리하되, **run 내부(문단 중간)의 공백은 건드리지 않는다**
  (이게 `docx_build.py`에서도 봤던 "문단 경계 공백은 정리, 내부
  공백은 보존" 원칙과 같은 태도).

## L438-478: `pdf_to_images` — PDF → 페이지별 PNG/JPG

```python
_PDF_IMAGE_PILLOW_FORMAT = {"png": "PNG", "jpg": "JPEG"}

def pdf_to_images(src: Path, tmpdir: Path, ext: str = "png") -> Path:
    import pypdfium2 as pdfium
    fmt = _PDF_IMAGE_PILLOW_FORMAT[ext]
    try:
        doc = pdfium.PdfDocument(src)
    except pdfium.PdfiumError as e:
        key = "err.password" if "password" in str(e).lower() else "err.corrupted"
        raise ConversionError(key, str(e))
    try:
        n_pages = len(doc)
        if n_pages == 0:
            raise ConversionError("err.corrupted", "페이지 없음")
        out_dir = tmpdir / src.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        width = len(str(n_pages))
        for i, page in enumerate(doc, start=1):
            bitmap = page.render(scale=2.0)
            try:
                bitmap.to_pil().save(out_dir / f"page_{i:0{width}d}.{ext}", format=fmt)
            finally:
                bitmap.close()
                page.close()
        return out_dir
    finally:
        doc.close()
```

- **왜 pypdfium2인가(docstring L445-447)**: LibreOffice의
  `--convert-to png`는 **다중 페이지 PDF에서 첫 페이지 1장만
  내보낸다**는 걸 직접 확인해서 채택하지 않았다 — 대신 Apache-2.0/
  BSD-3-Clause(허용적 라이선스)인 `pypdfium2`(Google의 PDFium
  엔진에 대한 Python 바인딩)를 쓴다.
- **알파 채널 처리가 필요 없는 이유(L448-450)**: `bitmap.to_pil()`
  (pypdfium2가 렌더링한 결과를 Pillow 이미지로 변환)은 항상 알파
  채널 없는 순수 RGB라는 걸 직접 확인했다 — `image.py`(다른 이미지
  변환)처럼 투명 배경을 흰색으로 합성하는 처리가 여기서는 필요
  없다.
- **반환값이 폴더라는 특이점(L452-453)**: 다른 모든 컨버터 함수는
  파일 경로 하나를 반환하는데, 이 함수만 **폴더 경로**를 반환한다
  (여러 페이지 이미지를 그 안에 담아서). `app/output.py`의
  `finalize()`가 이 반환값이 파일인지 폴더인지 자동 판단해서 처리
  방식을 바꾼다.
- **L456**: `ext`("png" 또는 "jpg")를 Pillow 포맷 이름으로 변환.
- **L458-461**: 문서 열기 실패 시, 에러 메시지에 `"password"`가
  있는지로 암호 잠금과 일반 손상을 구분(다른 파일들과 같은 패턴).
- **L466-468**: 결과를 담을 폴더를 원본 파일명(`src.stem`)으로
  만든다. `width = len(str(n_pages))`로 페이지 번호의 자릿수를
  계산 — 예를 들어 총 12페이지면 `width=2`, 총 120페이지면
  `width=3`.
- **L469-475: 페이지별 렌더링 루프**:
  - `page.render(scale=2.0)` — 실제 화면 표시 배율의 2배로 렌더링
    (PDF 좌표 단위 1pt=1/72인치를 2배 확대 → 대략 144 DPI 수준).
  - `f"page_{i:0{width}d}.{ext}"` — 파일명에 0으로 패딩된 번호를
    붙인다(예: `page_01.png`, `page_02.png`, ..., `page_12.png`) —
    이렇게 해야 파일 탐색기에서 정렬했을 때 `page_10`이
    `page_2`보다 뒤에 오는(문자열 정렬의 함정) 문제가 안 생긴다.
  - `try/finally`로 `bitmap.close()`, `page.close()`를 확실히
    호출한다 — pypdfium2의 네이티브 리소스(PDFium 엔진이 관리하는
    C 레벨 객체)를 매 페이지마다 명시적으로 해제해야 메모리가
    누적되지 않는다(대용량 PDF에서 특히 중요).
- **L477-478**: 바깥쪽 `finally`로 `doc.close()`도 확실히 호출 —
  문서 자체의 리소스도 정리.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_classify_alignment`가 한 줄짜리 문단에서 오른쪽 정렬을 절대
  확정하지 않는 이유를 구체적인 재현 사례로 설명할 수 있는가?
- `right_consistent` 계산에 `len(rights_body) >= 2` 조건이 없다면
  정확히 어떤 입력에서 어떤 잘못된 결과가 나오는가?
- `_char_is_underlined`가 글자 bbox의 중간이 아니라 아래쪽 끝을
  기준점으로 쓰는 이유는? pdfminer의 폰트 렌더링 특성과 어떤 관계가
  있는가?
- `_container_to_runs`에서 `LTAnno`를 만났을 때 스타일 전환이
  트리거되지 않는 이유는? 만약 트리거된다면 어떤 부작용이 생길까?
- `pdf_to_images`가 다른 모든 컨버터 함수와 다르게 폴더를 반환하는데,
  `app/output.py`의 `finalize()`는 이걸 어떻게 다르게 처리하는가?
  (`output.py`의 code-notes에서 확인 가능)
