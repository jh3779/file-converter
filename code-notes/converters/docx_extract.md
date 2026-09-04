# docx_extract.py — DOCX → "구조 블록" (docx_build.py의 역방향)

원본: `app/converters/docx_extract.py` (413줄)

`docx_build.py`가 "blocks JSON → DOCX"였다면, 이 파일은 정확히 반대
방향("DOCX → blocks JSON")이다. `hwp.py`의 `docx_to_hwp`, `hwpx.py`의
`docx_to_hwpx`가 이 파일의 `docx_to_blocks()`를 호출한다. 이 파일이
`docx_build.py`보다 더 복잡한 이유: **"만들기"는 스키마대로 순서대로
쓰면 되지만, "읽어내기"는 DOCX(OOXML)의 다양한 특수 사례(하이퍼링크,
스타일 상속, 자동 번호, 셀 병합 감지)를 전부 다뤄야 한다.**

---

## L1-52: 모듈 docstring — 이 파일이 다루는 6가지 특수 사례

- **블록 스키마(L3-8)**: `docx_build.py`와 같은 스키마를 정본으로
  삼는다. 특히 중요한 문장(L6-8): python-docx는
  `document.paragraphs`와 `document.tables`를 **각각 따로** 준다
  (문서에 등장하는 순서가 섞여서 나오지 않음) — 그래서 body XML을
  직접 순회해야 "문단1, 표1, 문단2, 표2..." 같은 실제 문서 순서를
  보존할 수 있다(→ `_iter_block_items`, L361-372).
- **문자 서식(L10-14, DEC-038)**: `run.bold`/`italic`/`underline`이
  `None`이면(스타일에서 상속받았을 뿐 직접 지정은 없음) "미지정"으로
  보고 `False`로 안전하게 처리한다 — 스타일 상속 체인 전체를 해석
  하지는 않는다는 단순화.
- **표 셀 서식(L15-21, DEC-051)**: 셀 안에 문단이 여러 개면(흔치
  않지만 가능) 공백 하나로 이어붙인다 — HWP 표 셀은 항상 단일
  문단이라는 전제와 대칭을 맞추기 위해서(`JsonToHwp.java`의
  `setParagraphForCell`).
- **문단 정렬(L23-29, DEC-040) — 실제 재현된 버그**: 정렬이 직접
  지정 안 됐으면(스타일 상속은 범위 밖) 예전엔 `"align"` 필드
  자체를 생략했다. 그런데 HWP 쪽(`JsonToHwp.java`)이 "정렬 필드가
  없음"을 **HWP 문서 기본값인 "양쪽 정렬"**로 해석해버려서, 평범한
  (정렬 미지정) DOCX 문단이 죄다 양쪽 정렬로 둔갑하는 회귀가 있었다
  — 자동 코드 리뷰가 발견, 실제 왕복 변환으로 재현 확인. 지금은
  정렬이 없으면 **Word가 실제로 렌더링하는 값인 `"left"`를 명시적으로
  채운다**.
- **표 셀 병합·열 너비(L31-40, DEC-035)**: python-docx의
  `table.cell(r, c)`는 병합된 영역의 **모든 그리드 위치에서 같은
  내부 XML 객체(`_tc`)를 돌려준다**는 걸 직접 만든 병합 DOCX로 실측
  확인했다 — 이 "객체 동일성"으로 병합 여부를 감지한다(→
  `_table_rows_with_spans`, L324-358).
- **번호·불릿 목록(L42-52)**: DOCX의 자동 번호("1.", "가.")·불릿
  ("•")은 `w:t`(실제 텍스트)가 아니라 `numbering.xml`이라는 별도
  서식 파일에 정의돼 있고 **뷰어가 화면에만 그려준다** — 코드
  리뷰에서 이걸 놓치면 마커가 조용히 사라진다는 게 지적·재현됐다.
  숫자/로마자/알파벳/불릿 서식은 numbering.xml을 직접 해석해서
  마커 문자열을 만들어 문단 맨 앞에 붙인다. 다단계 중첩 목록의
  "상위 레벨 변경 시 하위 레벨 재시작" 같은 OOXML 규칙 전체까지는
  재현하지 않는다(문서화된 단순화 — `(numId, ilvl)` 쌍별로 단순
  증가하는 카운터만 씀).

