# 04. 데이터 모델

> 인터뷰 영역 6 정리 · 상태: draft

## 엔티티 (ENT-*)
### ENT-001 · ConversionJob (변환 작업 — 변환하기 1회 = 1 Job)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | 작업 ID |
| createdAt | datetime | 시작 시각 |
| status | enum | STATE-001 참조 (running / done / cancelled) |
| items | FileItem[] | 포함된 파일 항목들 |

### ENT-002 · FileItem (파일 항목 — Job 내 파일 1개)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | 항목 ID |
| sourcePath | string | 원본 파일 경로 (읽기 전용 접근) |
| sourceFormat | enum | docx / pptx / pdf / hwp / csv / xlsx / json / avi / mov / mkv / wmv / flv / webm / m4v … |
| targetFormat | enum | 사용자가 선택한 대상 포맷 |
| outputPath | string? | 결과 파일 경로 (완료 후 확정, 충돌 시 자동 리네임 반영) |
| status | enum | STATE-002 참조 (queued / converting / done / failed / skipped) |
| errorReason | string? | 실패 시 사용자용 사유 메시지 |

### ENT-003 · HistoryEntry (최근 기록 — 완료된 FileItem의 요약 스냅샷)
| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | 기록 ID |
| sourceName | string | 원본 파일명 (경로 아님 — 최소 정보만) |
| targetFormat | enum | 대상 포맷 |
| outputPath | string | 결과 파일 경로 |
| convertedAt | datetime | 변환 일시 |
| success | bool | 성공 여부 |

### ENT-004 · AppSettings (앱 설정)
| 필드 | 타입 | 설명 |
|------|------|------|
| historyLimit | int | 기록 보관 건수 (기본 50, 초과 시 오래된 것부터 삭제) |
| language | enum? | UI 언어: null(시스템 따름) / ko / en — 이 두 언어만 지원 (DEC-009) |

## 관계 · 소유 단위
```
ConversionJob 1 ── N FileItem
FileItem(done) ──생성→ HistoryEntry   (완료 시 스냅샷, Job 자체는 미영속)
```
- 소유/공유 단위: **개인 로컬 전용.** 계정·공유·동기화 없음.
- 접근 규칙 요지: 원본 파일은 읽기만, 출력은 새 파일 생성만 (REQ-NF-007).

## 저장 · 동기화
- 저장 위치: HistoryEntry·AppSettings만 로컬(앱 데이터 폴더, SQLite 또는 JSON). ConversionJob/FileItem은 메모리 전용(앱 종료 시 소멸).
- 오프라인 가용성: 전 기능 오프라인 (REQ-NF-002). 외부 전송 없음.
- 변환 중 임시 파일: OS 임시 폴더 사용, 완료 시 결과 위치로 이동, 실패·취소 시 즉시 삭제.
