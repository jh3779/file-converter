# hwp.py — HWP 변환 (Java 사이드카 호출)

원본: `app/converters/hwp.py` (169줄)

이 프로젝트에서 가장 독특한 컨버터다 — 실제 HWP 파싱/생성 로직은 파이썬이
아니라 **Java 사이드카**(`sidecar/hwp/*.java`, hwplib 라이브러리 기반)가
담당하고, 이 파일은 그 Java 프로세스를 서브프로세스로 실행하고 JSON으로
데이터를 주고받는 "얇은 다리" 역할만 한다. `office.py`(LibreOffice)나
`video.py`(FFmpeg)와 같은 "외부 엔진 호출" 패턴이지만, 이번엔 그 엔진이
바이너리가 아니라 이 프로젝트가 직접 만든 Java 코드라는 점이 다르다.

---

## L1-43: 모듈 docstring — 5개의 결정 기록이 압축된 요약

- **파이프라인 요약(L3-8)**: 3개의 Java 진입점(`HwpToText`, `HwpToJson`,
  `JsonToHwp`)과 5가지 변환 경로가 나열돼 있다. 핵심은 "구조 JSON"이
  Python↔Java 경계를 넘나드는 **공용 데이터 형식**이라는 것 — HWP→DOCX는
  `HwpToJson`(Java)이 JSON을 내고 파이썬(`docx_build.blocks_to_docx`)이
  그걸 읽어 DOCX를 만들고, DOCX→HWP는 반대로 파이썬이 JSON을 만들어
  `JsonToHwp`(Java)에 넘긴다. `blocks_to_docx`의 스키마 문서
  (`docx_build.md` 참고)가 정확히 이 JSON의 정본이다.
  - "파일 경로만 인자로 주고받는다"(L8) — 프로세스 간 통신이 소켓·
    네트워크가 아니라 **디스크의 파일 경로 두 개(입력·출력)**라는
    뜻. 이건 이 앱의 "네트워크 요청 0건"(REQ-NF-002) 원칙과 직결된다 —
    Java 프로세스와 통신하는 것도 "네트워크"로 오해될 수 있는데, 실제로는
    로컬 프로세스 실행+파일 I/O일 뿐이라는 걸 명시.
- **DEC-017 정정 사례(L10-20)**: "hwplib은 표를 새로 못 만든다"는 예전
  기록이 **틀렸다**는 게 나중에 발견됐다 — 공식 샘플 코드를 놓쳤던 것.
  이후 실제 표 컨트롤 생성이 구현됐다(셀 병합은 여전히 범위 밖으로
  남음). 이렇게 "예전 결정이 틀렸음을 인정하고 수정한 기록"이 코드에
  그대로 남아 있다는 게 이 프로젝트의 문서화 방식을 보여준다.
- **번호·불릿 목록(L22-27)**: DOCX의 자동 번호("1.")·불릿("•")은 문단의
  **실제 텍스트가 아니라** `numbering.xml`이라는 별도 서식 파일이 뷰어
  화면에 그려주는 것이다. 이걸 놓치면 결과 HWP에서 번호·불릿이 조용히
  사라진다(코드 리뷰에서 재현·발견) — `docx_extract.py`가 이 XML을
  해석해서 마커를 실제 텍스트로 문단 앞에 붙인다.
- **PDF→HWP 페이지 경계(L29-35, DEC-039)**: 예전엔 PDF 전체를 한
  문자열로 뽑아 페이지 구분 자체가 사라졌었다(외부 QA가 발견). 지금은
  페이지 단위로 순회하며 각 페이지 첫 문단에 표시를 남기고, Java 쪽이
  그걸 "쪽 나눔"(page break) 비트로 반영한다.
- **문단 정렬(L37-42, DEC-040)**: 방향마다 정렬 정보의 출처가 다르다 —
  DOCX→HWP는 python-docx의 실제 지정값(스타일 상속은 범위 밖), PDF→HWP는
  좌표 기반 추정(bbox 휴리스틱), HWP→DOCX는 항상 원본 정렬을 읽어 반영.
  align 정보가 없으면 HWP 문서 기본값인 "양쪽 정렬"을 따른다(실측 확인).

## L44-55: import와 저장소 경로

