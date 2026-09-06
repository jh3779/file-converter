# hwpx.py — HWPX 변환 (hwp.py와 대칭 구조)

원본: `app/converters/hwpx.py` (80줄)

`hwp.py`를 먼저 이해했다면 이 파일은 빠르게 읽을 수 있다 — **거의 모든
함수가 hwp.py의 대응 함수와 1:1로 대칭**이고, 심지어 `_run_sidecar`
함수 자체를 새로 만들지 않고 `hwp.py`에서 그대로 import해서 재사용한다.
이 문서는 `hwp.py`와 **다른 점**을 중심으로 설명한다(공통된 메커니즘은
`hwp.md` 참고).

---

## L1-23: 모듈 docstring — HWPX가 HWP와 다른 점, 그리고 같은 점

- **HWPX란(L4-5)**: 한글과컴퓨터의 최신 표준 문서 포맷(확장자 `.hwpx`).
  hwplib이 다루는 기존 바이너리 `.hwp`와는 **완전히 다른 스펙**
  (OWPML, ZIP+XML 기반 — 사실상 DOCX와 비슷한 "ZIP 안에 XML들"
  구조)이다.
- **별도 라이브러리, 같은 인프라(L6-11)**: HWPX는 `hwplib`이 아니라
  같은 저자가 만든 **별도 라이브러리 `hwpxlib`**(Apache-2.0, 순수
  JDK)로 다룬다. 하지만 두 라이브러리의 Java 패키지명이 겹치지 않아서
  (`kr.dogfoot.hwplib` vs `kr.dogfoot.hwpxlib`), **엔진 번들·클래스패스·
  JVM 실행 인프라를 hwplib과 완전히 공유**할 수 있었다 — 이게 바로
  이 파일이 `hwp.py`의 `_run_sidecar()`를 import해서 그대로 쓰는
  이유(L30 `from .hwp import _run_sidecar`)다. 새 엔진 디렉터리나
  새 JVM 실행 경로를 전혀 안 만들었다.
- **Phase 1 → Phase 2 히스토리(L13-18)**: 처음엔 읽기만 지원했다
  (HWPX→TXT/DOCX/PDF, "Phase 1", 외부 QA 요청). 나중에(Phase 2, DEC-049)
  쓰기(DOCX/PDF→HWPX)를 추가했는데, **`hwp.py`의 기존 함수들
  (`docx_to_hwp`/`pdf_to_hwp`/`_blocks_to_hwp`)과 완전히 같은 패턴**
  으로 만들었다 — 유일한 차이는 Java 쪽에서 `JsonToHwp.java` 대신
  `JsonToHwpx.java`를 호출하는 것뿐. 게다가 blocks를 만드는 파이썬 쪽
  함수들(`docx_extract.docx_to_blocks()`, `pdf._extract_pdf_blocks_by_page()`)
  은 **이미** align/colSpan/rowSpan/pageBreakBefore를 다 내고 있어서
  (HWP 쓰기를 위해 이미 만들어둔 것), HWPX를 위해 파이썬 코드를
  수정할 필요가 전혀 없었다 — 그대로 재사용.
- **스키마 대칭(L20-23)**: `HwpxToJson.java`가 내는 JSON은
  `HwpToJson.java`(HWP용)와 **같은 스키마**를 쓴다 — 그래서
  `docx_build.blocks_to_docx`(HWP→DOCX에도 쓰이는 그 함수)를 여기서도
  그대로 재사용할 수 있다.

## L25-30: import

```python
import json
from pathlib import Path

from .base import ConversionError
from .docx_build import blocks_to_docx
from .hwp import _run_sidecar
```

`hwp.py`와 거의 같은 import 목록인데, `os`/`shutil`/`subprocess`/`sys`/
`engine_dir`이 **전혀 없다** — 이 파일은 Java 프로세스를 직접 실행하는
로직(`_java()`, `_classpath()`, `_run_sidecar()` 자체의 구현)을 전혀
갖고 있지 않고, `hwp.py`에서 이미 완성된 `_run_sidecar` 함수 하나만
가져다 쓰기 때문이다. 이게 이 파일이 80줄로 짧을 수 있는 핵심 이유.

