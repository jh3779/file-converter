# 파일 확장자 변환기 — 정본 스펙 문서

> 2026-07-29 discovery 인터뷰 결과. 이후 UI 설계·구현은 이 문서들의 ID(REQ/SCR/FLOW/STATE/ENT/DEC)를 근거로 참조한다.

| 문서 | 내용 |
|------|------|
| [00_project_brief.md](00_project_brief.md) | 문제·목표·사용자·핵심 가치(완전 오프라인)·품질 기준 |
| [01_requirements.md](01_requirements.md) | MoSCoW 범위, 기능(REQ-F)·비기능(REQ-NF) 요구사항, 제약 |
| [02_ui_flow.md](02_ui_flow.md) | 화면 목록(SCR), 핵심 플로우(FLOW), 네비게이션 |
| [03_screen_contract.md](03_screen_contract.md) | 화면별 가시 의무·행동·상태·금지 사항 |
| [04_data_model.md](04_data_model.md) | 엔티티(ENT): Job·FileItem·History·Settings |
| [05_state_machine.md](05_state_machine.md) | 상태(STATE)·전이·불변식(원본 비수정 등) |
| [06_open_questions.md](06_open_questions.md) | 미결정(OQ)·가정(ASM)·결정 로그(DEC)·리스크 |
| [07_test_plan.md](07_test_plan.md) | 자동 테스트 커버리지 지도 — 변환 경로·UI별 테스트 파일 대응표, 유닛 테스트로 못 잡는 항목과 대신 쓰는 검증 수단(수동 체크리스트는 [testing/MANUAL_TEST_CHECKLIST.md](../testing/MANUAL_TEST_CHECKLIST.md)) |
| [design-system/](design-system/README.md) | UI 디자인 시스템 v0.1 — Vault Teal 토큰·컴포넌트·상태 패턴·PySide6 매핑·와이어프레임 (HTML, 브라우저로 열람) |

**한 줄 요약:** 비개발자용 완전 오프라인 데스크톱 변환기 (Windows·macOS·Linux) — 문서(DOCX/PDF↔HWP/HWPX, DOCX/PPTX→PDF, PDF→TXT/DOCX/PPTX/이미지) + 데이터(CSV↔XLSX, CSV↔JSON) + 마크업(TXT/MD/HTML 상호 변환) + 영상(→MP4, H.264/HEVC만) + 이미지(JPG/PNG/BMP/GIF/WEBP/TIFF 상호 변환) + 3D 모델(OBJ/STL/PLY/GLB/GLTF 상호 변환), 원스크린 드롭존, 일괄 변환, 원본 절대 보호. 스택: Python + PySide6 + LibreOffice·FFmpeg·Pillow·trimesh (DEC-001).
