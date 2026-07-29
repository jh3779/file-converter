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

## 현재 상태
- [x] 제품 기획·요구사항 정의 (discovery 인터뷰)
- [x] hwplib 기술 스파이크 — 통과 ([spike/hwplib/RESULT.md](spike/hwplib/RESULT.md))
- [x] UI 디자인 시스템 v0.1 ([docs/design-system/](docs/design-system/README.md))
- [ ] 앱 구현 (MVP)

## 라이선스 고지
HWP 처리는 [neolord0/hwplib](https://github.com/neolord0/hwplib) (Apache License 2.0)을 사용할 예정입니다.
