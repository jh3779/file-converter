# 08. 정밀 감사 보고서 (2026-09-02)

> Production audit: **76/100, caveated release hold**.
> 현재 브랜치(`docs/sync-requirements-with-code`, HEAD `c555df5`)는 문서/CI 주석 중심 변경이라 코드 병합 리스크는 낮다. 다만 공개 릴리스 판단은 보류가 맞다. 로컬 전체 테스트가 LibreOffice PDF 변환 경로에서 실패했고, 제3자 고지 문서가 현재 번들/지원 범위와 어긋난다.

## 감사 범위

- 대상 저장소: `file-converter`
- 대상 브랜치: `docs/sync-requirements-with-code`
- 비교 기준: `origin/main...HEAD`
- 제품 표면: PySide6 기반 오프라인 데스크톱 파일 변환기
- 감사 관점: 배포 준비도, 테스트 신뢰도, 보안/프라이버시, 외부 엔진/라이선스, UX 계약, 운영 리스크, 문서 정합성
- 확인하지 못한 것: GitHub Actions 최신 실행 상태와 실제 배포 산출물 다운로드/실행. 이번 감사는 로컬 저장소와 로컬 실행 결과 기준이다.

## 점수 근거

76점은 "기반은 좋지만 릴리스 게이트를 다시 통과해야 하는 상태"라는 뜻이다.

- 강점: 오프라인/프라이버시 원칙이 코드에 잘 반영되어 있고, 출력 원본 보호/동시성/임시 파일 정리/패키징 스모크 설계가 탄탄하다.
- 감점: 현재 로컬 전체 테스트가 green이 아니며, 실패 지점이 핵심 문서 PDF 변환 경로다.
- 감점: `THIRD_PARTY_NOTICES.txt`가 최신 FFmpeg 버전, 플랫폼 범위, HWPX 범위, 영상 코덱 정책과 맞지 않는다.
- 감점: PyPI 의존성이 하한만 있어 릴리스 재현성이 약하다.
- 감점: 앱이 실제로 가능한 변환만 노출한다는 제품 계약 일부가 드롭존 문구/영상 오류 문구에서 흐려진다.

## 핵심 결론

릴리스 전 필수 확인은 아래 2개다.

1. 현재 커밋 기준 CI 전체가 green인지 확인하거나, 로컬 LibreOffice headless 실패 원인을 제거한 뒤 전체 테스트를 다시 통과시킨다.
2. `packaging/THIRD_PARTY_NOTICES.txt`를 현재 빌드/지원 범위와 맞게 갱신한다.

이 브랜치 자체의 코드 변경 위험은 낮다. 하지만 위 2개가 해결되기 전에는 새 공개 릴리스나 배포 고지 작성으로 넘어가지 않는 편이 안전하다.

## 실행 증거

### Git 상태

- `git status --short --branch`
  - `## docs/sync-requirements-with-code...origin/docs/sync-requirements-with-code`
- `git diff --stat origin/main...HEAD`
  - 5 files changed, 12 insertions, 9 deletions
  - 변경 파일: `.github/workflows/build.yml`, `docs/00_project_brief.md`, `docs/01_requirements.md`, `docs/README.md`, `docs/design-system/qt-mapping.html`

### 로컬 테스트

- 실행: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover tests -v`
- 결과: **FAILED**
- 범위: 234 tests, 5 errors, 8 skipped
- 실패한 테스트:
  - `tests/test_hwpx.py::TestHwpx.test_hwpx_to_pdf`
  - `tests/test_pdf_to_docx_layout.py::TestPdfToDocxLayout.test_bullet_survives_pdf_round_trip_to_docx`
  - `tests/test_pdf_to_docx_layout.py::TestPdfToDocxLayout.test_bullet_survives_pdf_round_trip_to_txt`
  - `tests/test_pipeline.py::TestOffice.test_docx_to_pdf`
  - `tests/test_pipeline.py::TestOffice.test_pptx_to_pdf`
- 공통 실패 지점:
  - `app/converters/office.py:40-60`
  - `office_to_pdf()`가 `soffice --headless --convert-to pdf`를 실행한 뒤 `ConversionError("err.engine")`를 발생시킨다.

### LibreOffice 직접 재현

- `find_soffice()` 결과: `/opt/homebrew/bin/soffice`
- `soffice --version` 결과: `LibreOffice 26.2.5.2`
- 동일한 방식으로 만든 작은 ASCII 파일명 DOCX를 직접 변환해도 `returncode -6`, stdout/stderr 없음, PDF 없음.
- 판단: 현재 로컬 환경의 LibreOffice/headless 런타임 crash 가능성이 높다. 앱 로직 결함이라고 단정할 수는 없지만, 릴리스 판단용 증거로는 local full suite가 red다.

### 정적 확인

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m compileall -q app scripts`: 통과
- `python3.13 -m compileall -q app scripts`: 통과
- `.venv/bin/python --version`: Python 3.14.5
- CI 워크플로는 Python 3.12를 사용한다. 로컬에는 `python3.12`가 없어서 동일 런타임 재현은 못 했다.

