# 07. 테스트 계획 (Test Plan)

> 정본 스펙 문서 00~06과 같은 체계 — 자동 테스트가 실제로 무엇을
> 검증하는지, 무엇을 검증하지 못해 수동 테스트로 넘어가는지 한눈에 보기
> 위한 문서. 테스트 자체의 내용(assert 하나하나)은 각 `tests/*.py` 파일이
> 정본이고, 이 문서는 그 위의 지도(map) 역할만 한다 — 테스트 코드가
> 바뀌면 이 문서도 같이 갱신한다.

## 실행 방법

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

전체 197개 중 7개는 로컬 환경에 따라 스킵된다(아래 "실행 조건" 참고).
CI(`test` job, `.github/workflows/build.yml`)는 매 push/PR마다 이 명령을
그대로 실행한다 — Java/LibreOffice/FFmpeg가 없는 가벼운 러너라 사이드카
필요 테스트는 CI에서도 스킵되고, 그 부분은 `build-windows`/`build-macos`
job의 **엔진 스모크**(사이드카를 실제로 빌드해 직접 실행)가 대신 게이트한다
— 이 문서 마지막 "자동 테스트가 못 잡는 것" 절 참고.

## 실행 조건 범례

| 조건 | 의미 | 로컬 준비 |
|------|------|-----------|
| 항상 | 외부 의존성 없음, 항상 실행 | — |
| JDK+hwplib | 로컬 hwplib 빌드 필요 | `spike/hwplib/RESULT.md` 절차 |
| JDK+hwpxlib | 로컬 hwpxlib 빌드 필요(위 사이드카도 함께 컴파일돼 있어야 함, `sh sidecar/hwp/build.sh`) | `spike/hwpxlib/RESULT.md` 절차 |
| soffice | LibreOffice 설치(또는 배포판 번들) 필요 | `find_soffice()`가 찾는 경로에 설치 |
| ffmpeg | FFmpeg 설치(또는 배포판 번들) 필요 | `find_ffmpeg()`가 찾는 경로에 설치 |

## 변환 경로별 커버리지

REQ-F ID·DEC는 `docs/01_requirements.md`·`docs/06_open_questions.md` 참고.

| 변환 | 관련 REQ/DEC | 테스트 파일::클래스 | 실행 조건 |
|------|--------------|----------------------|-----------|
| CSV↔XLSX | REQ-F-006 | `test_converters.py::TestCsvXlsx` | 항상 |
| CSV↔JSON | REQ-F-006 | `test_converters.py::TestCsvJson` | 항상 |
| PDF→TXT | REQ-F-004 | `test_pipeline.py::TestPdf` | 항상 |
| PDF→DOCX(절대 위치 레이아웃) | REQ-F-004, DEC-010·DEC-037 | `test_pipeline.py::TestPdf`, `test_pdf_to_docx_layout.py::TestPdfToDocxLayout`, `test_format_fidelity.py::TestPdfToDocxFormatting/TestPdfToDocxAlignment` | 항상 |
| PDF→HWP | REQ-F-005, DEC-023·DEC-039·DEC-040 | `test_pipeline.py::TestHwp`(`test_pdf_to_hwp_*`), `test_converters.py::TestPdfToHwpPageBreaks` | JDK+hwplib(왕복 검증 부분) |
| PDF→HWPX | DEC-049 | `test_hwpx.py::TestHwpxWrite`(`test_pdf_to_hwpx_preserves_page_breaks`) | JDK+hwpxlib |
| PDF→PNG/JPG | REQ-F-016, DEC-026·DEC-043 | `test_pdf_images.py::TestPdfToImages` | 항상 |
| PDF→PPTX | REQ-F-017, DEC-030·DEC-036 | `test_pdf_to_pptx.py`, `test_pdf_to_pptx_visuals.py` | 항상 |
| DOCX→PDF | REQ-F-003 | `test_pipeline.py::TestOffice` | soffice |
| PPTX→PDF | REQ-F-012, DEC-016 | `test_pipeline.py::TestOffice` | soffice |
| DOCX→HWP(표 신규 생성·병합·서식·정렬, 표 셀 안 서식) | REQ-F-005, DEC-017·DEC-028·DEC-035·DEC-038·DEC-040·DEC-051 | `test_pipeline.py::TestHwp`(`test_docx_to_hwp_*`), `test_hwp_table_generation.py`, `test_docx_table_merge.py`(추출 쪽, 사이드카 불요) | JDK+hwplib |
| DOCX→HWPX(표 신규 생성·병합·서식·정렬, 표 셀 안 서식) | DEC-049·DEC-051 | `test_hwpx.py::TestHwpxWrite`(`test_docx_to_hwpx_*`) | JDK+hwpxlib |
| HWP→TXT/PDF/DOCX | REQ-F-005, DEC-027 | `test_pipeline.py::TestHwp`, `test_format_fidelity.py::TestHwpToDocxFormatting` | JDK+hwplib(soffice도 PDF 경로에 필요) |
| HWPX→TXT/PDF/DOCX(머리말·꼬리말·각주·미주·글상자 텍스트 포함) | DEC-044·DEC-052 | `test_hwpx.py::TestHwpx`(`test_hwpx_to_docx_preserves_header_footer_text`·`test_hwpx_to_docx_preserves_nested_shape_text`) | JDK+hwpxlib(soffice도 PDF 경로에 필요) |
| 영상→MP4 | REQ-F-014, DEC-024 | `test_video.py` | ffmpeg |
| 이미지↔이미지 | REQ-F-015, DEC-025 | `test_image.py::TestImageConversion` | 항상(Pillow) |
| 3D 모델↔3D 모델(OBJ/STL/PLY/GLB/GLTF) | DEC-050 | `test_model3d.py::TestModel3DConversion` | 항상(trimesh) |

