# data.py — CSV↔XLSX, CSV↔JSON 변환

원본: `app/converters/data.py` (158줄)

REQ-F-006(데이터 변환)을 담당한다. 4개의 공개 변환 함수
(`csv_to_xlsx`, `xlsx_to_csv`, `csv_to_json`, `json_to_csv`)와 2개의 헬퍼
(`_read_csv_rows`, `_format_cell_value`), 그리고 UI가 쓰는 조회 함수
(`xlsx_sheet_count`)로 구성된다.

---

## L1-8: 헤더 · import

```python
"""데이터 변환 — CSV↔XLSX, CSV↔JSON (REQ-F-006). 한글 인코딩 자동 감지 (REQ-F-009 Should)."""
import csv
import datetime
import io
import json
from pathlib import Path

from .base import ConversionError, read_text_auto_encoding
```

`openpyxl`(엑셀 라이브러리)은 여기서 import하지 않는다 — 각 함수 안에서
지역 import(`from openpyxl import Workbook`, L27/L70/L81)로 필요할 때만
불러온다. 이건 이 프로젝트 전반의 패턴으로, 무거운 서드파티 라이브러리를
모듈 최상단에서 미리 로드하지 않고 실제로 그 함수가 호출될 때만 로드해
앱 시작 시간을 단축한다(PyInstaller로 패키징된 데스크톱 앱이라 콜드 스타트
비용이 특히 민감함).

## L11-23: `_read_csv_rows` — CSV 파싱의 유일한 진입점

```python
def _read_csv_rows(path: Path) -> list[list[str]]:
    text = read_text_auto_encoding(path)
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
```

- **L12**: 먼저 `base.py`의 `read_text_auto_encoding`으로 파일 전체를
  문자열로 읽는다(인코딩 자동 감지는 여기 위임 — 이 파일은 그 로직을
  중복하지 않는다).
- **L20**: `csv.Sniffer().sniff(...)`로 구분자(콤마/세미콜론/탭)를
  자동 감지한다. `text[:4096]`만 넘기는 이유: 파일 전체를 스니핑하면
  느리고, 앞부분 4KB면 구분자 패턴을 판단하기에 충분하다는 실용적 절충.
- **L21-22**: 스니핑 실패(예: 컬럼이 1개뿐이라 구분자를 추측할 단서가
  없는 경우)하면 콤마를 기본값으로 쓴다 — `csv.Error`를 넓게 잡아 어떤
  이유로든 스니핑이 안 되면 조용히 폴백한다.
- **주석(L13-16)이 설명하는 과거 버그**: `csv.Sniffer`가 구분자뿐 아니라
  `quotechar`(따옴표 문자)나 `doublequote`(이스케이프 규칙)까지 추측하게
  두면, 셀 안에 줄바꿈이나 이스케이프된 큰따옴표가 있는 실제 데이터에서
  오탐이 나서 값이 중간에 잘렸다. 그래서 지금은 **구분자만** 스니핑하고,
  따옴표 규칙은 `csv.reader`의 기본값(RFC4180 표준, `csv.excel`)으로
  고정했다 — `csv.reader(..., delimiter=delimiter)`처럼 `quotechar`
  파라미터를 안 넘기면 기본값이 쓰인다.
- **L23**: `io.StringIO(text)`로 문자열을 파일처럼 감싸 `csv.reader`에
  넘긴다. **왜 `text.splitlines()`로 미리 줄 단위로 쪼개지 않는가**
  (주석 L17-18): 셀 안에 줄바꿈이 포함된 필드(예: `"여러줄\n텍스트"`처럼
  큰따옴표로 감싸인 필드)가 있으면, `splitlines()`로 먼저 쪼개는 순간
  그 필드가 두 개의 별도 "행"으로 잘못 나뉜다. `csv.reader`는 원문
  텍스트 스트림을 통째로 받아야 따옴표 안의 줄바꿈을 필드의 일부로
  올바르게 인식한다.

## L26-35: `csv_to_xlsx`

```python
def csv_to_xlsx(src: Path, tmpdir: Path) -> Path:
    from openpyxl import Workbook
    rows = _read_csv_rows(src)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    for row in rows:
        ws.append(row)
    out = tmpdir / (src.stem + ".xlsx")
    wb.save(out)
    return out
```

- `Workbook(write_only=True)`: openpyxl의 "쓰기 전용" 모드 — 셀을
  하나씩 메모리에 다 올리지 않고 스트리밍으로 저장해, 대용량 CSV에서도
  메모리를 적게 쓴다. 대신 쓰기 전용 모드는 나중에 다시 읽거나 셀을
  랜덤 접근할 수 없다(이 함수는 순수 "쓰기"만 하므로 문제없음).