## 주요 발견 사항

| ID | 심각도 | 영역 | 발견 | 근거 | 권장 조치 |
|----|--------|------|------|------|-----------|
| F-01 | Blocker | 테스트/변환 엔진 | 로컬 전체 테스트가 핵심 PDF 변환 경로에서 실패한다. | `office_to_pdf()`는 `app/converters/office.py:40-60`에서 LibreOffice를 호출한다. 실패 테스트 5개가 모두 이 경로로 수렴한다. | 릴리스 전 GitHub Actions 최신 실행 전체 green 확인. 로컬에서는 LibreOffice headless crash 원인을 분리하고, 가능하면 CI와 같은 Python 3.12 환경에서 재실행한다. |
| F-02 | High | 라이선스/고지 | 제3자 고지 문서가 현재 구현과 불일치한다. | `packaging/THIRD_PARTY_NOTICES.txt:15`는 HWPX를 "읽기 Phase 1"로만 표기한다. `:35`는 LibreOffice를 Windows x86_64만으로 표기한다. `:68`은 FFmpeg n7.1이라고 쓰지만 워크플로는 n9.0.1을 사용한다. `:69-71`은 H.264/HEVC 외 코덱 미지원이라고 쓰지만 `app/converters/video.py:128-135`는 Windows `h264_mf` 재인코딩을 시도한다. | 릴리스 전 고지 문서를 Windows/macOS/Linux 번들, FFmpeg n9.0.1, HWPX 읽기/쓰기, Windows 재인코딩 범위에 맞게 갱신한다. |
| F-03 | Medium | 재현성/공급망 | Python 의존성과 PyInstaller가 릴리스 빌드 시점의 최신 버전으로 설치된다. | `requirements.txt:1-10`은 모두 `>=` 하한만 둔다. `.github/workflows/build.yml:71`, `:914` 등은 `pip install -r requirements.txt pyinstaller`를 그대로 실행한다. 이 리스크는 `docs/06_open_questions.md`에도 이미 별도 결정 필요 항목으로 남아 있다. | 플랫폼별로 검증된 `constraints.txt` 또는 lock 파일을 만들고, PyInstaller도 명시 버전으로 고정한다. |
| F-04 | Medium | UX/제품 계약 | 드롭존 문구가 영상 변환을 항상 광고한다. macOS 등 FFmpeg가 없는 환경에서는 실제 TARGETS에서 영상이 빠진다. | `app/i18n.py:21-24`는 영상 파일을 항상 표시한다. `app/converters/__init__.py:34-37`은 `find_ffmpeg()`가 성공할 때만 영상 확장자를 노출한다. | 드롭존 보조 문구를 런타임 지원 상태에 맞게 만들거나, 플랫폼별 문구를 분리한다. "가능한 것만 노출" 원칙과 UI 카피를 맞춘다. |
| F-05 | Medium | 오류 문구 | 영상 코덱 오류 문구가 현재 구현보다 좁게 말한다. | `app/i18n.py:108-111`은 H.264/HEVC만 지원한다고 말한다. 실제 구현은 H.264/HEVC 스트림 카피 외에 Windows `h264_mf` 재인코딩을 시도한다. | 오류 문구를 "이 환경에서 이 코덱을 MP4로 변환할 수 없음"처럼 구현과 플랫폼 차이를 반영하는 표현으로 바꾼다. |
| F-06 | Low | 문서 정합성 | 일부 정본/보조 문서가 현재 코드와 어긋난다. | `docs/README.md:17`과 `docs/01_requirements.md:9`는 영상 범위를 H.264/HEVC만으로 요약한다. `docs/06_open_questions.md:107`도 DEC-060 이후와 다르다. `docs/07_test_plan.md:15`는 전체 테스트를 232개라고 쓰지만 현재 실행은 234개다. `docs/07_test_plan.md:18-19`는 Linux build job을 언급하지 않는다. | 문서 정합성 브랜치라면 위 항목까지 같은 PR에서 맞추는 편이 좋다. |
| F-07 | Low | 리소스 관리 | 테스트 중 SQLite 연결 ResourceWarning이 반복된다. | `app/history.py:28-62`는 연결을 만들지만 닫는 메서드가 없다. `app/ui/main_window.py:227`이 `History()`를 소유하지만 종료 시 close 호출이 보이지 않는다. | `History.close()`를 추가하고 `MainWindow.closeEvent` 및 테스트 tearDown에서 닫는다. |
| F-08 | Low | CI 공급망 강화 | GitHub Actions가 major tag를 사용한다. | `actions/checkout@v4`, `actions/setup-python@v5`, `actions/cache@v4`, `actions/download-artifact@v4` 등. | 보안 민감도를 더 높일 경우 액션을 SHA로 pinning한다. 현재 외부 바이너리 자체는 버전/체크섬 고정이 잘 되어 있어 우선순위는 낮다. |

