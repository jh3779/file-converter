# docx_build.py — "구조 블록(blocks JSON)" → DOCX 생성

원본: `app/converters/docx_build.py` (209줄)

이 파일은 **어디서 왔는지 상관없이** "문단·표의 구조를 표현하는 JSON"
(이하 "blocks")을 받아서 실제 `.docx` 파일을 만드는 공용 엔진이다.
`pdf_docx.py`(PDF→DOCX), `hwp.py`(HWP→DOCX), `hwpx.py`(HWPX→DOCX)가
전부 이 파일의 `blocks_to_docx()` 하나를 호출한다 — "DOCX를 만드는 법"을
한 곳에만 구현해두고 여러 소스 포맷이 공유하는 구조다. 이 파일을 이해하면
"문서 변환 결과 DOCX가 왜 이렇게 생겼는지"(절대 위치가 아니라 이어지는
문단·표로 재구성되는 이유)를 알 수 있다.

---

## L1-35: 모듈 docstring — blocks JSON 스키마 정의

이 docstring 자체가 **이 프로젝트에서 가장 중요한 데이터 계약**(schema)의
정본이다. 다른 세 파일(`pdf_docx.py`, `hwp.py`, `hwpx.py`)이 만드는 JSON이
전부 이 스키마를 따라야 `blocks_to_docx`가 올바르게 동작한다.

- **문단 블록**: `{"type":"p", "runs":[{"text":str,"bold":bool,...,
  "size":float,"color":"RRGGBB"}, ...], "align": "left"|"center"|"right"|
  "justify"(선택)}` — 하나의 문단이 여러 "run"(서식이 같은 텍스트 조각)
  으로 구성된다는 뜻. 예: `"굵은텍스트"`와 `"일반텍스트"`가 한 문단
  안에 있으면 각각 다른 `bold` 값을 가진 별도 run이 된다.
- **구버전 호환**: `{"type":"p", "text":str}`처럼 `runs` 없이 `text`만
  있는 형태도 지원 — "서식 없는 단일 run"으로 취급한다. 이 호환
  처리가 `_runs_for()`(L93-99)에 있다.
- **표 블록**: `{"type":"table", "rows":[[cell,...],...]}` — 셀은
  신버전(`{"runs":[...], "colSpan":int, "rowSpan":int, "align":str}`)
  또는 구버전(평문 문자열, `{"text":str,"colSpan":int,"rowSpan":int}`,
  align 없음) 두 형태가 섞여 있을 수 있다.
- **핵심 규칙(L9-11)**: "한 행에는 그 행에서 **처음 등장하는** 셀만
  담긴다" — 세로 병합(rowSpan)이 위 행에서 아래로 내려와 차지하고
  있는 칸은 그 행의 `rows` 리스트에 **아예 없다**(자리를 비워두는
  `None` 같은 placeholder도 없이, 그냥 리스트가 짧아짐). 이건
  `JsonToHwp.java`(HWP를 만드는 쪽)와 `docx_extract.py`(DOCX에서
  읽어내는 쪽)가 공유하는 표현이다 — HTML `<table>`의 `rowspan`
  개념과 비슷하지만, HTML은 셀 자체를 생략하지 않고 `rowspan`
  속성만 주는 데 비해, 여기서는 아예 리스트에서 빠진다는 점이
  다르다. 이 "빠진 자리"를 다시 복원하는 게 `_place_cells_with_spans`
  (아래 L115-154)의 역할이다.
- **한글 글꼴 강제 지정(L21-23, DEC-015)**: python-docx가 새 문서를
  만들 때 기본 폰트(Calibri)는 한글 글리프가 없다. 폰트를 명시하지
  않으면 뷰어·OS마다 다른 대체 폰트를 골라서 렌더링이 일관되지
  않는다 — 실제로 글자가 깨지는 걸 재현·확인한 뒤 모든 run에 폰트를
  명시하기로 결정했다.