- `ws.append(row)`: `row`가 문자열 리스트인데, openpyxl이 각 값을 그대로
  셀에 넣는다 — 즉 숫자처럼 보이는 문자열("123")도 엑셀에서 자동으로
  숫자로 인식될 수 있다(엑셀 자체의 타입 추론에 맡김, 이 함수가 직접
  타입 변환은 안 함).
- `src.stem`: 확장자를 뺀 파일명(`"data.csv"` → `"data"`). 모든 변환
  함수가 이 패턴(`src.stem + ".ext"`)으로 출력 파일명을 짓는다.

## L38-64: `_format_cell_value` — XLSX→CSV의 값 정규화 (DEC-019)

```python
def _format_cell_value(v):
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        if v.time() == datetime.time(0, 0):
            return v.date().isoformat()
        return v.isoformat(sep=" ")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v
```

이 함수가 존재하는 이유(docstring L39-51)를 먼저 이해해야 한다: openpyxl로
셀 값을 읽으면, 엑셀에서 "2026-07-31"처럼 보이던 날짜 셀이 파이썬
`datetime.datetime` 객체로 온다. 이걸 그대로 `csv.writer`에 넘기면
`str()`이 적용돼 `"2026-07-31 00:00:00"`처럼 자정 시각까지 붙어버려서
사용자가 보기엔 "이상하게 추출됐다"고 느낀다. 정수처럼 보이던 셀도
내부적으로 `3.0`(float)일 수 있어 그대로 쓰면 `"3.0"`이 된다.

- **L52-53**: 빈 셀(`None`)은 빈 문자열로.
- **L54-57**: `datetime.datetime`이면, 시각이 정확히 자정(`00:00:00`)일 때는
  **날짜만**(`v.date().isoformat()` → `"2026-07-31"`) 반환한다. 자정이 아닌
  실제 시각이 있으면(드물지만 엑셀에 시간까지 입력된 셀) 날짜+시각을 공백으로
  구분해(`isoformat(sep=" ")`) 반환한다 — "시간 정보가 있을 때만 보여준다"는
  판단.
- **L58-59, 60-61**: 순수 `date`/`time` 타입도 각각 ISO 형식으로.
  (`isinstance(v, datetime.date)` 체크는 `datetime.datetime`도
  `datetime.date`의 서브클래스라서 **반드시 datetime 체크(L54) 뒤에
  와야 한다** — 순서를 바꾸면 datetime 객체가 이 date 분기에 먼저
  걸려버려 시각 정보가 사라진다.)
- **L62-63**: `float`이고 `.is_integer()`(소수부가 0)면 정수로 변환해
  문자열화 — `3.0` → `"3"`. `4.5`처럼 진짜 소수는 이 분기를 안 타고
  그대로(L64) 반환된다.
- **L64**: 위 어느 것도 아니면(문자열, 정수, bool 등) 그대로 반환 —
  `csv.writer.writerow`가 각 값을 알아서 `str()`한다.
- **범위 밖으로 명시한 것(docstring L47-50)**: 통화·퍼센트 서식 같은
  `number_format`은 안 본다 — `read_only=True`(L83)로 값만 빠르게 읽는
  현재 구조에서 서식까지 보려면 더 무거운 로딩이 필요해서, 이번 범위에서는
  뺐다고 명시돼 있다.

## L67-77: `xlsx_sheet_count` — UI 고지용 조회 함수

```python
def xlsx_sheet_count(path: Path) -> int:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, read_only=True)
        n = len(wb.sheetnames)
        wb.close()
        return n
    except Exception:
        return 1
```

- 이 함수는 **변환을 수행하지 않는다** — 단지 "이 XLSX 파일에 시트가
  몇 개인지" 알려줄 뿐이다. `app/ui/main_window.py`가 변환 시작 **전에**
  이 함수를 호출해서, 시트가 2개 이상이면 "첫 번째 시트만 변환돼요"라는
  고지(`note.xlsx_multisheet`)를 미리 보여준다.
- **L76-77**: 파일을 열다가 어떤 예외가 나든(`except Exception`, 넓게
  잡음) 그냥 `1`을 반환한다. 이유(docstring L68-69): 여기서 실패해도
  실제 변환(`xlsx_to_csv`)을 시도하면 그때 본연의 오류
  (`err.corrupted` 등)로 다시 드러나므로, 이 함수는 "UI 고지 판단용"
  이지 오류를 정확히 보고하는 역할이 아니다 — 그러니 실패하면 그냥
  "시트 1개(고지 불필요)"로 간주하고 넘어간다.

## L80-105: `xlsx_to_csv`