## 긍정적 발견

- 오프라인/프라이버시 계약이 코드에 잘 반영되어 있다. 런타임 네트워크는 옵트인 업데이트 확인(`app/update_check.py:21-55`)으로 제한되고, 파일 내용/경로 전송은 보이지 않는다.
- 변환 엔진 호출은 `subprocess.run([...])` 인자 배열 방식이다. 앱 코드에서 `shell=True` 사용은 발견하지 못했다.
- 출력 안전성이 좋다. `app/output.py:7-42`는 동시 변환 시 이름 충돌과 원본 덮어쓰기를 막기 위해 lock 안에서 최종 경로 예약/이동을 처리한다.
- 작업 격리가 좋다. `app/workers.py:39-56`은 작업별 임시 디렉터리를 만들고, 성공/실패/취소와 관계없이 정리한다.
- 일부 실패가 전체 배치를 무너뜨리지 않는다. `app/workers.py:48-56`은 변환 오류를 아이템 실패로 격리하고 나머지 작업을 계속 진행한다.
- CI 설계가 넓다. Windows/macOS/Linux 패키징, 엔진 스모크, 설치 파일 스모크, AppImage 실행 스모크가 워크플로에 들어 있다.
- 외부 대형 바이너리는 대체로 고정/검증된다. LibreOffice, FFmpeg, Noto Sans KR, appimagetool은 버전/SHA256 흐름이 있고, hwplib/hwpxlib도 고정 리비전을 checkout한다.
- 수동 테스트 한계를 문서화한 점이 좋다. `docs/07_test_plan.md:72-84`는 자동 테스트가 못 잡는 영역을 별도로 적고, `testing/MANUAL_TEST_CHECKLIST.md`로 넘기는 구조를 둔다.

## 보안/프라이버시 판정

현재 앱 구조에서 고위험 보안 이슈는 발견하지 못했다.

- 파일 변환은 로컬 처리로 설계되어 있다.
- 업데이트 확인은 기본 꺼짐이고, 켜져도 GitHub Releases API에서 버전 정보만 가져온다.
- 변환 대상 파일 경로를 외부 API로 보내는 코드는 발견하지 못했다.
- 저장되는 사용자 데이터는 로컬 변환 기록 SQLite 중심이다.
- 인증, 결제, 서버 API, 멀티테넌트 권한 모델은 이 프로젝트 범위에 없다.

잔여 보안/운영 리스크는 공급망 쪽이다. PyPI 의존성 lock 부재와 GitHub Actions SHA 미고정은 당장 악용 취약점이라기보다 재현성/공급망 성숙도 문제로 보는 것이 맞다.

## 권장 후속 작업

1. P0: 현재 커밋의 GitHub Actions 최신 실행을 확인한다. `test`, `build-windows`, `build-macos`, `build-linux`가 모두 green이어야 한다.
2. P0: 로컬 LibreOffice crash를 분리한다. Homebrew LibreOffice 문제인지, Python 3.14/테스트 조합 문제인지, 앱의 `UserInstallation` 프로필 처리 문제인지 확인한다.
3. P1: `packaging/THIRD_PARTY_NOTICES.txt`를 갱신한다. 이 파일은 배포물에 들어갈 가능성이 높아 릴리스 전 우선순위가 높다.
4. P1: `requirements.txt`와 release install 경로에 constraints/lock을 도입한다. 최소한 릴리스 태그에서는 의존성 해시와 PyInstaller 버전을 고정한다.
5. P2: 영상 지원 UI 문구를 런타임 지원 상태와 맞춘다. macOS/FFmpeg 미탑재 환경에서는 드롭존에서 영상 변환을 광고하지 않게 한다.
6. P2: 문서 정합성 잔여 항목을 정리한다. 특히 영상 요약, 테스트 수, Linux build job, HWPX Phase 1 표현을 맞춘다.
7. P3: `History.close()`와 UI 종료 시 연결 정리를 추가해 ResourceWarning을 없앤다.
8. P3: GitHub Actions SHA pinning을 공급망 강화 과제로 분리한다.

## 최종 판정

이 저장소는 기능 범위가 큰 데 비해 설계 문서, 결정 로그, 자동/수동 테스트 지도, 패키징 스모크가 상당히 잘 쌓여 있다. 가장 큰 문제는 "설계가 부실하다"가 아니라 "릴리스 증거가 지금 이 로컬 감사 시점에서 green이 아니다"에 가깝다.

따라서 현재 판정은 다음과 같다.

- 브랜치 병합 위험: 낮음
- 새 공개 릴리스 위험: 중간 이상
- 릴리스 조건: CI green 확인 + LibreOffice PDF 경로 재검증 + 제3자 고지 갱신