- **왜 "맑은 고딕"이 아니라 "Noto Sans KR"인가(L25-34)**: 흥미로운
  "채택하지 않은 대안"의 기록. 맑은 고딕은 대부분의 Windows에
  기본으로 깔려 있어 매력적인 선택지였지만, 이걸 시도했을 때 그
  폰트가 없는 개발 환경(mac)에서 LibreOffice의 폰트 대체 로직이
  "무지정 상태보다 더 나쁜" 대체 폰트를 골라 희귀 글자(뷁 등)의
  매핑이 깨지는 **회귀**가 실측됐다. 그래서 검증된 현재 상태(항상
  Noto Sans KR을 명시하고, 이 폰트를 앱이 직접 번들해 자기 렌더링
  경로에서는 항상 존재를 보장)를 유지하기로 했다. 다만 이 보장은
  "이 앱 자신이 LibreOffice로 렌더링할 때"(예: DOCX→PDF, HWP→PDF)에만
  적용되고, 사용자가 결과 DOCX를 자기 Word/한글에서 열 때는 그
  프로그램에 Noto Sans KR이 없으면 여전히 대체가 일어날 수 있다 —
  이건 "잔여 리스크"로 문서에 명시적으로 남겨져 있다.

## L36-40: import와 상수

```python
from pathlib import Path

EAST_ASIAN_FONT = "Noto Sans KR"

_ALIGN_FROM_STR = None  # 지연 초기화 — docx.enum.text 임포트 비용을 문서 안 열 때는 안 지불하도록
```

`_ALIGN_FROM_STR`이 모듈 최상단에서 `None`으로 시작하는 것 — 이건 "지연
초기화"(lazy init) 패턴이다. 만약 이 파일이 로드되기만 해도(다른 함수를
안 써도) `docx.enum.text`를 무조건 import하면, `python-docx` 로딩
비용을 매번 치르게 된다. 실제로 정렬 매핑이 **필요한 시점**(표나
정렬이 있는 문서를 처리할 때)에만 아래 `_align_map()`이 채운다.

## L43-53: `_align_map()` — 지연 초기화되는 정렬 매핑 딕셔너리

```python
def _align_map():
    global _ALIGN_FROM_STR
    if _ALIGN_FROM_STR is None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        _ALIGN_FROM_STR = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
    return _ALIGN_FROM_STR
```

첫 호출에서만 실제로 import하고 딕셔너리를 채운 뒤, `global`로 모듈
수준 변수에 캐싱한다 — 두 번째 호출부터는 `if` 조건이 거짓이라 즉시
캐싱된 딕셔너리를 반환한다. "필요할 때 한 번만 로드하고 그 뒤로는
재사용"하는 전형적인 지연 초기화(memoization)다.

## L56-68: `_set_font(run)` — 동아시아 폰트를 XML 레벨에서 직접 지정

```python
def _set_font(run):
    run.font.name = EAST_ASIAN_FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find("{...}rFonts")
    if rfonts is None:
        from docx.oxml.ns import qn
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    from docx.oxml.ns import qn
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), EAST_ASIAN_FONT)
```

- **L57**: `run.font.name = EAST_ASIAN_FONT`는 python-docx의 공식
  고수준 API지만, **서양 문자(ascii) 폰트에만 적용**된다(주석 L58-59).
  OOXML(Word의 내부 XML 포맷) 스펙은 폰트를 4가지 문자 범주별로
  따로 지정하게 돼 있다: `w:ascii`(라틴), `w:hAnsi`(고수준 라틴,
  보통 ascii와 같이 씀), `w:eastAsia`(한중일 문자), `w:cs`
  (복합 스크립트, 아랍어 등). 즉 `run.font.name`만 설정하면
  **한글이 여전히 기본 폰트(Calibri 등)로 렌더링될 수 있다** — 이게
  이 함수가 존재하는 이유다.
