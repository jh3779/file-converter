# office.py — DOCX/PPTX→PDF (번들 LibreOffice headless)

원본: `app/converters/office.py` (60줄)

`video.py`와 마찬가지로 외부 실행 파일(LibreOffice의 `soffice`)을
서브프로세스로 호출한다. 이 파일 하나가 DOCX→PDF와 PPTX→PDF **둘 다**
처리한다 — LibreOffice가 입력 포맷을 스스로 감지하기 때문이다. 다른
여러 컨버터(`hwp.py`, `hwpx.py`)도 내부적으로 "DOCX를 만든 다음
이 함수로 PDF화"하는 경로를 타므로, 이 파일은 생각보다 넓게 재사용된다.

---

## L1-6: 모듈 docstring

- `office_to_pdf` 하나로 DOCX/PPTX 둘 다 처리하는 이유: LibreOffice의
  `--convert-to` 옵션은 입력 파일의 내용을 보고 포맷을 자동 감지하므로,
  변환기 코드 입장에서는 DOCX든 PPTX든 완전히 같은 커맨드로 처리할 수
  있다.
- 배포판(사용자에게 나가는 실제 앱)은 LibreOffice 엔진을 **앱 안에
  번들**한다(REQ-NF-005 — "설치 간편함", MS오피스/한글 등 외부 프로그램이
  전혀 없어도 동작해야 한다는 요구사항). 개발 환경에서는 시스템에 설치된
  LibreOffice나 `FILECONV_SOFFICE` 환경변수로 경로를 직접 지정한다.

## L7-13: import

`os`, `shutil`, `subprocess` — `video.py`와 같은 조합(외부 프로세스를
찾고 실행하는 데 필요한 표준 라이브러리). `..bundle.engine_dir()`도
`video.py`의 `find_ffmpeg()`와 완전히 같은 방식으로 쓰인다.

## L15-19: `_DEFAULTS` — 최후의 수단 하드코딩 경로

```python
_DEFAULTS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",             # macOS
    r"C:\Program Files\LibreOffice\program\soffice.exe",                 # Windows
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)
```

사용자가 시스템에 LibreOffice를 직접 설치했지만 PATH에 등록 안 된 경우
(macOS 앱 번들은 보통 PATH에 안 들어감, Windows도 설치 시 PATH 등록을
선택 안 했을 수 있음)를 위한 마지막 폴백 — OS별 "가장 흔한 설치 위치"를
하드코딩해뒀다.

## L22-37: `find_soffice` — 4단계 탐색

```python
def find_soffice() -> str | None:
    env = os.environ.get("FILECONV_SOFFICE")
    if env and Path(env).exists():
        return env
    for bundled in (engine_dir() / "libreoffice" / "program" / "soffice.exe",
                    engine_dir() / "libreoffice" / "program" / "soffice",
                    engine_dir() / "libreoffice" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"):
        if bundled.exists():
            return str(bundled)
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in _DEFAULTS:
        if Path(candidate).exists():
            return candidate
    return None
```

`video.py`의 `_find_tool`보다 한 단계 더 많은(4단계) 탐색 순서:

1. **L23-25**: `FILECONV_SOFFICE` 환경변수(테스트·개발용 강제 지정).
2. **L26-30: 번들 경로 3가지를 순서대로 확인**:
   - `libreoffice/program/soffice.exe` — Windows 배포판(주석에
     "v0.3b"라고 이 경로가 도입된 버전 표시가 남아 있다).
   - `libreoffice/program/soffice`(확장자 없음) — **Linux 배포판**이
     쓰는 경로. macOS와 파일명은 같지만 디렉터리 구조가 다르다(이건
     `code-notes` 밖의 조사에서 실제로 이 경로에 대한 회귀 테스트가
     없다는 걸 발견한 적이 있다 — `docs/07_test_plan.md` 참고).
   - `libreoffice/LibreOffice.app/Contents/MacOS/soffice` — macOS
     배포판(`.app` 번들 내부 구조를 그대로 반영).
   - 이 3개를 **튜플로 나열하고 for로 순회**하는 이유: 같은
     `find_soffice()` 함수가 3개 플랫폼 어디서 실행되든 동작해야
     하므로, "이 실행 환경에 맞는 것 하나만 있을 것"이라는 전제로
     맞는 걸 찾을 때까지 순서대로 확인한다.
3. **L31-33**: 시스템 PATH(`shutil.which("soffice")`) — 개발자가
   Homebrew(`brew install libreoffice`) 등으로 설치한 경우.
