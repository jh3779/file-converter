# 파일 변환기 — 디자인 시스템 문서 (v0.1)

> 2026-07-29 · Material 3 기반 · ColorScheme **"Vault Teal"** (완전 오프라인 보안 → 금고 청록)
> 이 문서 세트는 **시각 토큰·컴포넌트·상태 표현·화면 목업·구현 매핑만** 소유한다.
> 화면 계약·데이터·상태 전이의 정본은 [`../`](../README.md)의 스펙 문서(00~06)다.

## 보는 법
브라우저로 `design-system.html`을 열면 상단 네비로 5개 페이지를 오간다. 우상단 ◐ 버튼으로 라이트/다크 확인.

| 페이지 | 내용 |
|--------|------|
| [design-system.html](design-system.html) | 1 · 디자인 원칙 6개, Vault Teal Light/Dark, 상태색 5종, 타이포(Pretendard+Roboto Mono), 간격/모양/고도/모션 |
| [components.html](components.html) | 2 · 드롭존, 파일 행, 포맷 셀렉트, 버튼, 진행 표시, 결과 패널, 기록 행, 다이얼로그 + **제외 목록** |
| [patterns.html](patterns.html) | 3 · 화면×상태 매트릭스(전 상태), FileItem 5상태 표현, 결과 3변형, 오류 문안 규칙, 원본 보호 표현, 접근성 표 |
| [qt-mapping.html](qt-mapping.html) | 4 · 토큰→QSS, 컴포넌트→PySide6 위젯, 상태머신→스레딩, 변환 엔진 연결 + **Conflict List** |
| [wireframes.html](wireframes.html) | 5 · 흐름도 + 데스크톱 창 목업 7종 (SCR-001 3상태, SCR-002 2변형, SCR-003, 다이얼로그 2종) |

## 핵심 규칙 요약
- tertiary(녹색)는 **"변환 완료" 한 의미에만** 사용. 상태는 색+아이콘+텍스트 3중 부호화.
- 원본을 위협하는 UI(덮어쓰기 질문 등)는 존재 자체 금지 — 자동 리네임 후 사후 보고만.
- 가짜 진행률·완료 선표시·토스트 금지. 실패는 사람 언어 사유 + 재시도 경로.
- 강조 굵기는 SemiBold(600) — 한글 Medium(500) 금지. 수치·포맷명은 Roboto Mono.

## 미결(Conflict List) — 임의 확정하지 않음
OQ-002(자동 업데이트) · OQ-003(PDF→DOCX 기대치 문안) · OQ-004(기록 N) · **OQ-005(결과 오버레이 — 이 문서는 오버레이로 제안, 승인 시 DEC 승격)**. 전체는 [qt-mapping.html](qt-mapping.html) M-05와 [`../06_open_questions.md`](../06_open_questions.md).