```python
import json, os, shutil, subprocess, sys
from pathlib import Path
from ..bundle import engine_dir
from .base import ConversionError
from .docx_build import blocks_to_docx

_REPO = Path(__file__).resolve().parents[2]
```

- `_REPO = Path(__file__).resolve().parents[2]`: 이 파일
  (`app/converters/hwp.py`)에서 부모 디렉터리를 2단계 올라가면
  저장소 루트(`app/converters/` → `app/` → 저장소 루트)가 된다.
  아래 `_classpath()`가 개발 환경에서 `spike/hwplib/...`,
  `sidecar/hwp/...` 같은 저장소 내부 경로를 찾을 때 이 기준점을 쓴다.

## L58-65: `_java()` — JRE 실행 파일 탐색

`office.py`의 `find_soffice()`, `video.py`의 `_find_tool()`과 완전히
같은 3단계 패턴(환경변수 → 번들 경로 → 시스템 PATH)이다. 다만 후보가
하나뿐이라(`java`) 더 단순하다.

## L68-87: `_classpath()` — Java 클래스패스 탐색 (개발/배포 이중 경로)

```python
def _classpath() -> str | None:
    env = os.environ.get("FILECONV_HWP_CLASSPATH")
    if env:
        return env
    bundled = engine_dir() / "hwp"
    if bundled.exists():
        return str(bundled)
    hwplib = _REPO / "spike" / "hwplib" / "libs" / "hwplib-main"
    sidecar = _REPO / "sidecar" / "hwp" / "out"
    if hwplib.exists() and sidecar.exists():
        parts = [str(sidecar), str(hwplib)]
        hwpxlib = _REPO / "spike" / "hwpxlib" / "libs" / "hwpxlib-main"
        if hwpxlib.exists():
            parts.append(str(hwpxlib))
        return os.pathsep.join(parts)
    return None
```

- **L72-74**: 배포판이면 `engine_dir()/hwp`에 hwplib+hwpxlib+사이드카
  클래스가 **전부 미리 컴파일돼 한 폴더**로 번들돼 있다(CI가 빌드
  단계에서 만들어 둠) — 이 경로 하나면 끝.
- **L75-86**: 개발 환경(이 저장소를 직접 clone해서 로컬 실행하는 경우)
  에는 그런 번들이 없으므로, 저장소 안의 스파이크 빌드 산출물
  (`spike/hwplib/libs/hwplib-main`)과 사이드카 컴파일 결과
  (`sidecar/hwp/out`)를 각각 찾아 `os.pathsep`(OS별 클래스패스 구분자
  — Windows는 `;`, macOS/Linux는 `:`)으로 합친 문자열을 만든다.
  - `hwpxlib`(HWPX 지원용, HWP와 별개 라이브러리)은 **선택적으로만**
    추가한다(L83-85) — 로컬에 HWPX 스파이크를 아직 안 해본 환경이면
    조용히 빠지고, HWP 경로는 정상 동작한다. HWPX 변환을 실제로
    시도할 때만 그때 가서 `err.hwp_missing`으로 실패한다(즉시 전체를
    막지 않고, 필요한 기능만 늦게 실패하는 "우아한 열화").
- 셋 다 없으면 `None` → 호출자가 `err.hwp_missing`.

## L90-115: `_run_sidecar` — Java 프로세스 실행의 핵심 (한글 경로 버그 우회 포함)

```python
def _run_sidecar(main_class: str, src: Path, out: Path):
    java = _java()
    cp = _classpath()
    if java is None or cp is None:
        raise ConversionError("err.hwp_missing")
    safe_src = out.parent / f"_hwp_in{src.suffix}"
    safe_out = out.parent / f"_hwp_out{out.suffix}"
    shutil.copy(src, safe_src)
    try:
        proc = subprocess.run(
            [java, "-cp", cp, main_class, str(safe_src), str(safe_out)],
            capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not safe_out.exists():
        stderr = proc.stderr.decode(errors="replace")
        key = "err.password" if "distribution" in stderr.lower() else "err.corrupted"
        raise ConversionError(key, stderr[:200])
    shutil.move(str(safe_out), out)
```

**이 함수가 모든 HWP/HWPX 변환의 공통 실행 지점**이다 — `main_class`
파라미터로 어떤 Java 프로그램(`HwpToText`, `HwpToJson`, `JsonToHwp`,
그리고 `hwpx.py`도 이 함수를 그대로 재사용)을 실행할지만 다르고, 나머지
로직(프로세스 실행, 오류 처리)은 완전히 공유된다.