## L33-36: `hwpx_to_txt`

`hwp.py`의 `hwp_to_txt`와 완전히 동일한 구조, `main_class`만
`"HwpxToText"`로 다르다.

## L39-47: `hwpx_to_docx`

`hwp.py`의 `hwp_to_docx`와 **줄 단위로 거의 동일**하다(`main_class`가
`"HwpxToJson"`이라는 것만 다름). 두 함수를 나란히 놓고 비교하면
diff가 거의 없을 정도로 대칭이다 — 이건 "복붙 중복"이 아니라
`hwp.py`의 `_run_sidecar`/`blocks_to_docx`처럼 **실제 공유 로직은
이미 별도 함수로 뽑혀 있고, 남은 차이(어떤 Java 클래스를 부를지)만
각 파일이 자기 방식대로 표현**하는 구조다.

## L50-54: `hwpx_to_pdf`

```python
def hwpx_to_pdf(src: Path, tmpdir: Path) -> Path:
    from . import office
    intermediate = hwpx_to_docx(src, tmpdir)
    return office.office_to_pdf(intermediate, tmpdir)
```

`hwp.py`의 `hwp_to_pdf`와 동일한 "중간 변환 재사용" 패턴 — HWPX를
먼저 DOCX로 바꾸고, 그 DOCX를 LibreOffice로 PDF화한다. HWPX→PDF
직행 경로가 따로 없다.

## L57-63: `docx_to_hwpx`

```python
def docx_to_hwpx(src: Path, tmpdir: Path) -> Path:
    from .docx_extract import docx_to_blocks
    blocks = docx_to_blocks(src)
    return _blocks_to_hwpx(blocks, src, tmpdir)
```

`hwp.py`의 `docx_to_hwp`와 완전히 같은 구조 — 유일한 차이는 마지막에
`_blocks_to_hwpx`(이 파일의 로컬 헬퍼)를 호출한다는 것.

## L66-72: `pdf_to_hwpx`

`hwp.py`의 `pdf_to_hwp`와 동일한 구조 — `pdf_mod._extract_pdf_blocks_by_page`
를 그대로 재사용(같은 함수, HWP/HWPX 양쪽에서 공유).

## L75-80: `_blocks_to_hwpx` — 유일하게 "새로 정의"된 함수

```python
def _blocks_to_hwpx(blocks: list[dict], src: Path, tmpdir: Path) -> Path:
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    blocks_json.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    out = tmpdir / (src.stem + ".hwpx")
    _run_sidecar("JsonToHwpx", blocks_json, out)
    return out
```

`hwp.py`의 `_blocks_to_hwp`와 로직이 완전히 같지만, 출력 확장자가
`.hwpx`이고 Java 클래스가 `"JsonToHwpx"`라는 점만 다르다. 이 함수를
`hwp.py`의 `_blocks_to_hwp`와 통합(파라미터로 확장자·클래스명을 받는
공용 함수 하나로)하지 않고 **각 파일에 각자 정의**한 이유는 추정컨대:
두 함수가 3줄짜리로 이미 충분히 짧고, 통합하면 오히려 "왜 HWP 파일에
HWPX 헬퍼가 있지?"처럼 개념적 경계가 흐려질 수 있어서 — 각 포맷의
"쓰기 종착점"을 그 포맷 파일 안에 두는 대칭성을 선택한 것으로 보인다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- 이 파일이 `_java()`, `_classpath()`를 전혀 정의하지 않고도 Java
  프로세스를 실행할 수 있는 이유는?
- `hwpx_to_docx`와 `hwp_to_docx`(hwp.py)의 차이는 정확히 무엇인가?
  (한 단어로 답할 수 있어야 한다)
- `_blocks_to_hwp`(hwp.py)와 `_blocks_to_hwpx`(이 파일)를 하나의 공용
  함수로 합친다면 어떤 파라미터가 필요할까? 합치지 않은 것이 더 나은
  설계라고 생각하는가?
- HWP와 HWPX가 완전히 다른 파일 포맷 스펙인데도 이렇게 코드를 거의
  100% 공유할 수 있었던 근본적인 이유는 무엇인가? (힌트: "구조 JSON"
  이라는 중간 표현의 역할)