```python
def xlsx_to_csv(src: Path, tmpdir: Path) -> Path:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(src, read_only=True, data_only=True)
    except Exception as e:
        key = "err.password" if "encrypt" in str(e).lower() else "err.corrupted"
        raise ConversionError(key, str(e))
    ...
    ws = wb.worksheets[0]
    out = tmpdir / (src.stem + ".csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow([_format_cell_value(v) for v in row])
    wb.close()
    return out
```

- **L83**: `data_only=True` — 셀에 수식(`=A1+B1`)이 있으면 그 **수식
  문자열이 아니라 마지막으로 계산된 결과값**을 읽는다(엑셀이 저장 시점에
  캐싱해둔 값). 수식 자체를 CSV로 내보내는 건 의미가 없으므로.
- **L84-86**: 파일을 여는 데 실패하면(zip 손상, 암호로 잠긴 파일 등)
  예외 메시지에 `"encrypt"`가 포함돼 있는지로 "암호로 잠긴 파일인지
  단순 손상인지"를 구분한다 — openpyxl이 암호화된 xlsx를 열려고 하면
  에러 메시지에 그런 단어가 들어가는 걸 이용한 문자열 매칭 휴리스틱이다
  (정식 API로 명확히 구분하는 방법이 없어서 택한 방식으로 보인다).
  `err.password`와 `err.corrupted`는 서로 다른 i18n 문구로 이어진다.
- **L87-96 주석이 설명하는 정책**: 시트가 여러 개면 **첫 번째 시트만**
  변환한다. 왜: "입력 1개 → 출력 1개"라는 이 앱의 데이터 모델
  (`FileItem.output`이 단일 경로) 전제상, 여러 시트를 여러 파일로
  뽑아내려면 모델 자체를 바꿔야 해서 별도 과제로 미뤘다.
  - **`wb.active`를 안 쓰고 `wb.worksheets[0]`을 쓰는 이유**(L91-93):
    `wb.active`는 "첫 번째 시트"가 아니라 "파일이 마지막 저장될 때
    화면에 열려 있던 탭"이다. 사용자가 세 번째 탭을 보다가 저장하면
    `wb.active`는 세 번째 시트를 가리킨다 — 이걸 쓰면 UI가 "첫 번째
    시트만 변환돼요"라고 말해놓고 실제로는 활성 탭을 변환하는
    불일치 버그가 있었다(주석에 "버그였다"고 명시). `worksheets[0]`은
    항상 워크북 저장 순서상 맨 앞 시트를 가리켜 문구와 실제 동작이
    일치한다.
  - **의도적 범위 밖(L94-96)**: 여기서 "첫 번째"는 숨김 시트도 포함한
    저장 순서 기준이다 — 실사용에서 맨 앞 시트가 숨겨진 메타데이터
    시트이고 사용자가 보는 실제 첫 탭이 두 번째인 경우까지는
    처리하지 않는다.
- **L99**: `utf-8-sig`로 저장 — BOM(Byte Order Mark)을 포함해야 엑셀이
  한글 CSV를 열 때 자동으로 UTF-8로 인식한다(BOM 없는 UTF-8은 엑셀이
  로케일 기본 인코딩으로 오인해 한글이 깨질 수 있음).
- **L102-103**: `ws.iter_rows(values_only=True)`로 각 행을 값만
  (셀 객체가 아니라 순수 값) 순회하고, 각 값을 `_format_cell_value`로
  정규화한 뒤 `writer.writerow`로 쓴다.

## L108-131: `csv_to_json`

```python
def csv_to_json(src: Path, tmpdir: Path) -> Path:
    rows = _read_csv_rows(src)
    if not rows:
        records: list = []
    else:
        header, body = rows[0], rows[1:]
        extra_key = "_extra"
        header_set = set(header)
        while extra_key in header_set:
            extra_key = "_" + extra_key
        records = []
        for row in body:
            record = dict(zip(header, row))
            if len(row) > len(header):
                record[extra_key] = row[len(header):]
            records.append(record)
    out = tmpdir / (src.stem + ".json")
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
```

- **L109-111**: CSV가 완전히 비어있으면 빈 리스트(`[]`)를 JSON으로 낸다.
- **L113**: 첫 행을 헤더(컬럼명), 나머지를 데이터 행으로 나눈다.
- **L119-122 (충돌 없는 초과 컬럼 키 만들기 — 최근 수정 사항)**:
  `dict(zip(header, row))`는 두 리스트 중 짧은 쪽 길이에 맞춰 짝을
  짓는다 — 즉 `row`가 `header`보다 길면 초과 값이 조용히 버려지는게
  원래 문제였다(실제 사용자 CSV에서 불규칙한 행이 있으면 데이터가
  말없이 사라짐). 이를 막기 위해 `csv.DictReader`의 `restkey` 관례를
  따라, 초과 값을 별도 키에 리스트로 보존한다.
  - 다만 원본 헤더에 이미 `"_extra"`라는 컬럼이 있으면, 그 키에 초과
    값을 넣는 순간 **원래 `_extra` 컬럼 값을 덮어써 버리는 새로운
    데이터 손실**이 생긴다(이 버그는 코드 리뷰에서 실제로 발견됨).
    그래서 `header_set`(헤더 컬럼명 집합)과 겹치지 않을 때까지
    `extra_key` 앞에 언더스코어를 계속 붙여가며(`"_extra"` →
    `"__extra"` → ...) 충돌 없는 키를 찾는다.