- **L95-101: 한글 경로 우회(가장 미묘한 버그 방지 코드)**:
  주석(L95-98)이 설명하는 실제 재현된 버그: JVM이 명령줄 인자
  (argv, 여기서는 `str(safe_src)`, `str(safe_out)`)를 디코딩할 때
  `sun.jnu.encoding`이라는 내부 설정을 쓰는데, 이건 **OS 로캘의 기본
  코드페이지**를 따른다. 영어 로캘 Windows(코드페이지 1252, 서유럽
  문자만 표현 가능)에서 한글이 포함된 파일 경로("표.hwp")를 그대로
  JVM에 넘기면, 표현 불가능한 한글 문자가 `?`로 뭉개져 **JVM이 엉뚱한
  파일을 찾으려 든다** — 이게 실제로 CI(en-US 러너)에서 재현됐다.
  - **해결책**: 원본 경로를 그대로 넘기지 않고, ASCII만으로 이루어진
    **임시 별칭**(`_hwp_in.hwp`, `_hwp_out.hwp`)을 `out.parent`(임시
    작업 디렉터리, 항상 안전한 위치)에 만들어 그걸 JVM에 넘긴다.
  - `shutil.copy(src, safe_src)`: 원본을 이 안전한 이름으로 **복사**
    한다(원본은 절대 건드리지 않음 — 이 앱의 "원본 보호" 원칙과
    일치).
- **L103-106**: `[java, "-cp", cp, main_class, str(safe_src), str(safe_out)]`
  — Java 실행 명령. `-cp`(클래스패스), 실행할 메인 클래스 이름,
  입력·출력 경로 두 개를 인자로 넘긴다. 사이드카 Java 코드
  (`HwpToText.main(String[] args)` 등)는 `args[0]`이 입력, `args[1]`이
  출력이라는 계약으로 작성돼 있다.
- **L107-108**: 120초 타임아웃, 초과 시 `err.engine`.
- **L109-112: 실패 원인 구분**:
  ```python
  key = "err.password" if "distribution" in stderr.lower() else "err.corrupted"
  ```
  Java 프로세스가 실패했을 때(비정상 exit, 또는 출력 파일이 안 생김),
  stderr에 `"distribution"`이라는 단어가 있는지로 원인을 나눈다 —
  hwplib이 "배포용으로 암호화된 HWP"(distribution 파일, 한글의 문서
  보안 기능)를 열려고 시도하면 그런 메시지를 내는 걸 이용한 문자열
  매칭 휴리스틱이다(`office.py`의 `"encrypt"` 검사와 같은 패턴).
- **L113-115**: 성공했으면 `safe_out`(안전한 임시 이름으로 나온 결과)을
  **진짜 원하는 최종 경로**(`out`)로 옮긴다. 주석(L113-114)이
  설명하듯, 이 `shutil.move`는 순수 Python/OS 파일 API를 쓰므로
  (Windows에서도 wide-char 경로를 지원) 한글이 포함된 최종 경로로
  옮기는 건 전혀 문제없다 — **문제는 오직 JVM의 argv 디코딩
  구간에만 있었다**는 걸 명확히 한다(그래서 입력만 안전한 이름으로
  바꾸고, 출력 이동은 별도 우회 없이 그냥 표준 API로 처리).

## L118-121: `hwp_to_txt`

```python
def hwp_to_txt(src: Path, tmpdir: Path) -> Path:
    out = tmpdir / (src.stem + ".txt")
    _run_sidecar("HwpToText", src, out)
    return out
```

가장 단순한 변환 — `HwpToText` Java 클래스를 호출해 평문 텍스트를 뽑는다.

## L124-132: `hwp_to_docx`

```python
def hwp_to_docx(src: Path, tmpdir: Path) -> Path:
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    _run_sidecar("HwpToJson", src, blocks_json)
    try:
        blocks = json.loads(blocks_json.read_text(encoding="utf-8"))["blocks"]
    except (json.JSONDecodeError, KeyError) as e:
        raise ConversionError("err.corrupted", str(e))
    return blocks_to_docx(blocks, tmpdir / (src.stem + ".docx"))
```