## L56-99: 번호 매기기 값 생성 — 로마자·알파벳 변환 + 마커 포맷

```python
def _to_roman(n: int) -> str:
    out = []
    for value, symbol in _ROMAN_VALUES:
        count, n = divmod(n, value)
        out.append(symbol * count)
    return "".join(out)

def _to_letter(n: int) -> str:
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("a") + rem))
    return "".join(reversed(letters))
```

- `_to_roman`: 표준 "그리디 알고리즘"으로 정수를 로마 숫자로 변환
  — `_ROMAN_VALUES`(L56-60)가 큰 값부터 정렬돼 있어, 각 값으로 나눈
  몫만큼 그 기호를 반복하고 나머지로 다음 값을 시도한다(예:
  `divmod(1994, 1000)` → `(1, 994)`, `M` 1개 추가하고 994 계속 처리).
- `_to_letter`: 정수를 엑셀 열 이름 같은 알파벳 시퀀스로 변환
  (1→a, 2→b, ..., 26→z, 27→aa, ...). `n - 1`을 26으로 나누는 이유:
  0-indexed alphabet(a=0)로 다루기 위한 보정 — 26진법과 비슷하지만
  "0"에 해당하는 표기가 없는(z 다음이 aa이지 a0이 아닌) 특수한
  진법 변환이라 `n-1` 보정이 필요하다.
- **L79-99: `_format_marker`** — numFmt(서식 종류 문자열)에 따라
  분기해서 값을 만들고, `lvltext`(예: `"%1."`, `"(%1)"`처럼 `%숫자`
  자리에 값을 끼워 넣는 템플릿)가 있으면 `re.sub(r"%\d+", value,
  lvltext, count=1)`로 **첫 번째** `%숫자` 패턴만 그 값으로 치환한다.
  지원하지 않는 서식(`else: return None`, L94-95)이면 마커 자체를
  생략(본문 텍스트는 그대로 유지) — "지원 안 하는 서식이라고 텍스트
  까지 날리지 않는다"는 원칙.

## L102-138: `_numbering_levels` — numbering.xml 파싱

```python
def _numbering_levels(document):
    from docx.oxml.ns import qn
    try:
        numbering_el = document.part.numbering_part.element
    except Exception:
        return {}
    ...
```

- **L106-109**: `numbering_part`가 없는 문서(자동 번호를 아예 안
  쓰는 문서)도 많으므로, 접근 실패 시 빈 dict를 반환해 이후 코드가
  자연스럽게 "번호 없음"으로 처리하게 한다.
- **L111-127: 1단계 — abstractNum 파싱**. OOXML의 numbering.xml은
  2단계 구조다: `w:abstractNum`(번호 매기기의 "정의", 레벨별 서식)과
  `w:num`(실제 문서에서 참조하는 "인스턴스", 어떤 abstractNum을
  쓸지 지정). 이 블록은 모든 `abstractNum`을 순회하며, 각각의
  `abstractNumId`를 키로, 그 안의 각 레벨(`w:lvl`, `ilvl`로 구분)의
  `(numFmt, lvlText, start)` 튜플을 값으로 만든다. 서식 요소가
  없으면 기본값(`"decimal"`, `"%1."`, `1`)을 쓴다.
- **L129-138: 2단계 — num→abstractNum 매핑**. `w:num` 요소는
  `numId`(문서에서 실제로 참조하는 값)와 그게 가리키는
  `abstractNumId`를 담고 있다. 이 매핑을 따라가서, 최종적으로
  `{numId: {ilvl: (numFmt, lvlText, start)}}` 형태의 결과를 만든다
  — 문단이 "이 numId, 이 레벨"이라고 하면 바로 이 dict에서 서식
  정보를 찾을 수 있다.

## L141-170: `_paragraph_numpr` — 문단이 어떤 번호 매기기를 쓰는지 찾기

```python
def _paragraph_numpr(paragraph):
    ppr = paragraph._p.find(qn("w:pPr"))
    numpr = ppr.find(qn("w:numPr")) if ppr is not None else None
    if numpr is None:
        style = paragraph.style
        seen = set()
        while style is not None and id(style) not in seen:
            seen.add(id(style))
            style_ppr = style.element.find(qn("w:pPr"))
            if style_ppr is not None:
                numpr = style_ppr.find(qn("w:numPr"))
                if numpr is not None:
                    break
            style = getattr(style, "base_style", None)
    ...
```

