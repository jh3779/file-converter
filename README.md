# 파일 변환기 (File Converter)

비개발자를 위한 **완전 오프라인** 데스크톱 파일 포맷 변환기. 파일이 PC 밖으로 절대 나가지 않습니다.

> Windows 배포 (v0.3.5 프리릴리스) · macOS 개발 환경 · 사이드 프로젝트 · MVP 완성

## 다운로드

| 플랫폼 | 방법 |
|---|---|
| 🪟 **Windows** | **[v0.3.5 다운로드](https://github.com/jh3779/file-converter/releases/download/v0.3.5/FileConverter-Setup-latest.exe)** — 관리자 권한 불요, 인스톨러 실행 후 안내만 따라가면 끝 (v0.3c·DEC-013). 최신 버전·릴리스 노트는 [Releases](https://github.com/jh3779/file-converter/releases) 참고 |
| 🍎 macOS | 아직 배포판이 없습니다(REQ-NF-001: macOS는 현재 개발 환경 전용). 아래 "실행 방법(개발)"로 소스에서 바로 실행할 수 있습니다 |
| 🐧 Linux | 지원 계획 없음 |

> 유지보수 메모: `.../releases/latest/download/...` 단축 링크는 GitHub이 **pre-release를
> "latest"로 인정하지 않아** 쓸 수 없다(0.x라 `--prerelease`로 발행 — DEC-014). 그래서 위
> 링크는 태그 버전이 URL에 고정되어 있다 — **새 버전을 태그할 때마다 이 표의 URL도 함께
> 갱신할 것**(파일명은 `FileConverter-Setup-latest.exe`로 고정이라 태그 부분만 바꾸면 됨).

## 무엇을 하나
- **문서**: DOCX→PDF · PPTX→PDF · PDF→TXT/DOCX · HWP→PDF/TXT/DOCX · DOCX→HWP (문단 텍스트, 표는 텍스트로 단순화 — DEC-017)
- **데이터**: CSV↔XLSX · CSV↔JSON (한글 인코딩 깨짐 방지)
- **일괄 변환**: 여러 파일을 드래그앤드롭 → 포맷 선택 → 변환, 3클릭 완결
- **원본 절대 보호**: 원본 폴더에 새 파일로 저장, 이름 충돌 시 자동 리네임 — 덮어쓰기 경로 없음
- **한글 글꼴 번들**: PDF/HWP→DOCX로 생성하는 문서는 Noto Sans KR을 항상 명시 지정 —
  **우리 앱 자신의 렌더링 경로**(DOCX/HWP→PDF)에서는 항상 정상 렌더링됨을 검증함.
  결과 DOCX를 사용자의 Word/한글(HWP)에서 직접 열 때는 그 프로그램에 설치된 글꼴에
  따라 달라질 수 있음(DEC-015 — 잔여 리스크로 문서화)
- **업데이트 확인(선택, 기본 꺼짐)**: 설정(⚙)에서 켜면 GitHub에 **버전 번호만** 조회해
  새 버전이 있을 때 조용히 안내 — 자동 다운로드·설치 없음, 파일·경로 등은 절대 전송하지
  않음(DEC-022)

## 기술 스택 (확정)
Python + PySide6(Qt) · PyInstaller 패키징 · **LibreOffice 26.2.5 엔진 번들**(DOCX/PPTX→PDF·HWP→PDF, SHA256 검증) · **Noto Sans KR**(OFL-1.1, 한글 글꼴 번들) · **hwplib**(Apache-2.0) + JRE 사이드카(HWP) — 근거는 [docs/06_open_questions.md](docs/06_open_questions.md) 결정 로그(DEC) 참조.

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
- [x] v0.3.1 — **실사용 Windows 테스트 피드백 반영**: PDF/HWP→DOCX 글자 깨짐·DOCX→PDF 일부 문자 삭제의 근본 원인(한글 글꼴 미지정 + 번들 LibreOffice의 CJK 글꼴 0개)을 확정해 수정, Noto Sans KR 글꼴 번들(DEC-015). **보장 범위는 우리 앱 자신의 렌더링 경로(DOCX/HWP→PDF)로 한정** — 실사용자가 결과 DOCX를 자신의 Word/한글(HWP)에서 직접 열 때의 렌더링은 그 프로그램의 글꼴 대체 로직에 의존하는 잔여 리스크로 문서화됨(대체 글꼴명 지정 시도는 로컬 검증에서 회귀가 발견돼 채택하지 않음). **PPTX→PDF 신규 지원**(DEC-016)
- [x] v0.3.2 — CSV→JSON 변환 시 셀 안 줄바꿈·이스케이프된 큰따옴표가 있으면 값이 잘리던 버그 수정(`csv.Sniffer`가 인용 규칙까지 오탐하던 것이 원인) — 재현 테스트 추가. **DOCX→HWP 신규 지원**(DEC-017, DEC-003 일부 번복) — hwplib로 HWP 파일을 새로 생성하는 사이드카(`JsonToHwp.java`) 추가. 문단 텍스트는 그대로 보존되고, 자동 번호("1.")·불릿("•")도 numbering.xml을 해석해 마커로 보존(코드 리뷰 지적 반영). 표는 hwplib에 신규 생성 도구가 없어 각 행을 텍스트 한 줄로 안전하게 단순화(내용 유실 없음, 변환 전 UI 고지)
- [x] v0.3.3 — **DOCX→HWP 레이아웃(형태) 깨짐 수정**(DEC-018): 실사용 보고 원인을 hwplib 실제 샘플 문서 구조와 대조해 확정 — 문단 길이와 무관하게 항상 레이아웃 캐시(LineSeg)를 1개만·세로 위치를 0으로 고정 생성하던 버그. 문단 텍스트 길이에 맞춰 줄바꿈을 계산하고 문단 간 세로 위치를 누적하도록 수정, 테스트 전용 도구로 구조까지 검증(실제 외부 뷰어 렌더링은 Mac 개발 환경 특성상 아직 미검증 — 잔여 리스크). **XLSX→CSV 값 표시 형식 정리 + 다중 시트 고지 추가**(DEC-019): 날짜·정수값 표시를 엑셀에서 보던 모습에 맞춰 정규화, 시트가 여러 개면 변환 전 고지(첫 시트만 변환됨을 조용히 넘기지 않음), `wb.active`(활성 탭)와 "첫 번째 시트" 고지 문구가 어긋나던 버그도 함께 수정
- [x] v0.3.4 — v0.3.3 실사용 테스트 피드백: HWP→PDF/DOCX 텍스트 보존 정상 확인(표만 의도한 대로 단순화). **지원 안 되는 파일의 ✕(제거) 버튼이 클릭에 반응하지 않던 버그 수정**(DEC-020) — 행 전체를 비활성화하면서 Qt의 부모-자식 활성 상태 전파로 제거 버튼 클릭까지 막혀 있었음. **일괄 변환 시 결과물이 조용히 덮어써지던 경쟁 상태 수정**(DEC-021) — 같은 이름으로 끝나는 두 파일이 동시에 변환 완료되면 파일명 충돌 검사가 원자적이지 않아 한쪽이 다른 쪽을 덮어쓸 수 있었음(REQ-F-008 "덮어쓰기 경로 없음" 위반, 스트레스 테스트로 재현 후 수정). 숨은 오류 점검 목적의 코드 감사로 발견
- [x] v0.3.5 — **업데이트 확인 기능 추가, 옵트인·기본 꺼짐**(REQ-F-013, DEC-022 — 기획 초기부터 미결이던 OQ-002 해결): 설정에서 켜면 GitHub Releases에 버전 번호만 조회, 새 버전이 있으면 조용히 안내(클릭 시 릴리스 페이지로 이동). 자동 다운로드·설치 없음, 파일·경로·식별 정보 미전송 — 오프라인·요청 실패 시 조용히 무시. 릴리스 전 최종 점검 중 발견한 사소한 버그(알림이 떠 있는 채로 언어 전환 시 텍스트 미갱신)도 함께 수정

## 라이선스 고지
- HWP 처리: [neolord0/hwplib](https://github.com/neolord0/hwplib) (Apache License 2.0)
- 문서 변환 엔진: [LibreOffice](https://www.libreoffice.org) 26.2.5 (Mozilla Public License 2.0)
- 한글 글꼴: [Noto Sans KR](https://github.com/notofonts/noto-cjk) (SIL Open Font License 1.1)
- 전문은 배포판 `THIRD_PARTY_NOTICES.txt` 참조