- **L60-65**: python-docx의 고수준 API로는 `w:eastAsia`를 못 건드리므로,
  XML 트리에 직접 접근한다. `run._element`는 이 run을 표현하는 실제
  XML 요소(`<w:r>`)다. `get_or_add_rPr()`는 그 안의 서식 속성 요소
  (`<w:rPr>`, run properties)를 가져오거나 없으면 새로 만든다.
  `rPr` 안에 `<w:rFonts>` 요소가 없으면(`rfonts is None`) 새로
  만들어(`rpr.makeelement(...)`) `rPr`에 추가한다.
  - `run._element`처럼 언더스코어로 시작하는 속성에 접근하는 건
    파이썬 컨벤션상 "비공개 API"에 손대는 것이다 — python-docx가
    공식적으로 지원하지 않는 저수준 조작이지만, 라이브러리가
    필요한 기능(4개 폰트 슬롯 개별 지정)을 고수준 API로 제공하지
    않아 불가피하게 XML을 직접 다룬다. 이 프로젝트의 여러 DOCX/PDF
    관련 파일에서 반복되는 패턴이다.
- **L66-68**: `qn(attr)`(qualified name, XML 네임스페이스 접두사를
  실제 네임스페이스 URI로 변환하는 python-docx 헬퍼)로 4개 속성
  (`w:ascii`, `w:hAnsi`, `w:eastAsia`, `w:cs`) 전부를 같은
  `EAST_ASIAN_FONT`로 설정한다 — 문자가 어느 범주에 속하든 항상
  Noto Sans KR이 쓰이도록 4개를 모두 통일한다(라틴 문자에까지 이
  폰트를 쓰는 건 "한글 폰트가 라틴 문자도 대부분 포함하고 있으니
  일관성을 우선한다"는 선택으로 보인다).

## L71-90: `_apply_run_style(run, run_dict)` — 굵게/기울임/밑줄/크기/색상

```python
def _apply_run_style(run, run_dict: dict):
    if run_dict.get("bold") is not None:
        run.font.bold = bool(run_dict["bold"])
    if run_dict.get("italic") is not None:
        run.font.italic = bool(run_dict["italic"])
    if run_dict.get("underline") is not None:
        run.font.underline = bool(run_dict["underline"])
    size = run_dict.get("size")
    if size:
        from docx.shared import Pt
        run.font.size = Pt(size)
    color = run_dict.get("color")
    if color and color.upper() != "000000":
        from docx.shared import RGBColor
        try:
            run.font.color.rgb = RGBColor.from_string(color)
        except ValueError:
            pass
```

- **L74-79: `is not None` 체크가 핵심**. `run_dict.get("bold")`가
  `False`인 것과 `None`(키 자체가 없음)인 것을 구분한다 —
  `if run_dict.get("bold"):`(False도 안 걸림)이 아니라
  `if run_dict.get("bold") is not None:`을 쓴 이유는, "명시적으로
  bold=False로 지정된 run"과 "구버전 스키마라 bold 정보 자체가
  없는 run"을 다르게 처리해야 하기 때문이다 — 후자는 아무것도
  건드리지 않아 DOCX 기본값(보통 False)을 그대로 따르게 둔다.
  (실질적으로 결과는 비슷할 수 있지만, "명시적으로 지정 안 함"이라는
  의도를 코드에 정확히 남기는 방어적 스타일.)
- **L80-83**: `size`는 pt(포인트) 단위 숫자로 오는데, python-docx는
  `Pt(size)`(EMU 단위로 변환하는 헬퍼)로 감싸야 한다. `if size:`는
  0이나 None이면 건너뛴다(글자 크기 0은 의미 없으므로 falsy 체크로
  충분).
- **L84-90: 색상 처리의 두 가지 방어**:
  - `color.upper() != "000000"`: 색상이 검정(000000)이면 **아예
    설정하지 않는다** — 검정은 DOCX의 기본 텍스트 색상이라 굳이
    명시할 필요가 없다는 최적화이자, "명시적 검정"과 "지정 없음"을
    구분 안 해도 결과가 같으므로 코드를 단순화한 것.
  - `try/except ValueError: pass`: `RGBColor.from_string(color)`가
    실패할 수 있다(예: 색상 문자열이 6자리 hex가 아닌 손상된 값).
    이때 **조용히 넘어간다**(주석: "텍스트 보존 우선") — 색상 하나가
    잘못됐다고 해서 전체 변환을 실패시키지 않고, 최소한 텍스트
    내용만이라도 살리는 방어적 태도.

## L93-99: `_runs_for(block)` — 문단 블록의 신/구버전 호환

```python
def _runs_for(block: dict) -> list[dict]:
    runs = block.get("runs")
    if runs is not None:
        return runs
    text = block.get("text")
    return [{"text": text}] if text else []
```

`"runs"` 키가 있으면(신버전) 그대로 쓰고, 없으면 `"text"`(구버전)를
"서식 없는 단일 run 하나짜리 리스트"로 감싸서 반환한다 — 이후 코드는
"블록에는 항상 runs 리스트가 있다"고 가정하고 처리할 수 있어, 호출부의
분기가 단순해진다.

## L102-112: `_cell_runs(cell)` — 표 셀의 3가지 형태 호환

```python
def _cell_runs(cell) -> list[dict]:
    if isinstance(cell, str):
        return [{"text": cell}] if cell else []
    runs = cell.get("runs")
    if runs is not None:
        return runs
    text = cell.get("text")
    return [{"text": text}] if text else []
```

`_runs_for`보다 한 단계 더 많은 경우를 처리한다: 셀이 **평문 문자열
자체**(가장 오래된 구버전 표현, `["a", "b"]`처럼 표를 문자열 리스트로
표현하던 시절의 흔적)일 수도 있어서, `isinstance(cell, str)`부터
확인한다. 그다음은 `_runs_for`와 같은 패턴(runs 있으면 그대로, 없으면
text를 감싸기).

## L115-154: `_place_cells_with_spans` — 병합 셀 그리드 좌표 복원 (가장 복잡한 로직)

```python
def _place_cells_with_spans(rows: list) -> tuple[list[dict], int, int]:
    n_rows = len(rows)
    norm_rows = []
    for row in rows:
        norm_row = []
        for cell in row:
            col_span = (cell.get("colSpan") or 1) if isinstance(cell, dict) else 1
            row_span = (cell.get("rowSpan") or 1) if isinstance(cell, dict) else 1
            align = cell.get("align") if isinstance(cell, dict) else None
            norm_row.append({"runs": _cell_runs(cell), "colSpan": col_span, "rowSpan": row_span, "align": align})
        norm_rows.append(norm_row)

    n_cols = sum(c["colSpan"] for c in norm_rows[0]) if norm_rows and norm_rows[0] else 0
    reserved_until_row = [-1] * n_cols
    placed = []
    for r in range(n_rows):
        col = 0
        cell_idx = 0
        row_cells = norm_rows[r]
        while col < n_cols and cell_idx < len(row_cells):
            if reserved_until_row[col] >= r:
                col += 1
                continue
            cell = row_cells[cell_idx]
            cell_idx += 1
            col_span = cell["colSpan"]
            row_span = cell["rowSpan"]
            placed.append({"runs": cell["runs"], "row": r, "col": col, "colSpan": col_span, "rowSpan": row_span,
                           "align": cell["align"]})
            if row_span > 1:
                for cc in range(col, min(col + col_span, n_cols)):
                    reserved_until_row[cc] = r + row_span - 1
            col += col_span
    return placed, n_rows, n_cols
```

**이 함수가 왜 필요한가**: 앞서 스키마에서 설명했듯, 원본 JSON은 "각
행에 그 행에서 처음 등장하는 셀만" 담고 있다 — 세로 병합이 차지한
칸은 생략된다. 하지만 DOCX 테이블을 만들려면(python-docx의
`doc.add_table(rows=n, cols=m)`) **정확한 그리드 크기(행×열)**와
"이 셀이 그리드의 어느 좌표에서 시작하는지"를 알아야 한다. 이 함수는
그 복원 작업을 한다 — HTML 표의 `rowspan` 렌더링과 원리가 같다
(주석 L120: "JsonToHwp.java의 addTableBlock과 동일한 알고리즘" —
즉 이 파이썬 코드와, HWP를 만드는 Java 사이드카가 **같은 알고리즘을
두 언어로 각각 구현**하고 있다는 뜻).

- **L123-131: 1단계 — 셀 정규화**. 각 셀(문자열이든, 구버전
  `{"text":...}`든, 신버전 `{"runs":...}`든)을 전부
  `{"runs": [...], "colSpan": int, "rowSpan": int, "align": str|None}`
  형태로 통일한다. `(cell.get("colSpan") or 1)`은 값이 없거나
  `0`/`None`이면 기본값 1로 — 병합 정보가 없는 일반 셀은 1×1로
  취급된다.
- **L133**: `n_cols`(전체 열 개수)를 **첫 번째 행**의 `colSpan` 합으로
  계산한다. 예: 첫 행이 3개 셀이고 각각 colSpan=1이면 `n_cols=3`.
  첫 행에 이미 가로 병합(colSpan=2)이 있어도, "첫 행 = 전체 열 폭을
  다 채운다"는 전제로 계산한다(표 전체의 폭이 첫 행 기준으로
  결정된다는 가정 — 표 데이터가 이 전제를 어기면 잘못 계산될 수
  있지만, 보통의 표 구조에서는 성립한다).