- **L147-148**: 먼저 문단 자체에 직접 `w:numPr`(번호 매기기 속성)이
  있는지 본다.
- **L149-159: 스타일 체인을 거슬러 올라가는 탐색**: 직접 지정이
  없으면, 이 문단의 스타일(예: "List Number", "List Bullet" 같은
  Word 내장 스타일)을 확인한다. 주석(L143-144)이 설명하듯, 이런
  내장 스타일은 **번호 매기기 속성이 문단이 아니라 스타일 자체에**
  붙어 있다는 걸 실제 생성 DOCX로 확인했다. `while style is not None
  and id(style) not in seen:`으로 **스타일 상속 체인**(어떤 스타일이
  다른 스타일을 기반으로 할 수 있음, `base_style`)을 따라 올라가며
  찾는다. `seen` 집합으로 순환 참조(스타일 A가 B를 상속하고 B가
  다시 A를 상속하는 등, 이론상 있을 수 있는 잘못된 문서)에 빠지지
  않게 방어한다.
- **L166-169**: `numId`가 `"0"`이면 **"목록 아님"(번호 제거)을 뜻하는
  예약값**이라 무시한다(Word는 "이 문단은 번호 목록에서 빠져라"는
  걸 numId=0으로 표현하는 관례가 있다).
- 반환값은 `(num_id, ilvl)` 문자열 쌍 또는 `None`.

## L173-211: 정렬 읽기 — `_align_to_str_map` + `_paragraph_align`

```python
_ALIGN_TO_STR = None

def _align_to_str_map():
    global _ALIGN_TO_STR
    if _ALIGN_TO_STR is None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        _ALIGN_TO_STR = {
            WD_ALIGN_PARAGRAPH.LEFT: "left",
            ...
            WD_ALIGN_PARAGRAPH.JUSTIFY_MED: "justify",
            WD_ALIGN_PARAGRAPH.JUSTIFY_HI: "justify",
            WD_ALIGN_PARAGRAPH.JUSTIFY_LOW: "justify",
            WD_ALIGN_PARAGRAPH.DISTRIBUTE: "justify",
            WD_ALIGN_PARAGRAPH.THAI_JUSTIFY: "justify",
        }
    return _ALIGN_TO_STR
```

- `docx_build.py`의 `_align_map()`(문자열→enum)의 **정반대 방향**
  (enum→문자열) — 같은 지연 초기화 패턴.
- **주석(L177-180)에 남은 자동 리뷰 지적**: 딕셔너리 키를
  `WD_ALIGN_PARAGRAPH.LEFT.name`(문자열 `"LEFT"`) 같은 문자열
  비교가 아니라 **enum 값 자체**로 쓴다 — python-docx의 내부 문자열
  표현이 라이브러리 버전에 따라 바뀔 수 있는데, enum 객체 자체를
  키로 쓰면 그런 변화에 안전하다.
- 여러 개의 "양쪽 정렬 계열" enum(`JUSTIFY`, `JUSTIFY_MED`,
  `JUSTIFY_HI`, `JUSTIFY_LOW`, `DISTRIBUTE`, `THAI_JUSTIFY`)이 전부
  `"justify"` 하나로 뭉뚱그려진다 — 이 프로젝트가 다루는 blocks
  스키마는 4가지 정렬만 표현하므로(left/center/right/justify), 세부
  variant는 구분하지 않는다.

```python
def _paragraph_align(paragraph) -> str | None:
    alignment = paragraph.alignment
    if alignment is None:
        return "left"
    return _align_to_str_map().get(alignment)
```

- 이 함수가 `docx_build.py`의 docstring에서 언급했던 "회귀"를 고친
  코드다: `alignment is None`(정렬 미지정)일 때 예전에는 `None`을
  반환해서 blocks JSON에 `"align"` 필드 자체가 안 실렸는데, 지금은
  **명시적으로 `"left"`**를 반환한다.

## L214-232: `_run_to_dict` — run 하나를 dict로

