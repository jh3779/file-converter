# 파일 변환기 (File Converter)

비개발자를 위한 **완전 오프라인** 데스크톱 파일 포맷 변환기. 파일이 PC 밖으로 절대 나가지 않습니다.

> Windows 배포 (v0.3.0 프리릴리스) · macOS 개발 환경 · 사이드 프로젝트 · MVP 완성

## 다운로드

| 플랫폼 | 방법 |
|---|---|
| 🪟 **Windows** | **[v0.3.0 다운로드](https://github.com/jh3779/file-converter/releases/download/v0.3.0/FileConverter-Setup-latest.exe)** — 관리자 권한 불요, 인스톨러 실행 후 안내만 따라가면 끝 (v0.3c·DEC-013). 최신 버전·릴리스 노트는 [Releases](https://github.com/jh3779/file-converter/releases) 참고 |
| 🍎 macOS | 아직 배포판이 없습니다(REQ-NF-001: macOS는 현재 개발 환경 전용). 아래 "실행 방법(개발)"로 소스에서 바로 실행할 수 있습니다 |
| 🐧 Linux | 지원 계획 없음 |

> 유지보수 메모: `.../releases/latest/download/...` 단축 링크는 GitHub이 **pre-release를
> "latest"로 인정하지 않아** 쓸 수 없다(0.x라 `--prerelease`로 발행 — DEC-014). 그래서 위
> 링크는 태그 버전이 URL에 고정되어 있다 — **새 버전을 태그할 때마다 이 표의 URL도 함께
> 갱신할 것**(파일명은 `FileConverter-Setup-latest.exe`로 고정이라 태그 부분만 바꾸면 됨).

## 무엇을 하나
- **문서**: DOCX→PDF · PDF→TXT/DOCX · HWP→PDF/TXT/DOCX (읽기 전용)
- **데이터**: CSV↔XLSX · CSV↔JSON (한글 인코딩 깨짐 방지)
- **일괄 변환**: 여러 파일을 드래그앤드롭 → 포맷 선택 → 변환, 3클릭 완결
- **원본 절대 보호**: 원본 폴더에 새 파일로 저장, 이름 충돌 시 자동 리네임 — 덮어쓰기 경로 없음

## 기술 스택 (확정)
Python + PySide6(Qt) · PyInstaller 패키징 · **LibreOffice 26.2.5 엔진 번들**(DOCX→PDF·HWP→PDF, SHA256 검증) · **hwplib**(Apache-2.0) + JRE 사이드카(HWP) — 근거는 [docs/06_open_questions.md](docs/06_open_questions.md) 결정 로그(DEC) 참조.

## 저장소 구조
```
docs/                  정본 스펙 문서 (기획 인터뷰 산출물)
  00_project_brief.md    문제·목표·핵심 가치
  01_requirements.md     MoSCoW·기능/비기능 요구사항
  02_ui_flow.md          화면·플로우
  03_screen_contract.md  화면별 계약
  04_data_model.md       엔티티
  05_state_machine.md    상태·전이·불변식
  06_open_questions.md   미결정·가정·결정 로그·리스크
  design-system/         UI 디자인 시스템 v0.1 (HTML — 브라우저로 열람)
spike/hwplib/          HWP 라이브러리 기술 검증 (결과: RESULT.md)
research/hwp-coverage/ 실사용 HWP 문서 커버리지 검증 (결과: RESULT.md)
packaging/             배포 자산 — 아이콘, 인스톨러 스크립트, 버전, 제3자 고지
```

## 실행 방법 (개발)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.main          # 앱 실행
.venv/bin/python -m unittest discover tests   # 테스트
sh sidecar/hwp/build.sh               # HWP 사이드카 빌드 (JDK + spike 빌드 필요)
```
- UI 언어: 한국어/영어 (⚙ 메뉴에서 전환, 기본은 시스템 언어 — DEC-009)
- DOCX→PDF·HWP→PDF는 LibreOffice 필요 — 개발 환경은 시스템 설치본 자동 탐지
  (`FILECONV_SOFFICE` 환경변수로 위치 지정 가능), Windows 배포판은 `engine/libreoffice/`에 번들(DEC-012)

## 현재 상태
- [x] 제품 기획·요구사항 정의 (discovery 인터뷰)
- [x] hwplib 기술 스파이크 — 통과 ([spike/hwplib/RESULT.md](spike/hwplib/RESULT.md))
- [x] UI 디자인 시스템 v0.1 ([docs/design-system/](docs/design-system/README.md))
- [x] MVP 앱 스캐폴드 — PySide6 UI(3화면·오버레이·기록·i18n), CSV↔XLSX/CSV↔JSON/PDF→TXT/DOCX→PDF/HWP→TXT 동작
- [x] v0.2 파이프라인 — HWP→DOCX(구조 JSON, 표 보존)·HWP→PDF(DOCX→LibreOffice)·PDF→DOCX(텍스트 기반, DEC-010 고지)
- [x] CI — GitHub Actions: ubuntu 테스트 + Windows exe 빌드(아티팩트)
- [x] v0.3a — Windows 빌드에 HWP 엔진 번들(jlink JRE + hwplib 클래스): **HWP→TXT/DOCX가 Java 설치 없이 동작** (HWP→PDF·DOCX→PDF는 v0.3b 전까지 시스템 LibreOffice 자동 탐지 필요)
- [x] 실사용 HWP 커버리지 검증(TXT·DOCX) — 공공기관 서식 5건 + 배포용 문서 1건, 6/6 성공. **HWP→PDF는 미검증**(LibreOffice 필요, v0.3b 이후) ([research/hwp-coverage/RESULT.md](research/hwp-coverage/RESULT.md))
- [x] v0.3b — Windows 빌드에 **LibreOffice 26.2.5 번들**(버전 고정·SHA256 검증·MPL 2.0 고지): **DOCX→PDF·HWP→PDF가 Java·LibreOffice 설치 없이 동작**. CI가 매 PR마다 실제 exe 위치를 흉내낸 프로즌 모드 자동 탐색(환경변수 없음) + 두 파이프라인 전체 변환 + PDF 내용(pdfminer)까지 검증(DEC-012) — [PR #4 CI 통과 기록](https://github.com/jh3779/file-converter/actions/runs/30458685792)
- [x] v0.3c — **Inno Setup 인스톨러**(관리자 권한 불요·한/영 지원·전용 아이콘, 394MB): CI가 무인 설치→설치된 실경로에서 exe 실행→무인 제거까지 전 과정을 매 PR 게이트로 검증하고 통과(DEC-013) — [PR #5 CI 통과 기록](https://github.com/jh3779/file-converter/actions/runs/30461638374). 완전 클린 Windows(VC++ 런타임 부재) 실기기 검증만 별도로 남음

## 라이선스 고지
- HWP 처리: [neolord0/hwplib](https://github.com/neolord0/hwplib) (Apache License 2.0)
- 문서 변환 엔진: [LibreOffice](https://www.libreoffice.org) 26.2.5 (Mozilla Public License 2.0) — 전문은 배포판 `THIRD_PARTY_NOTICES.txt` 참조
