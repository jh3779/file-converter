# 05. 상태 머신 (State Machine)

> 인터뷰 영역 6 정리 — 시간에 따라 변하는 대상의 상태·전이 · 상태: draft

## STATE-001 · ConversionJob (일괄 변환 작업)
### 상태값
| 상태 | 의미 | 사용자 표현 |
|------|------|-------------|
| running | 하나 이상의 FileItem이 진행 중 | 전체 진행률 + 파일별 상태 |
| done | 모든 FileItem 종료(성공/실패/건너뜀 포함) | SCR-002 결과 요약 |
| cancelled | 사용자가 취소 | "취소됨 — 완료된 파일은 유지되었습니다" |

### 전이
```
(변환하기) → running ──[모든 항목 종료]→ done
                └──[취소]→ cancelled  (완료분 유지, 진행분 임시파일 삭제)
```

## STATE-002 · FileItem (파일 1개의 변환)
### 상태값
| 상태 | 의미 | 사용자 표현 |
|------|------|-------------|
| queued | 대기 중 | "대기 중" |
| converting | 변환 진행 중 | 스피너/진행 표시 |
| done | 성공, outputPath 확정 | ✓ 완료 |
| failed | 실패, errorReason 보유 | ✗ + 사람이 읽을 수 있는 사유 |
| skipped | 취소로 실행되지 않음 | "건너뜀" |

### 전이
```
queued ──[차례 도달]→ converting ──[성공]→ done
                          └──[오류]→ failed          (Job은 계속 진행 — REQ-F-009)
queued ──[Job 취소]→ skipped
converting ──[Job 취소]→ failed(사유: 취소) + 임시파일 삭제
failed ──[재시도(결과 화면 복귀 후 다시 변환하기)]→ queued
```

### 불변식 (INV)
- INV-01: **원본 파일은 어떤 상태·전이에서도 수정되지 않는다** (REQ-NF-007). 출력은 항상 새 경로.
- INV-02: done 이전에 성공을 선표시하지 않는다. outputPath는 파일이 실제로 존재할 때만 확정.
- INV-03: failed는 반드시 errorReason(사용자 언어)과 함께 노출되고, 재시도 경로가 제공된다.
- INV-04: 한 항목의 failed가 다른 항목의 진행을 막지 않는다 (계속 진행 원칙).
- INV-05: 이름 충돌 시 자동 리네임 — 기존 파일을 덮어쓰는 전이는 존재하지 않는다.