```python
def _run_to_dict(run) -> dict | None:
    if not run.text:
        return None
    size = run.font.size
    color = None
    try:
        rgb = run.font.color.rgb if run.font.color is not None else None
        if rgb is not None:
            color = str(rgb)
    except Exception:
        pass
    return {
        "text": run.text,
        "bold": bool(run.bold),
        "italic": bool(run.italic),
        "underline": bool(run.underline),
        "size": (size.pt if size is not None else None),
        "color": color,
    }
```

- 텍스트가 없는 run(예: 필드 코드 전용)은 `None`을 반환해 걸러낸다.
- `bool(run.bold)`: `run.bold`가 `True`/`False`/`None` 중 하나일 수
  있는데, `bool(None) == False`이므로 이 한 줄이 "None이면 False로
  안전 처리"(docstring L10-14의 원칙)를 자동으로 구현한다.
- **L219-224: 색상 읽기의 방어**: `run.font.color.rgb`가 항상 성공
  하는 게 아니다 — **테마 색상**(Word의 "강조 1" 같은 팔레트 참조,
  구체적인 RGB 값이 아니라 테마 참조로 저장됨)처럼 RGB로 안 떨어지는
  경우가 있어서, `try/except Exception: pass`로 감싸 실패하면
  그냥 색상 미지정(`None`)으로 처리한다.

## L235-254: `_paragraph_runs` — 하이퍼링크 안 run까지 펼치기 (재현된 버그)

```python
def _paragraph_runs(paragraph) -> list[dict]:
    from docx.text.hyperlink import Hyperlink
    from docx.text.run import Run
    runs = []
    for item in paragraph.iter_inner_content():
        inner_runs = item.runs if isinstance(item, Hyperlink) else [item] if isinstance(item, Run) else []
        for run in inner_runs:
            d = _run_to_dict(run)
            if d is not None:
                runs.append(d)
    return runs
```

**해결하는 실제 버그(docstring L239-243)**: `paragraph.runs`(python-docx의
표준 속성)는 `<w:hyperlink>` 태그 **안에 중첩된 run을 포함하지 않는다**
— python-docx가 `w:p`(문단)의 **직계 자식** `w:r`만 보기 때문이다.
하이퍼링크로 감싸인 run은 `w:p` → `w:hyperlink` → `w:r`처럼 한 단계
더 깊이 있어서 직계 자식이 아니다. 그 결과, **문단 전체가 하이퍼링크
하나로만 이루어진 경우**(이메일 주소나 웹 링크 문단), `paragraph.runs`가
완전히 빈 리스트가 되어 **문단 전체가 조용히 통째로 사라지는** 회귀가
있었다.

- 해결: `paragraph.iter_inner_content()`(Run과 Hyperlink를 **문서
  순서대로** 순회하는 python-docx API)를 쓴다. 각 항목이
  `Hyperlink`면 그 안의 `.runs`를(하이퍼링크는 내부에 여러 run을
  가질 수 있음), `Run`이면 그 자체를 리스트에 담아 처리 — 결국
  하이퍼링크 안팎을 가리지 않고 모든 run을 순서대로 얻는다.

## L257-267: 표 열 너비 변환

```python
_EMU_PER_MM = 36000

def _column_widths_mm(table) -> list[float] | None:
    widths = []
    for col in table.columns:
        w = col.width
        if w is None:
            return None
        widths.append(round(w / _EMU_PER_MM, 2))
    return widths
```

OOXML은 길이를 EMU(English Metric Units, 1인치=914400 EMU, 1mm=36000
EMU) 단위로 저장한다. `col.width`가 하나라도 `None`이면(드물지만
있을 수 있음) 전체를 `None`으로 반환 — "일부만 아는 열 너비"보다는
"열 너비 정보 없음"으로 명확히 표현하는 편이 낫다는 판단.

## L270-303: `_trim_cell_runs` — 셀 전체 기준 앞뒤 공백 제거

```python
def _trim_cell_runs(runs: list[dict]) -> list[dict]:
    if not runs:
        return runs
    full = "".join(r.get("text") or "" for r in runs)
    if not full.strip():
        return []
    lead = len(full) - len(full.lstrip())
    trail = len(full) - len(full.rstrip())
    out = [dict(r) for r in runs]
    remaining = lead
    for r in out:
        if remaining <= 0:
            break
        t = r.get("text") or ""
        if len(t) <= remaining:
            remaining -= len(t)
            r["text"] = ""
        else:
            r["text"] = t[remaining:]
            remaining = 0
    remaining = trail
    for r in reversed(out):
        ...
    return [r for r in out if r.get("text")]
```