- **L134**: `reserved_until_row = [-1] * n_cols` — **열마다** "이 열이
  세로 병합으로 몇 번째 행까지 점유돼 있는지"를 추적하는 배열.
  `-1`은 "아무 병합도 점유하고 있지 않음"을 뜻한다.
- **L136-153: 행을 순회하며 실제 그리드 좌표를 채워나가는 핵심 루프**:
  - `col = 0`(현재 열 위치), `cell_idx = 0`(이 행에서 몇 번째 원본
    셀을 처리 중인지 — `row_cells`는 압축된 리스트라 실제 그리드
    열 개수보다 짧을 수 있음을 기억).
  - **L140**: `while col < n_cols and cell_idx < len(row_cells):` —
    아직 채울 열이 남았고, 아직 배정할 원본 셀도 남았으면 계속.
  - **L141-143**: `reserved_until_row[col] >= r`이면(이 열이 세로
    병합으로 인해 현재 행까지도 점유돼 있으면), 이 칸은 **위 행의
    병합 셀이 차지하고 있으니 건너뛴다**(`col += 1; continue`) —
    원본 셀을 소비하지 않고 그냥 열 위치만 다음으로 넘긴다.
  - **L144-149**: 점유되지 않은 칸을 찾으면, `row_cells`에서 다음
    원본 셀 하나를 꺼내(`cell_idx += 1`) 그 셀이 **지금 위치
    (`r`, `col`)에서 시작**한다고 확정한다. 이 좌표·colSpan·rowSpan·
    runs·align 정보를 `placed` 리스트에 기록한다 — 이게 최종
    결과물(호출자가 실제로 쓰는 값).
  - **L150-152**: 만약 이 셀이 세로 병합(`row_span > 1`)이면, 이
    셀이 차지하는 **모든 열**(`col`부터 `col+colSpan`까지)에 대해
    `reserved_until_row[cc] = r + row_span - 1`(마지막으로 점유하는
    행 번호)을 기록해둔다 — 이후 행을 처리할 때 이 정보로 "이 칸은
    이미 차 있다"고 판단하게 된다.
  - **L153**: 다음 열 위치로 `colSpan`만큼 이동.
