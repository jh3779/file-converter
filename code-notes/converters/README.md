# app/converters/ 코드 노트 — 인덱스

`app/converters/` 전체(16개 파일, 2642줄)에 대한 파일별 상세 설명
문서. 각 문서는 "의미 단위 블록 + 정확한 라인 번호"로 구성돼 있고,
끝에 스스로 점검할 수 있는 질문을 붙여뒀다. 원본 코드가 바뀌면 이
노트도 낡을 수 있으니, 실제 동작이 궁금하면 항상 `app/converters/`의
원본 파일을 함께 열어 대조할 것.

## 읽는 순서 추천 (기초 → 응용)

| 순서 | 파일 | 노트 | 무엇을 다루는가 |
|---|---|---|---|
| 1 | `base.py` | [base.md](base.md) | 모든 컨버터의 공용 기반 — `ConversionError`, 인코딩 자동 감지 |
| 2 | `__init__.py` | [__init__.md](__init__.md) | 변환기 레지스트리 — `TARGETS`/`_DISPATCH`, 패키지의 공개 API 3개 함수 |
| 3 | `data.py` | [data.md](data.md) | CSV↔XLSX, CSV↔JSON |
| 4 | `markup.py` | [markup.md](markup.md) | TXT/MD/HTML 6방향 상호 변환 |
| 5 | `image.py` | [image.md](image.md) | 이미지 상호 변환(Pillow) — EXIF·알파 합성·애니메이션 |
| 6 | `model3d.py` | [model3d.md](model3d.md) | 3D 모델(OBJ/STL/PLY/GLB/GLTF) 상호 변환(trimesh) |
| 7 | `video.py` | [video.md](video.md) | 영상→MP4(FFmpeg 서브프로세스) — 스트림 카피/재인코딩 |
| 8 | `office.py` | [office.md](office.md) | DOCX/PPTX→PDF(LibreOffice 서브프로세스) |
| 9 | `docx_build.py` | [docx_build.md](docx_build.md) | "구조 블록(blocks JSON)" → DOCX 생성 — HWP/HWPX/PDF→DOCX 공용 |
| 10 | `hwp.py` | [hwp.md](hwp.md) | HWP 변환(Java 사이드카 호출) — `_run_sidecar`의 정본 |
| 11 | `hwpx.py` | [hwpx.md](hwpx.md) | HWPX 변환 — hwp.py와 거의 완전 대칭 |
| 12 | `pdf.py` | [pdf.md](pdf.md) | PDF 읽기 공유 프리미티브(정렬 추정·서식 감지·도형 추출) + PDF→TXT/이미지 |
| 13 | `pdf_docx.py` | [pdf_docx.md](pdf_docx.md) | PDF→DOCX — 줄 단위 절대 위치(`w:framePr`) 재구성 |
| 14 | `docx_extract.py` | [docx_extract.md](docx_extract.md) | DOCX → "구조 블록" — docx_build.py의 역방향, 번호 매기기·병합 감지 |
| 15 | `pdf_pptx.py` | [pdf_pptx.md](pdf_pptx.md) | PDF→PPTX — python-pptx 셰이프 API로 재구성 |

(참고: `docx_extract.py`를 14번에 둔 이유는 `hwp.py`/`hwpx.py`의
`docx_to_hwp`/`docx_to_hwpx`가 이 파일을 호출한다는 걸 먼저 안 뒤에
보는 게 맥락이 잡히기 때문. `pdf.py`→`pdf_docx.py`→`docx_extract.py`
→`pdf_pptx.py` 순서로 읽어도 무방하다.)

## 전체 그림 — 어떤 파일이 어떤 파일을 부르는가

```
__init__.py (TARGETS/_DISPATCH 레지스트리)
  ├─ data.py, markup.py, image.py, model3d.py, video.py, office.py
  │    (각자 독립적으로 완결됨)
  │
  ├─ hwp.py ──┬─ docx_build.py (HWP→DOCX)
  │           ├─ docx_extract.py (DOCX→HWP)
  │           ├─ pdf.py._extract_pdf_blocks_by_page (PDF→HWP)
  │           └─ office.py (HWP→PDF, DOCX 경유)
  │
  ├─ hwpx.py ─┤ (hwp.py의 _run_sidecar를 그대로 재사용, 나머지는 hwp.py와 대칭)
  │
  ├─ pdf.py (저수준 추출 프리미티브 — 다른 pdf_*.py가 공유)
  │    ├─ pdf_docx.py (PDF→DOCX, w:framePr)
  │    └─ pdf_pptx.py (PDF→PPTX, 셰이프 API)
  │
  └─ base.py (ConversionError, 인코딩 자동 감지 — 전 파일 공용)
```

## 자주 등장하는 공통 패턴 (한 번 알아두면 여러 파일에서 반복 확인됨)

- **지연 초기화(lazy import)**: 거의 모든 파일이 무거운 서드파티
  라이브러리(openpyxl, PIL, docx, pptx, markdown, bs4 등)를 모듈
  최상단이 아니라 **함수 안에서** import한다 — 앱 시작 시간 단축.
- **`ConversionError(key, detail)`로 실패를 통일**: 어떤 컨버터도
  raw `ValueError`/`RuntimeError`를 직접 던지지 않는다(`base.md`
  참고).
- **"blocks JSON" 중간 표현**: HWP/HWPX/PDF→DOCX 경로가 전부
  `docx_build.py`의 스키마를 공유한다(`docx_build.md`의 L1-35 참고)
  — 이 스키마를 이해하면 4개 파일(`docx_build.py`, `docx_extract.py`,
  `hwp.py`, `hwpx.py`)의 데이터 흐름이 한 번에 이해된다.
- **외부 엔진 탐색 3~4단계 패턴**: `find_soffice()`(office.py),
  `find_ffmpeg()`(video.py), `_java()`(hwp.py)가 전부
  "환경변수 → 번들 경로 → 시스템 PATH (→ 하드코딩 폴백)" 순서를
  공유한다.
- **재현된 버그가 주석으로 남아있는 경우가 많음**: 이 프로젝트는
  "왜 지금 이 코드가 이 모양인지"를 코드 리뷰·자동 리뷰가 지적한
  실제 버그와 그 재현 사례로 설명하는 관례가 있다 — 각 노트에서
  "재현된 버그"라고 표시한 부분을 눈여겨보면 이 프로젝트의 검증
  방식(로컬 재현 우선)을 알 수 있다.