이 함수는 `pdf.py`의 `_container_to_runs` 후처리(첫/마지막 run만
lstrip/rstrip)와 **다른 문제**를 푼다: 여기서는 **셀 전체를 하나의
문자열처럼 이어붙였을 때** 앞뒤 공백이 몇 글자인지 계산하고
(`lead`, `trail`), 그 공백을 **여러 run에 걸쳐서** 정확히 잘라낸다
— 왜냐하면 셀의 첫 공백이 첫 run 안에만 있으리라는 보장이 없기
때문이다(예: 첫 run 자체가 빈 문자열이고 두 번째 run이
`"  텍스트"`로 시작하는 경우).

- **L275-277**: 전체 텍스트를 이어붙여서, strip 후 완전히 비면
  빈 리스트를 반환(셀 전체가 공백뿐이면 셀 자체가 빈 것으로 취급).
- **L278-279**: `lead`(앞쪽 공백 글자 수), `trail`(뒤쪽 공백 글자
  수)을 원본과 strip된 버전의 길이 차이로 계산.
- **L281-291: 앞쪽 공백 제거 루프**: `out`(원본을 복사한 리스트)을
  앞에서부터 순회하며, `remaining`(아직 지워야 할 공백 글자 수)만큼
  각 run의 텍스트 앞부분을 깎아낸다. 한 run의 텍스트 전체가
  `remaining`보다 짧으면 그 run 전체를 비우고 다음 run으로 넘어가고,
  `remaining`보다 길면 그 run에서 필요한 만큼만 잘라내고 종료.
- **L292-302: 뒤쪽 공백 제거**: 같은 로직을 `reversed(out)`(뒤에서
  부터)으로 반복.
- **L303**: 텍스트가 빈 문자열이 된 run은 최종적으로 걸러낸다.

## L306-321: `_cell_runs` — 셀의 여러 문단을 하나로 합치기

```python
def _cell_runs(cell) -> list[dict]:
    runs = []
    for i, p in enumerate(cell.paragraphs):
        if i > 0:
            runs.append({"text": " "})
        for r in _paragraph_runs(p):
            if "\n" in r["text"]:
                r = {**r, "text": r["text"].replace("\n", " ")}
            runs.append(r)
    return _trim_cell_runs(runs)
```

- **L315-316**: 셀 안에 문단이 여러 개면(두 번째 문단부터) 그 사이에
  공백 하나를 삽입 — HWP 표 셀은 항상 단일 문단이라는 전제와 대칭을
  맞추기 위한 "여러 줄 → 한 줄" 평탄화.
- **L318-319**: run 텍스트 안에 직접 삽입된 줄바꿈(`<w:br/>`,
  python-docx가 이걸 `"\n"` 문자로 돌려줌)도 같은 이유로 공백으로
  바꾼다. `{**r, "text": ...}`는 dict를 복사하면서 `text` 키만
  바꾸는 관용구(원본 dict를 직접 변경하지 않음).
- 마지막에 `_trim_cell_runs`로 전체 앞뒤 공백을 정리.

## L324-358: `_table_rows_with_spans` — 병합 감지 (객체 동일성 활용)

```python
def _table_rows_with_spans(table) -> list[list[dict]]:
    n_rows = len(table.rows)
    n_cols = len(table.columns)
    row_tcs = [list(table.rows[r].cells) for r in range(n_rows)]
    seen = set()
    rows_out = []
    for r in range(n_rows):
        row_out = []
        cells = row_tcs[r]
        for c in range(min(n_cols, len(cells))):
            tc_id = id(cells[c]._tc)
            if tc_id in seen:
                continue
            seen.add(tc_id)
            col_span = 1
            while c + col_span < len(cells) and id(cells[c + col_span]._tc) == tc_id:
                col_span += 1
            row_span = 1
            while r + row_span < n_rows:
                below = row_tcs[r + row_span]
                if c < len(below) and id(below[c]._tc) == tc_id:
                    row_span += 1
                else:
                    break
            cell_align = _paragraph_align(cells[c].paragraphs[0]) if cells[c].paragraphs else "left"
            entry = {"runs": _cell_runs(cells[c]), "colSpan": col_span, "rowSpan": row_span,
                     "align": cell_align}
            row_out.append(entry)
        rows_out.append(row_out)
    return rows_out
```