- 반환값 `(placed, n_rows, n_cols)`: `placed`는 "그리드 좌표가 확정된
  셀들의 리스트", `n_rows`/`n_cols`는 실제 테이블 크기.

## L157-209: `blocks_to_docx` — 메인 함수

```python
def blocks_to_docx(blocks: list[dict], out_path: Path) -> Path:
    from docx import Document
    doc = Document()
    for block in blocks:
        if block.get("type") == "table":
            ...
        else:
            ...
    doc.save(out_path)
    return out_path
```

- **L160**: `Document()` — 빈 새 DOCX 문서를 메모리에 생성.
- **L161**: `blocks` 리스트를 순서대로 순회 — blocks JSON의 배열
  순서가 곧 문서에 나타날 순서다.

### L162-193: 표 블록 처리

```python
if block.get("type") == "table":
    rows = block.get("rows") or []
    if not rows:
        continue
    placed, n_rows, n_cols = _place_cells_with_spans(rows)
    if n_cols == 0:
        continue
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.style = "Table Grid"
    for item in placed:
        cell = table.cell(item["row"], item["col"])
        if item["colSpan"] > 1 or item["rowSpan"] > 1:
            other = table.cell(
                item["row"] + item["rowSpan"] - 1,
                item["col"] + item["colSpan"] - 1,
            )
            cell = cell.merge(other)
        p = cell.paragraphs[0]
        cell_align = _align_map().get(item.get("align"))
        if cell_align is not None:
            p.alignment = cell_align
        for run_dict in item["runs"]:
            text = run_dict.get("text")
            if not text:
                continue
            run = p.add_run(text)
            _set_font(run)
            _apply_run_style(run, run_dict)
```