- **L124-128**: 각 데이터 행에 대해 `dict(zip(header, row))`로 기본
  딕셔너리를 만들고, `len(row) > len(header)`(행이 헤더보다 길 때)면
  `row[len(header):]`(초과분 전체)를 리스트로 만들어 `extra_key`에
  붙인다. 행이 헤더보다 **짧을 때**는 이 로직이 손대지 않는다 — `zip`이
  짧은 쪽에서 멈추므로, 부족한 컬럼은 그냥 dict에 키 자체가 안 생긴다
  (값 손실이 아니라 애초에 값이 없는 경우이므로 이건 별개 이슈).
- **L130**: `ensure_ascii=False`로 한글이 `\uXXXX` 이스케이프가 아니라
  실제 문자로 그대로 JSON에 저장된다(가독성).

## L134-158: `json_to_csv`

```python
def json_to_csv(src: Path, tmpdir: Path) -> Path:
    try:
        payload = json.loads(read_text_auto_encoding(src))
    except json.JSONDecodeError as e:
        raise ConversionError("err.corrupted", str(e))
    if not isinstance(payload, list):
        raise ConversionError("err.jsonshape")

    out = tmpdir / (src.stem + ".csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if all(isinstance(r, dict) for r in payload):
            keys: list[str] = []
            for r in payload:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            writer.writerow(keys)
            for r in payload:
                writer.writerow([r.get(k, "") for k in keys])
        elif all(isinstance(r, list) for r in payload):
            writer.writerows(payload)
        else:
            raise ConversionError("err.jsonshape")
    return out
```

- **L136-138**: JSON 파싱 실패 → `err.corrupted`.
- **L139-140**: JSON의 최상위 값이 리스트가 아니면(예: 객체 하나만
  있는 JSON) `err.jsonshape` — "표로 바꿀 수 없는 구조"라는 뜻(CSV는
  본질적으로 "행의 나열"이라 리스트 형태여야 함).
- **L145-153: 리스트 원소가 전부 dict일 때 — "union of keys" 전략**:
  - **L146-150**: 모든 레코드를 순회하며 **처음 등장하는 순서대로**
    키를 수집한다(`if k not in keys: keys.append(k)` — 중복 없이,
    등장 순서 보존). 예: `[{"a":1}, {"a":2,"b":"x"}]`이면
    `keys == ["a", "b"]`가 된다(첫 레코드에 없던 `"b"`도 두 번째
    레코드에서 발견되면 포함됨).
  - **L151**: 이 통합된 키 목록을 헤더 행으로 먼저 쓴다.
  - **L152-153**: 각 레코드에 대해 `r.get(k, "")`로 값을 꺼낸다 —
    그 레코드에 없는 키는 빈 문자열로 채운다(예: 첫 레코드는
    `"b"`가 없으므로 그 칸이 빈 칸이 됨). 이게 "union of keys" 전략의
    핵심 — 레코드마다 필드가 달라도 전체 필드의 합집합을 헤더로 삼아
    표 형태를 강제로 맞춘다.
- **L154-155**: 리스트 원소가 전부 list(2차원 배열 형태 JSON)면, 그냥
  그대로 각 행을 쓴다(`writer.writerows`) — 이미 표 형태이므로 변환할
  게 없다.
- **L156-157**: dict도 아니고 list도 아닌 혼합/다른 타입이 섞여 있으면
  `err.jsonshape`.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `csv_to_json`에서 헤더에 이미 `_extra`가 있는 CSV를 넣으면 실제 출력
  키 이름은 무엇이 되는가?
- `xlsx_to_csv`가 `wb.active` 대신 `wb.worksheets[0]`을 쓰는 이유는
  무엇이고, 이게 왜 실제 버그를 고친 변경이었는가?
- `_format_cell_value`에서 `datetime.date` 체크가 `datetime.datetime`
  체크보다 반드시 뒤에 와야 하는 이유는? (파이썬 상속 관계와 관련)
- `json_to_csv`가 레코드마다 필드가 다른 dict 리스트를 받으면 최종 CSV의
  컬럼 순서는 어떻게 결정되는가?
