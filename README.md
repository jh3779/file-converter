# 파일 변환기 (File Converter)

비개발자를 위한 **완전 오프라인** 데스크톱 파일 포맷 변환기. 파일이 PC 밖으로 절대 나가지 않습니다.

> Windows 우선 배포 · macOS 개발 환경 · 사이드 프로젝트 · 기획 단계

## 무엇을 하나
- **문서**: DOCX→PDF · PDF→TXT/DOCX · HWP→PDF/TXT/DOCX (읽기 전용)
- **데이터**: CSV↔XLSX · CSV↔JSON (한글 인코딩 깨짐 방지)
- **일괄 변환**: 여러 파일을 드래그앤드롭 → 포맷 선택 → 변환, 3클릭 완결
- **원본 절대 보호**: 원본 폴더에 새 파일로 저장, 이름 충돌 시 자동 리네임 — 덮어쓰기 경로 없음

## 기술 스택 (확정)
Python + PySide6(Qt) · PyInstaller 패키징 · LibreOffice 엔진 번들(DOCX→PDF) · **hwplib**(Apache-2.0) + JRE 사이드카(HWP) — 근거는 [docs/06_open_questions.md](docs/06_open_questions.md) 결정 로그(DEC) 참조.

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
```

## 실행 방법 (개발)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.main          # 앱 실행
.venv/bin/python -m unittest discover tests   # 테스트
sh sidecar/hwp/build.sh               # HWP 사이드카 빌드 (JDK + spike 빌드 필요)
```
- UI 언어: 한국어/영어 (⚙ 메뉴에서 전환, 기본은 시스템 언어 — DEC-009)
- DOCX→PDF는 LibreOffice 필요(개발: 시스템 설치본 자동 탐지, 배포: 번들 예정)

## 현재 상태
- [x] 제품 기획·요구사항 정의 (discovery 인터뷰)
- [x] hwplib 기술 스파이크 — 통과 ([spike/hwplib/RESULT.md](spike/hwplib/RESULT.md))
- [x] UI 디자인 시스템 v0.1 ([docs/design-system/](docs/design-system/README.md))
- [x] MVP 앱 스캐폴드 — PySide6 UI(3화면·오버레이·기록·i18n), CSV↔XLSX/CSV↔JSON/PDF→TXT/DOCX→PDF/HWP→TXT 동작
- [x] v0.2 파이프라인 — HWP→DOCX(구조 JSON, 표 보존)·HWP→PDF(DOCX→LibreOffice)·PDF→DOCX(텍스트 기반, DEC-010 고지)
- [x] CI — GitHub Actions: ubuntu 테스트 + Windows exe 빌드(아티팩트)
- [x] v0.3a — Windows 빌드에 HWP 엔진 번들(jlink JRE + hwplib 클래스): HWP 변환이 설치 없이 동작
- [ ] v0.3b — LibreOffice 번들 + 설치 파일(인스톨러)
- [ ] 실사용 HWP 커버리지 검증 (OQ-006)

## 라이선스 고지
HWP 처리는 [neolord0/hwplib](https://github.com/neolord0/hwplib) (Apache License 2.0)을 사용할 예정입니다.