- **L164-165, 167-168**: 빈 표(rows 없음, 또는 계산 결과 열이 0개)는
  건너뛴다 — 방어적 처리.
- **L169-170**: `doc.add_table(rows=n_rows, cols=n_cols)`로 **비어있는
  전체 그리드**를 먼저 만든다(모든 칸이 빈 셀인 균일한 테이블).
  `table.style = "Table Grid"`로 격자선이 보이는 기본 스타일을 지정
  (스타일 없이 만들면 테두리가 안 보이는 표가 됨).
- **L172**: `table.cell(item["row"], item["col"])`로 이 셀이 시작하는
  위치의 셀 객체를 가져온다.
- **L173-178: 병합 실제 수행**: colSpan/rowSpan이 1보다 크면, "끝
  좌표"의 셀(`item["row"]+rowSpan-1`, `item["col"]+colSpan-1`)을
  계산해서 `cell.merge(other)`로 시작 셀과 끝 셀 사이의 **직사각형
  영역 전체를 병합**한다 — python-docx의 `merge()`는 "이 두 셀을
  대각선 모서리로 하는 사각형을 하나로 합쳐라"는 의미로 동작한다.
  병합 후 `cell` 변수를 병합된 새 셀 객체로 갱신한다(`cell = cell.merge(other)`).
- **L179-182 (주석)**: `cell.text = "..."`(python-docx가 제공하는
  가장 간단한 셀 텍스트 설정법)을 쓰지 않고, 문단 블록과 똑같이
  run 단위로 직접 붙이는 이유 — 셀 안 문자 서식(굵게/색상 등,
  DEC-051)을 보존하려면 run 단위 제어가 필요하다. `p.add_run(text)`
  안의 `"\n"`(줄바꿈)은 python-docx가 **자동으로** `<w:br/>`(줄바꿈
  태그)로 바꿔준다는 걸 직접 확인했다고 명시(즉 셀 안에 여러 줄이
  있는 텍스트를 하나의 run으로 넣어도 여러 줄로 렌더링된다는 뜻).