3단계 파이프라인: (1) `HwpToJson`(Java)이 HWP를 구조 JSON으로 변환,
(2) 그 JSON을 파이썬이 읽어 `blocks`(문단·표 배열)를 꺼냄, (3) 이미
문서화한 `docx_build.blocks_to_docx`로 실제 DOCX 생성. JSON 형식이
예상과 다르면(`json.JSONDecodeError`) 또는 `"blocks"` 키 자체가
없으면(`KeyError`) `err.corrupted`.

## L135-139: `hwp_to_pdf`

```python
def hwp_to_pdf(src: Path, tmpdir: Path) -> Path:
    from . import office
    intermediate = hwp_to_docx(src, tmpdir)
    return office.office_to_pdf(intermediate, tmpdir)
```

**중간 변환 재사용**의 전형적 사례 — HWP를 직접 PDF로 만드는 별도
로직이 없다. 대신 이미 만든 `hwp_to_docx`로 먼저 DOCX를 만들고, 그
DOCX를 `office.py`(LibreOffice)로 PDF화한다. HWP→PDF 직행 경로를 새로
짤 필요가 전혀 없다 — HWP→DOCX와 DOCX→PDF 둘 다 이미 검증된 경로이므로
그냥 이어붙이면 된다.

## L142-148: `docx_to_hwp`

```python
def docx_to_hwp(src: Path, tmpdir: Path) -> Path:
    from .docx_extract import docx_to_blocks
    blocks = docx_to_blocks(src)
    return _blocks_to_hwp(blocks, src, tmpdir)
```

역방향(DOCX→HWP). `docx_extract.py`(다음 문서에서 다룸)의
`docx_to_blocks`로 DOCX에서 구조 JSON을 뽑고, 아래 공용 헬퍼
`_blocks_to_hwp`로 HWP를 만든다.

## L151-161: `pdf_to_hwp`

```python
def pdf_to_hwp(src: Path, tmpdir: Path) -> Path:
    from . import pdf as pdf_mod
    blocks = pdf_mod._extract_pdf_blocks_by_page(src)
    return _blocks_to_hwp(blocks, src, tmpdir)
```

`pdf.py`의 `_extract_pdf_blocks_by_page`(밑줄로 시작하는 비공개 함수를
다른 모듈이 직접 import해서 씀 — 패키지 내부 재사용은 이 프로젝트에서
흔한 패턴)로 PDF에서 페이지별 blocks를 뽑아 같은 `_blocks_to_hwp`로
HWP를 만든다. `docx_to_hwp`와 `pdf_to_hwp`가 "blocks를 어떻게 얻는지"
만 다르고, "blocks로 HWP를 어떻게 만드는지"는 완전히 공유한다.

## L164-169: `_blocks_to_hwp` — DOCX/PDF→HWP 공용 종착점

```python
def _blocks_to_hwp(blocks: list[dict], src: Path, tmpdir: Path) -> Path:
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    blocks_json.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    out = tmpdir / (src.stem + ".hwp")
    _run_sidecar("JsonToHwp", blocks_json, out)
    return out
```

`hwp_to_docx`가 Java→Python 방향으로 JSON을 읽었다면, 이 함수는
Python→Java 방향으로 JSON을 **쓴다**: blocks 리스트를
`{"blocks": [...]}` 형태로 JSON 파일에 저장하고, `JsonToHwp`(Java)를
호출해 실제 HWP 파일을 만들게 한다. `ensure_ascii=False`로 한글이
이스케이프 없이 그대로 저장된다(Java 쪽에서 UTF-8로 정상 읽는다는
전제).

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_run_sidecar`가 왜 입력 파일만 안전한 이름으로 복사하고 출력은
  그대로 두는가? 만약 출력 경로도 같은 문제(JVM argv 디코딩)를
  겪는다면 코드가 어떻게 달라져야 하는가?
- `hwp_to_pdf`가 별도의 "HWP→PDF 직접 변환" 로직을 갖지 않는 이유는?
  이 설계의 장단점은 무엇인가?
- `docx_to_hwp`와 `pdf_to_hwp`가 공유하는 부분과 각자 다른 부분을
  정확히 구분할 수 있는가?
- `_classpath()`가 `hwpxlib`을 선택적으로만 추가하는 이유는? 이게 왜
  "즉시 전체 실패"보다 나은 설계인가?