`docx_build.py`의 `_place_cells_with_spans`가 "압축된 표현을 그리드로
복원"했다면, 이 함수는 **정반대**로 "이미 완전한 그리드(python-docx가
주는 형태)에서 병합을 감지해 압축된 표현으로 만든다".

- **핵심 통찰(docstring L325-329, L31-33)**: python-docx의
  `table.cell(r, c)`는 **병합된 영역의 모든 그리드 좌표에서 같은
  내부 XML 객체(`_tc`)를 돌려준다** — 직접 만든 병합 DOCX로 실측
  확인. 즉 2×2로 병합된 셀은 4개 좌표(`(0,0)`,`(0,1)`,`(1,0)`,`(1,1)`)
  전부에서 `cell(r,c)._tc`가 **같은 파이썬 객체**다. 이 "객체 동일성"
  (`id()`로 비교)이 병합 감지의 유일한 근거다.
- **L339-342**: `seen` 집합에 이미 있는 `_tc` 객체는 건너뛴다 — 이게
  "각 행에 처음 등장하는 셀만 담는다"는 압축 규칙의 구현이다. 첫
  등장(왼쪽 위 모서리)만 `seen`에 없으므로 처리되고, 나머지 반복
  등장(병합으로 인한 중복)은 스킵된다.
- **L343-345: colSpan 계산**: 같은 행에서 오른쪽으로 이동하며, `_tc`
  객체가 같은 동안 계속 카운트를 늘린다 — 가로로 몇 칸이나 같은
  셀이 반복되는지가 곧 가로 병합 폭이다.
  가로 병합 폭이다.
- **L346-352: rowSpan 계산**: 아래쪽 행으로 이동하며, 같은 열
  위치(`c`)의 `_tc`가 같은 객체인 동안 계속 카운트를 늘린다.
  다른 객체를 만나거나 행 범위를 벗어나면 멈춘다.
- **L353**: 셀의 정렬은 그 셀의 **첫 번째 문단**을 기준으로
  판단한다(`_paragraph_align`) — 셀 안에 문단이 여러 개면 나머지
  문단의 정렬은 반영되지 않는다는 단순화(문서화되진 않았지만 코드
  구조상 자명함).

## L361-372: `_iter_block_items` — 문서 순서 보존

```python
def _iter_block_items(document):
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)
```

docstring(L6-8)이 예고한 "body XML을 직접 순회" 구현. `document.element.body`
(문서 본문의 최상위 XML 요소)의 자식들을 **문서에 실제로 등장하는
순서 그대로** 순회한다. 각 자식이 `CT_P`(문단의 XML 표현)면
`Paragraph` 객체로, `CT_Tbl`(표의 XML 표현)이면 `Table` 객체로
감싸서 yield — 이 두 저수준 XML 클래스를 python-docx의 고수준 객체로
직접 래핑하는 코드다.

## L374-413: `docx_to_blocks` — 메인 함수

```python
def docx_to_blocks(src: Path) -> list[dict]:
    from docx import Document
    from docx.table import Table

    doc = Document(src)
    levels = _numbering_levels(doc)
    counters: dict[tuple, int] = {}
    blocks: list[dict] = []
    for item in _iter_block_items(doc):
        if isinstance(item, Table):
            rows = _table_rows_with_spans(item)
            if any(cell["runs"] for row in rows for cell in row):
                block = {"type": "table", "rows": rows}
                col_widths = _column_widths_mm(item)
                if col_widths is not None:
                    block["colWidthsMm"] = col_widths
                blocks.append(block)
        else:
            if not item.text.strip():
                continue
            runs = _paragraph_runs(item)
            numpr = _paragraph_numpr(item)
            if numpr is not None:
                num_id, ilvl = numpr
                level = levels.get(num_id, {}).get(ilvl)
                if level is not None:
                    numfmt, lvltext, start = level
                    key = (num_id, ilvl)
                    counters[key] = counters.get(key, start - 1) + 1
                    marker = _format_marker(numfmt, lvltext, counters[key])
                    if marker:
                        runs.insert(0, {"text": f"{marker} ", ...})
            if runs:
                block = {"type": "p", "runs": runs}
                align = _paragraph_align(item)
                if align:
                    block["align"] = align
                blocks.append(block)
    return blocks
```