4. **L34-36**: 위 셋 다 실패하면 `_DEFAULTS`의 하드코딩 경로들을 확인.
5. **L37**: 전부 실패하면 `None`.

## L40-60: `office_to_pdf`

```python
def office_to_pdf(src: Path, tmpdir: Path) -> Path:
    soffice = find_soffice()
    if soffice is None:
        raise ConversionError("err.engine_missing")
    profile = tmpdir / "lo-profile"
    cmd = [
        soffice, "--headless", "--norestore",
        f"-env:UserInstallation={profile.as_uri()}",
        "--convert-to", "pdf", "--outdir", str(tmpdir), str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    out = tmpdir / (src.stem + ".pdf")
    if proc.returncode != 0 or not out.exists():
        raise ConversionError("err.engine", proc.stderr.decode(errors="replace")[:200])
    return out
```

- **L42-43**: 엔진을 못 찾으면 `err.engine_missing`("문서 변환 엔진을
  찾을 수 없습니다") — `video.py`의 `err.video_missing`과 같은
  성격이지만 별도 키(영상용/문서용 메시지가 다름).
- **L44, L50: `-env:UserInstallation` — 프로필 격리 (가장 미묘한 버그
  방지 코드)**:
  ```python
  profile = tmpdir / "lo-profile"
  ...
  f"-env:UserInstallation={profile.as_uri()}",
  ```
  LibreOffice는 실행할 때마다 "사용자 프로필"(설정·잠금 파일 등을
  담는 디렉터리)을 쓴다. 이 옵션을 안 주면 **모든 변환 작업이 같은
  기본(전역) 프로필을 공유**하게 되는데, 이 앱은 여러 파일을 동시에
  (`app/workers.py`의 `QThreadPool`, 최대 4개 스레드) 변환할 수 있으므로,
  동시에 여러 `soffice` 프로세스가 같은 프로필을 두고 충돌할 수 있다
  (락 파일 경합 등). 그래서 매 변환마다 `tmpdir` 아래 **격리된 임시
  프로필**을 만들어 쓴다 — 이 `tmpdir` 자체가 `app/output.py`의
  `make_tmpdir()`로 작업마다 새로 만들어지는 것이므로, 결과적으로
  변환 작업마다 완전히 독립된 프로필이 보장된다.
  - **`profile.as_uri()`를 쓰는 이유(주석 L47-49)**: `f"file://{profile}"`
    처럼 문자열을 직접 조합하면, **Windows**에서 경로 구분자가
    역슬래시(`C:\Users\...`)라서 `file://C:\Users\...`처럼 슬래시와
    역슬래시가 섞인 **잘못된 file URI**가 만들어진다. `Path.as_uri()`는
    플랫폼에 맞게 올바른 `file:///C:/Users/...` 형태를 생성해주므로,
    이 버그를 원천적으로 피한다.
- **L46**: `--norestore` — LibreOffice가 이전 세션의 비정상 종료를
  감지해서 "문서를 복구하시겠습니까" 같은 대화상자를 headless 모드에서도
  띄우려는 걸 막는다(자동화 스크립트에서 흔히 필요한 옵션).
- **L51**: `--convert-to pdf --outdir <tmpdir> <src>` — 실제 변환
  명령. LibreOffice가 `src`의 파일명 그대로(확장자만 `.pdf`로 바꿔서)
  `tmpdir`에 결과를 쓴다.
- **L53-56**: 180초(3분) 타임아웃. 초과하면 `err.engine`(timeout detail).
- **L57-59**: LibreOffice의 exit code가 0이 아니거나, exit code는
  0인데 실제 출력 파일이 안 생겼으면(둘 다 확인 — LibreOffice가
  가끔 exit 0인데 조용히 실패하는 경우가 있어서 이중 체크) `err.engine`
  으로 실패 처리, stderr 앞 200자를 detail로 남긴다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `-env:UserInstallation` 옵션을 빼면 어떤 상황(동시 변환)에서 어떤
  증상이 나타날 수 있는가?
- `find_soffice()`의 3가지 번들 경로 후보 중, 실제로 Linux 배포판이
  쓰는 경로는 어느 것이고, 이 경로에 대한 전용 테스트가 있는가?
- `profile.as_uri()` 대신 `f"file://{profile}"`을 썼다면 Windows에서
  구체적으로 어떤 문자열이 만들어지고 왜 잘못된 URI가 되는가?
- 이 함수가 DOCX와 PPTX를 구분하는 코드가 어디에도 없는데, 어떻게
  둘 다 올바르게 PDF로 변환되는가?