## UI·플랫폼·부가 기능 커버리지

| 영역 | 관련 REQ/DEC | 테스트 파일 |
|------|--------------|-------------|
| 변환 전 단순화 고지 문구 | DEC-010·017·023·028·037·049·050 | `test_ui_notes.py::TestFormatNote`(17건, 모든 고지 키 조합) |
| 파일 목록 행(FileRow) — 미지원 형식 제거 버튼 | — | `test_ui_filerow.py` |
| 결과 오버레이 — 저장 위치 안내 | REQ-F-008, DEC-042 | `test_ui_result_location.py` |
| 결과 오버레이 — 저해상도 스크롤 | REQ-NF-008, DEC-045 | `test_ui_result_scroll.py` |
| 최소 창 크기(640×480) 레이아웃 충족 | REQ-NF-008, DEC-046·048 | `test_ui_min_size.py` |
| 기록 패널 — 열려있을 때 실시간 갱신 | DEC-041 | `test_ui_history.py` |
| 기록 패널 — 고정폭이 파일 목록을 안 가림 | REQ-NF-008, DEC-047 | `test_ui_history_panel_width.py` |
| 업데이트 확인(옵트인) — UI 통합 | REQ-F-013, DEC-022 | `test_ui_update_notice.py` |
| 업데이트 확인 — 버전 비교·네트워크 실패 처리 | REQ-F-013, DEC-022 | `test_update_check.py` |
| LibreOffice 번들 경로 탐색(macOS) | DEC-029 | `test_office.py` |

## 자동 테스트가 못 잡는 것 → 다른 방법으로 게이트

자동 유닛 테스트가 구조적으로 확인할 수 없는 항목들이다 — "테스트가
없다"가 아니라 "이 방법으로는 검증 불가능해서 다른 수단을 쓴다"는 뜻.

| 항목 | 왜 유닛 테스트로 안 되는지 | 대신 쓰는 방법 |
|------|---------------------------|----------------|
| 실제 한글(HWP)/한워드/MS Word에서 생성 문서가 어떻게 보이는지 | Mac 개발 환경에 그 프로그램들이 없음(DEC-018·DEC-028·DEC-049 공통 제약) | `testing/MANUAL_TEST_CHECKLIST.md` — Windows 실사용자 수동 확인 |
| 쪽 나눔(pageBreakBefore) 등 정식 JSON 스키마에 없는 내부 구조 | HwpToJson/HwpxToJson이 애초에 이 값을 안 읽음(DEC-039·DEC-049) | `PageBreakDebug.java`/`PageBreakDebugHwpx.java`(디버그 전용 도구) — `tests/test_pipeline.py::_run_pagebreakdebug`, `tests/test_hwpx.py::_run_pagebreakdebug_hwpx`로 유닛 테스트에서 직접 호출은 됨(뷰어 렌더링 자체는 여전히 미검증) |
| Windows/macOS 실제 패키징 산출물(exe/dmg) 설치·엔진 실행 | 유닛 테스트는 소스만 다루고 PyInstaller 번들·jlink JRE·인스톨러는 안 만듦 | CI `build-windows`/`build-macos` job의 엔진 스모크 + 인스톨러 스모크(`build.yml`) |
| 완전히 클린한 Windows(사전 설치된 VC++ 런타임 없음)에서의 동작 | CI 러너에는 이미 VC++ 런타임이 있음 | `testing/MANUAL_TEST_CHECKLIST.md` — 실기기 권장 |
| 백신 오탐(SmartScreen/Defender 격리) | 로컬·CI 환경의 백신 정책과 무관 | 실사용 중 관측 시 README/DEC로 사후 대응(DEC-033 선례) |

## 새 기능을 추가할 때

1. 이 표에 새 행(또는 기존 행 확장)을 추가한다 — 어떤 테스트 파일이
   커버하는지, 실행 조건이 뭔지.
2. 유닛 테스트로 못 잡는 부분이 있으면 "자동 테스트가 못 잡는 것" 표에
   추가하고, `testing/MANUAL_TEST_CHECKLIST.md`에도 대응 항목을 넣는다.
3. CI 게이트가 필요한 사이드카 변경(Java 코드)은 `.github/workflows/
   build.yml`의 해당 플랫폼 스모크 스텝에도 회귀 체크를 추가한다(로컬
   dry-run으로 실제 통과를 확인한 뒤 커밋 — 이 프로젝트의 일관된 관례).