- **L183-186**: `cell.paragraphs[0]`(새로 만든 셀은 항상 빈 문단
  하나를 갖고 시작한다)을 가져와, `align`이 있으면 그 문단에 정렬을
  적용한다.
- **L187-193**: 셀의 각 run에 대해 텍스트가 있으면(`if not text:
  continue`로 빈 run은 건너뜀) `p.add_run(text)`로 실제 run을
  추가하고, `_set_font`(폰트 강제 지정)와 `_apply_run_style`(서식
  적용)을 순서대로 호출한다.

### L194-207: 문단 블록 처리

```python
else:
    runs = [r for r in _runs_for(block) if r.get("text")]
    if not any((r.get("text") or "").strip() for r in runs):
        continue
    p = doc.add_paragraph()
    for run_dict in runs:
        run = p.add_run(run_dict["text"])
        _set_font(run)
        _apply_run_style(run, run_dict)
    align = _align_map().get(block.get("align"))
    if align is not None:
        p.alignment = align
```

- **L195**: `_runs_for(block)`으로 신/구버전 호환된 run 목록을 얻고,
  텍스트가 있는 run만 남긴다.
- **L196-199 (주석이 중요)**: "문단 전체가 공백뿐이면(실제 내용 없음)
  문단 자체를 건너뛴다"와 "공백만 있는 개별 run은 단어 사이 구분자일
  수 있어 그대로 둔다"는 **서로 다른 기준을 두 단계로 적용**한다.
  - `any((r.get("text") or "").strip() for r in runs)`: **하나라도**
    strip 후 비어있지 않은 run이 있으면 True — 즉 "이 문단에
    의미있는 텍스트가 하나라도 있는가"를 확인한다.
  - 이게 False면(즉 모든 run이 공백뿐이면) 문단 자체를 스킵
    (`continue`) — 완전히 빈 줄을 DOCX에 남기지 않는다.
  - 하지만 문단이 스킵되지 않고 진행되면, **개별 run 안의 공백은
    strip하지 않고 그대로** 쓴다(L201-204에 strip 로직이 없음) —
    예를 들어 `"굵게 "`(끝에 공백) + `"이어지는말"`처럼 두 run
    사이의 공백이 단어 구분자 역할을 할 수 있으므로 지우면 안
    된다는 판단.
- **L200-204**: 새 문단을 만들고, 각 run에 텍스트를 추가하며 폰트·
  서식을 적용한다(표 셀 처리와 완전히 동일한 패턴).
- **L205-207**: 문단 전체의 정렬(`align`)이 있으면 적용.

## L208-209: 저장과 반환

`doc.save(out_path)`로 실제 파일을 디스크에 쓰고, 그 경로를 그대로
반환한다 — 이 반환값이 호출자(`pdf_docx.py`, `hwp.py`, `hwpx.py`)의
최종 변환 결과가 된다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_place_cells_with_spans`가 "각 행에 처음 등장하는 셀만 있다"는
  압축된 표현을 어떻게 완전한 그리드 좌표로 복원하는가? `reserved_until_row`
  배열이 정확히 무엇을 추적하는가?
- `_set_font`가 `run.font.name`만으로 충분하지 않은 이유는? OOXML의
  4가지 폰트 슬롯(ascii/hAnsi/eastAsia/cs)은 각각 무슨 문자 범주를
  담당하는가?
- 색상이 `"000000"`일 때 굳이 설정을 생략하는 이유는 무엇이고, 이게
  결과에 실질적인 차이를 만드는가?
- 문단 블록 처리에서 "문단 전체가 공백"과 "개별 run이 공백"을 다르게
  처리하는 이유는? 이 구분이 없다면 어떤 실제 문서에서 문제가 생길까?
- 왜 "맑은 고딕"을 채택하지 않았는가? 이 결정을 뒤집으려면 어떤
  조건이 충족돼야 하는가?