- **L379**: `_numbering_levels(doc)`을 **문서 전체에 대해 한 번만**
  미리 계산해둔다(문단마다 다시 파싱하지 않음 — 성능·일관성).
- **L380**: `counters: dict[tuple, int] = {}` — `(numId, ilvl)`
  쌍마다 "지금까지 몇 번째 항목인지" 세는 카운터. 이 dict가 함수
  전체에 걸쳐 유지되므로, 문서에서 같은 목록이 여러 번 등장해도
  (예: 본문 중간에 다른 내용이 끼어들어도) 번호가 이어서 계속된다.
- **L383-390: 표 블록 처리**: `_table_rows_with_spans`로 압축된
  행렬을 얻고, `any(cell["runs"] for row in rows for cell in row)`
  로 **표 전체가 완전히 비어있지 않은지** 확인한다(모든 셀이 빈
  텍스트뿐이면 표 자체를 blocks에 안 넣음 — 빈 표를 만드는 실수
  방지). 열 너비가 있으면(`col_widths is not None`) 함께 담는다.
- **L392-393**: 문단 전체가 공백뿐이면 건너뛴다(표시할 내용 없음).
- **L394-406: 번호 매기기 마커 삽입**:
  - `_paragraph_numpr`로 이 문단의 `(num_id, ilvl)`을 얻는다.
  - `levels.get(num_id, {}).get(ilvl)`로 그 서식 정보를 찾는다 —
    문서에 정의는 있지만 실제로 쓰지 않는 numId/ilvl 조합이면
    `None`이 나와 마커 생성을 건너뛴다(방어적 `.get()` 체이닝).
  - `counters[key] = counters.get(key, start - 1) + 1`: 이 키가
    처음 등장하면 `start - 1`(정의된 시작값보다 1 작은 값)에서
    시작해 바로 `+1`해서 `start`가 되고, 두 번째부터는 이전 카운트
    에서 계속 `+1`한다 — "시작값부터 1씩 증가"를 이 한 줄로
    구현한다.
  - `_format_marker`로 실제 마커 문자열을 만들고, 있으면(`if marker:`)
    **runs 리스트의 맨 앞**(`runs.insert(0, ...)`)에 서식 없는
    별도 run으로 삽입한다 — 마커 뒤에 공백 하나(`f"{marker} "`)를
    붙여 본문과 시각적으로 구분한다.
- **L407-412**: run이 하나도 없으면(빈 문단, 마커도 없음) blocks에
  안 넣는다. 있으면 문단 블록을 만들고 정렬을 붙인다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_table_rows_with_spans`가 colSpan과 rowSpan을 각각 어떻게
  다른 방향(가로/세로)으로 계산하는지, 그리고 둘 다 같은 원리
  (`_tc` 객체 동일성)에 기반한다는 걸 설명할 수 있는가?
- `_paragraph_runs`가 `paragraph.runs` 대신
  `paragraph.iter_inner_content()`를 쓰는 이유를 구체적인 실패
  사례(어떤 문단에서 어떤 문제가 생기는지)로 설명할 수 있는가?
- `_trim_cell_runs`와 `pdf.py`의 `_container_to_runs` 후처리
  (lstrip/rstrip)가 "공백 제거"라는 같은 목표를 다른 방식으로
  구현하는 이유는 무엇인가? (힌트: 공백이 한 run에만 있다고
  보장할 수 있는가?)
- `_paragraph_align`이 정렬 미지정일 때 `None` 대신 `"left"`를
  반환하도록 바뀐 이유를, 이 값을 소비하는 Java 쪽 코드
  (`JsonToHwp.java`)의 동작과 연결해서 설명할 수 있는가?
- `counters` dict가 `(numId, ilvl)`을 키로 쓰는 이유는? 만약 `ilvl`
  없이 `numId`만으로 카운트한다면 어떤 문서(다단계 중첩 목록)에서
  잘못된 번호가 나올까?
