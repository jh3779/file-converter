# base.py — 공용 기반 (모든 컨버터가 의존하는 최하위 모듈)

원본: `app/converters/base.py` (28줄)

이 파일은 `app/converters/` 안의 다른 모든 파일이 가장 먼저 import하는 파일이다.
`ConversionError`(실패를 표현하는 방법)와 `read_text_auto_encoding`(한글 인코딩
자동 감지) 두 가지만 제공한다. 다른 컨버터가 이 파일을 import하는 이유를 알면,
"이 프로젝트에서 실패는 어떻게 표현되는가"라는 질문에 답할 수 있다.

---

## L1: `from pathlib import Path`

`Path` 하나만 import한다 — 이 파일이 다루는 게 파일시스템 경로(텍스트 파일 읽기)
뿐이라는 뜻. 다른 무거운 라이브러리(pdfminer, python-docx 등)는 여기 없다 —
이 파일은 의도적으로 "가벼운 공용 유틸"로 남아 있다.

## L4-10: `class ConversionError(Exception)`

```python
class ConversionError(Exception):
    def __init__(self, key: str, detail: str = ""):
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key
        self.detail = detail
```

- 이 프로젝트에서 "변환이 실패했다"는 사실을 표현하는 **유일한 공식 예외 타입**이다.
  `app/converters/` 전체를 뒤져도 `raise ValueError(...)`, `raise RuntimeError(...)`
  같은 계약 밖 예외를 직접 던지는 곳이 없다(전부 `ConversionError`로 통일).
- `key`는 **에러 메시지 문자열이 아니라 i18n 키**다(예: `"err.corrupted"`,
  `"err.encoding"`). 실제 사용자에게 보여줄 한국어/영어 문구는
  `app/i18n.py`의 `_S` 딕셔너리에 이 키로 등록돼 있다 — 즉 컨버터 코드는 "무엇이
  잘못됐는지"만 키로 표현하고, "그걸 어떻게 말로 표현할지"는 UI 계층(i18n)의 책임이다.
  이 분리 덕분에 같은 실패라도 한국어/영어 두 언어로 자동 전환된다.
- `detail`은 선택 항목 — 로그·디버깅용 원문 메시지(예: 원래 파이썬 예외의
  `str(e)`)를 실어 보낼 때 쓴다. `super().__init__(...)`에 그대로 넘겨 Python
  예외 체계와도 호환되게(예: `str(exc)`로 사람이 읽을 수 있는 형태) 만든다.
- `self.key`, `self.detail`을 인스턴스 속성으로 남겨두는 이유: 호출한 쪽
  (`app/workers.py`)이 `except ConversionError as e: ... e.key ...`처럼
  **키만 꺼내 UI 시그널로 전달**하기 위해서다. `app/workers.py:48-49`에서
  `except ConversionError as e: job.signals.item_failed.emit(item.id, e.key)`로
  이어진다 — 즉 이 클래스는 "컨버터 → 워커 → UI"로 실패 정보가 흘러가는
  파이프라인의 첫 관문이다.

**어디서 쓰이는가**: `hwp.py`, `hwpx.py`, `pdf.py`, `pdf_docx.py`, `pdf_pptx.py`,
`data.py`, `image.py`, `office.py`, `video.py`, `model3d.py`가 전부 이걸 raise한다
(`docx_build.py`는 순수 "생성" 로직이라 실패할 일이 거의 없어 직접 쓰지 않음).

## L13: `_TEXT_ENCODINGS = ("utf-8-sig", "cp949", "utf-8")`

- 시도 순서가 중요하다: **BOM 있는 UTF-8 → CP949(EUC-KR 상위 호환) → BOM 없는
  UTF-8** 순.
- 왜 이 순서인가: 한국에서 만들어진 CSV/TXT 파일은 엑셀 등에서 "ANSI(CP949)"로
  저장되는 경우가 매우 흔하고, 반대로 요즘 도구는 UTF-8(BOM 포함)로 저장하는
  경우도 많다. UTF-8을 먼저 시도해야 하는 이유는, CP949로 먼저 시도하면 실제
  UTF-8 파일도 (한글 코드 포인트 범위와 겹쳐) **깨지지 않고 엉뚱하게 디코딩**돼
  버려 조용한 데이터 손상이 날 수 있기 때문이다. UTF-8은 잘못된 바이트 시퀀스에서
  확실히 `UnicodeDecodeError`를 던지므로, "정상 디코딩되면 그게 맞는 인코딩"이라는
  가정이 위 순서에서는 안전하게 성립한다.
- 함수 이름 앞의 `_` 접두사(비공개 규약)는 없지만 모듈 상수 표기(`_UPPER`가 아닌
  `_snake`)로 "이 모듈 내부에서만 쓰는 상수"라는 뜻을 나타낸다.

## L16-28: `def read_text_auto_encoding(path: Path) -> str`

```python
def read_text_auto_encoding(path: Path) -> str:
    for enc in _TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError:
            raise ConversionError("err.corrupted")
    raise ConversionError("err.encoding")
```

- **L21-23**: `_TEXT_ENCODINGS`를 순서대로 시도하며 `Path.read_text(encoding=enc)`를
  호출한다. 성공하면(디코딩 에러 없이 끝까지 읽히면) 그 문자열을 즉시 반환한다 —
  가장 먼저 성공하는 인코딩이 최종 채택된다.
- **L24-25**: `UnicodeDecodeError`(그 인코딩으로는 못 읽음)는 무시하고 다음
  인코딩으로 넘어간다(`continue`). 이게 "자동 감지"의 핵심 — 여러 인코딩을
  순서대로 찔러보고 처음 맞는 걸 쓴다.
- **L26-27**: `OSError`(파일이 아예 안 열림 — 권한 문제, 디스크 오류 등)는
  인코딩 문제가 아니므로 재시도할 이유가 없다 — 즉시 `err.corrupted` 키로
  `ConversionError`를 던져 루프를 빠져나간다. 이 두 예외를 구분한 것이 중요한
  설계 포인트다: "인코딩을 못 맞췄다"와 "파일 자체가 문제다"는 사용자에게
  다른 메시지로 보여야 한다.
- **L28**: 3가지 인코딩을 전부 시도했는데도(즉 루프가 끝까지 돌았는데도) 전부
  `UnicodeDecodeError`였다면, 마지막으로 `err.encoding` 키를 던진다. 이 줄은
  `for` 루프 밖에 있으므로 "루프 안에서 return도 못 하고 raise도 안 했다"는
  뜻 — 즉 3가지 인코딩 모두 실패했을 때만 도달한다.

**히스토리(docstring L17-20)**: 원래 `data.py`(CSV 전용)에만 있던 로직이었는데,
`markup.py`(TXT/MD/HTML, DEC-061)가 두 번째 소비자로 생기면서 이 공용 모듈로
승격됐다 — "두 번째 소비자가 생기면 공유 모듈로 승격"이라는 이 프로젝트의 관례를
보여주는 예시다(`docx_build.py`/`docx_extract.py`가 여러 컨버터에 공유되는 것도
같은 패턴).

**어디서 쓰이는가**: `data.py`(`_read_csv_rows`), `markup.py`(TXT/MD/HTML 읽기)가
직접 호출한다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `ConversionError`의 `key`와 `detail`은 각각 어디로 흘러가는가? (UI에 보이는
  문구 vs 로그)
- 왜 CP949보다 UTF-8을 먼저 시도해야 하는가?
- `OSError`와 `UnicodeDecodeError`를 다르게 처리하는 이유는?
