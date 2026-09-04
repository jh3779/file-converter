# __init__.py — 변환기 레지스트리 (전체를 하나로 묶는 진입점)

원본: `app/converters/__init__.py` (112줄)

이 파일은 `app/converters/` 패키지의 공개 API 전부다. 다른 코드(`app/workers.py`,
`app/ui/main_window.py`)는 개별 컨버터 파일(`pdf.py`, `hwp.py` 등)을 직접 import
하지 않고, 오직 이 파일이 노출하는 3개 함수(`supported`, `targets_for`, `convert`)
만 사용한다 — 이게 "패키지의 얼굴"이다. 핵심은 **두 개의 dict**
(`TARGETS`, `_DISPATCH`)이고, 나머지 코드는 전부 이 두 dict를 채우거나 조회하는
역할만 한다.

---

## L1-5: 모듈 docstring

```
TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
```

"가능한 것만 노출"(원칙 C-03)이 이 파일 전체를 관통하는 설계 원칙이다. 예를 들어
FFmpeg가 없는 배포판(macOS)에서는 영상 확장자 자체가 `TARGETS`에 안 들어간다
(L34-37) — UI가 "지원 안 함" 에러를 보여주는 게 아니라, 애초에 그 옵션 자체가
안 보이게 만든다.

## L6-10: import

```python
from functools import partial
from pathlib import Path

from .base import ConversionError
from . import data, pdf, pdf_docx, pdf_pptx, office, hwp, hwpx, video, image, model3d, markup
```

- `partial`(functools): L72-73, L86-90에서 "같은 함수를 인자 하나만 다르게 해서
  여러 dict 키에 등록"할 때 쓴다. 예: `pdf_to_images`는 `ext` 파라미터가 있는데,
  `("pdf","png")`와 `("pdf","jpg")` 둘 다 이 함수를 쓰되 `ext`만 다르게 고정해서
  등록해야 하므로 `partial(pdf.pdf_to_images, ext="png")`처럼 미리 인자를 박아둔
  새 함수를 만든다.
- `from . import data, pdf, ...`: 이 패키지 안의 **모든 컨버터 모듈을 한 번에**
  import한다. 이 한 줄이 "새 포맷을 추가하려면 여기 이름을 추가해야 한다"는
  최초 진입점이다.

## L12-21: `TARGETS`의 정적(고정) 부분

```python
TARGETS: dict[str, list[str]] = {
    "docx": ["pdf", "hwp", "hwpx"],
    "pptx": ["pdf"],
    "pdf": ["txt", "docx", "hwp", "hwpx", "png", "jpg", "pptx"],
    "hwp": ["txt", "pdf", "docx"],
    "hwpx": ["txt", "pdf", "docx"],
    "csv": ["xlsx", "json"],
    "xlsx": ["csv"],
    "json": ["csv"],
}
```

- 키는 **소스 확장자**(소문자, 점 없음), 값은 **그 확장자에서 변환 가능한 대상
  확장자 리스트**다.
- 이 dict가 UI 계층에서 "이 파일을 넣으면 어떤 포맷으로 바꿀 수 있는지" 드롭다운을
  채우는 데 그대로 쓰인다(`app/ui/main_window.py`가 `targets_for()`를 호출).
- 비대칭에 주목: `docx→[pdf,hwp,hwpx]`이지만 `pdf→[...]`에는 `hwpx`가 있어도
  `docx`가 없다(PDF→DOCX는 되지만 나열이 다른 순서 — 실제로는 있다,
  `"pdf": [... "docx" ...]`). `pptx→[pdf]`뿐이고 `pdf→pptx`도 있지만
  `pptx`는 다른 포맷을 받지 않는다 — 즉 이 dict는 "모든 포맷이 서로 변환
  가능"이 아니라 **실제로 구현된 방향만** 정직하게 나열한 것이다. 이후
  L39-62의 3개 블록(이미지·3D·마크업)과 대비된다 — 그것들은 "포맷 집합 내
  전원이 서로 변환 가능"이라 반복 루프로 자동 생성되지만, 문서/데이터 포맷은
  방향마다 사정이 달라 손으로 하나씩 나열했다.

## L23-37: 영상 포맷 — **런타임에 조건부로 TARGETS에 추가**

```python
_VIDEO_EXTS = ("avi", "mov", "mkv", "wmv", "flv", "m4v")
...
if video.find_ffmpeg() is not None:
    for _ext in _VIDEO_EXTS:
        TARGETS[_ext] = ["mp4"]
    del _ext
```

- 이 블록이 이 파일에서 가장 중요한 설계 포인트다: `TARGETS`는 **모듈 로드
  시점에 한 번, 실행 환경을 보고 동적으로 결정**된다. `video.find_ffmpeg()`가
  번들된 FFmpeg 바이너리(또는 시스템 설치본)를 찾으면 그때만 영상 확장자들이
  `TARGETS`에 들어간다.
- macOS 배포판은 FFmpeg를 아예 번들하지 않으므로(L29-30 주석, DEC-029), 이
  `if`가 거짓이 되어 영상 확장자들이 `TARGETS`에 **전혀 없다** — 즉 macOS
  사용자는 UI에서 영상 파일을 넣어도 "지원하지 않는 형식"으로 취급된다
  (엉뚱하게 "재설치하세요"라는 오류가 뜨는 게 아니라).
- `del _ext`: 반복문 변수가 모듈 전역 네임스페이스에 남아 있으면 다른 코드에서
  실수로 `converters._ext`를 참조할 수 있으므로 정리한다. 이 파일 전체에서
  반복되는 패턴(L47 `del _src`, L55, L62도 동일)이다 — 이건 이 모듈이
  "함수 본문"이 아니라 "모듈 최상위 스크립트"라서, 지역 변수 스코프가 없어
  루프 변수가 그대로 새어나가기 때문에 생기는 파이썬 특유의 습관이다.
- **webm 제외 이유(L26-28)**: 표준 WEBM 컨테이너는 VP8/VP9/AV1 코덱만 담을 수
  있는데, 이 프로젝트의 영상 변환은 H.264/HEVC(또는 그 재인코딩)만 다룬다
  (DEC-024) — 즉 webm을 "지원 포맷"으로 노출해도 사실상 항상 변환에 실패할
  것이므로, 애초에 노출하지 않는다. 이것도 "가능한 것만 노출"(C-03) 원칙의
  적용 사례로, 코드 리뷰에서 지적돼 빠진 것이라고 주석에 남아 있다.

## L39-47: 이미지 — "자기 자신 제외 상호 변환" 패턴

```python
_IMAGE_SRC_EXTS = ("jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff")
_IMAGE_CANON = {"jpg": "jpg", "jpeg": "jpg", "png": "png", ...}
_IMAGE_TARGET_EXTS = ("jpg", "png", "bmp", "gif", "webp", "tiff")
for _src in _IMAGE_SRC_EXTS:
    TARGETS[_src] = [t for t in _IMAGE_TARGET_EXTS if t != _IMAGE_CANON[_src]]
del _src
```

- `_IMAGE_SRC_EXTS`(7개: jpg/jpeg 둘 다 포함)와 `_IMAGE_TARGET_EXTS`(6개:
  jpg만, jpeg 없음)가 다르다는 게 핵심. jpg와 jpeg는 **같은 포맷(JPEG)의
  다른 확장자**일 뿐이므로, "jpeg 파일을 jpg로 변환"하는 옵션은 의미가 없어
  대상 목록에서 jpeg 자체를 뺐다(`_IMAGE_CANON`이 jpg/jpeg를 모두 `"jpg"`로
  정규화).
- `_IMAGE_CANON[_src]`로 "이 소스의 정규화된 이름"을 구해서, 대상 리스트에서
  자기 자신(정규화 기준)만 제외한다. 예: `_src="jpeg"`일 때
  `_IMAGE_CANON["jpeg"]=="jpg"`이므로 대상에서 `"jpg"`가 빠진다 — 즉 jpeg는
  jpg로도 변환 못 하게 막힌다(같은 포맷이므로 무의미한 변환이라 판단).
- 결과적으로 `TARGETS["png"] = ["jpg","bmp","gif","webp","tiff"]`처럼, 자기
  자신을 뺀 나머지 전부가 대상이 된다 — "포맷 집합 내 전원이 서로 변환
  가능"이라는 패턴의 전형.

## L49-55: 3D 모델 — 같은 패턴, 더 단순한 버전

```python
_MODEL3D_EXTS = ("obj", "stl", "ply", "glb", "gltf")
for _src in _MODEL3D_EXTS:
    TARGETS[_src] = [t for t in _MODEL3D_EXTS if t != _src]
del _src
```

- 이미지와 달리 "정규화" 개념이 필요 없다(각 확장자가 서로 다른 포맷이므로) —
  단순히 `t != _src`(자기 자신만 제외)로 충분하다.
- 5개 포맷 × 나머지 4개 = 20개 조합이 이 3줄로 자동 생성된다. 주석(L49-51)에
  "스파이크로 20쌍 전 조합의 정점·면·부피 보존을 확인했다"는 근거가 남아
  있다 — 즉 이 자동 생성된 20개 조합이 전부 실제로 검증됐다는 뜻.

## L57-62: TXT/MD/HTML — 같은 패턴 세 번째

3D 모델과 똑같은 구조(3개 포맷, 자기 자신 제외). 6방향(3×2)이 여기서 나온다.

## L64-97: `_DISPATCH` — "(소스,대상) → 실제 변환 함수" 매핑

```python
_DISPATCH = {
    ("csv", "xlsx"): data.csv_to_xlsx,
    ...
    ("pdf", "png"): partial(pdf.pdf_to_images, ext="png"),
    ("pdf", "jpg"): partial(pdf.pdf_to_images, ext="jpg"),
    ...
    **{(ext, "mp4"): video.video_to_mp4 for ext in _VIDEO_EXTS},
    **{(src, tgt): partial(image.convert_image, target_ext=tgt)
       for src in _IMAGE_SRC_EXTS for tgt in TARGETS[src]},
    **{(src, tgt): partial(model3d.convert_3d, target_ext=tgt)
       for src in _MODEL3D_EXTS for tgt in TARGETS[src]},
    ...
}
```

`TARGETS`가 "무엇이 가능한지"를 나타낸다면, `_DISPATCH`는 "그걸 실제로
어떻게 하는지"(어느 함수를 부를지)를 나타낸다. 두 dict는 **키 집합이
정확히 일치해야 한다**(TARGETS에 있는데 DISPATCH에 없으면 UI에는 옵션이
보이는데 실제로 누르면 `err.engine`이 뜨는 버그가 됨).

- **L65-68**: CSV/XLSX/JSON은 함수 하나당 방향 하나씩, 손으로 나열
  (`data.py`의 4개 함수 그대로 매핑).
- **L69-74**: PDF에서 나가는 5가지 방향. `pdf_to_images`는 `ext` 파라미터를
  `partial`로 고정해 png/jpg 두 키에 각각 다른 함수(사실은 같은 함수의
  변형)를 등록한 것 — L72-73에서 `partial(pdf.pdf_to_images, ext="png")`와
  `ext="jpg"`가 서로 다른 `partial` 객체이므로 dict에서 서로 다른 값으로
  저장된다.
- **L75-76**: `docx→pdf`와 `pptx→pdf`가 **같은 함수**(`office.office_to_pdf`)를
  가리킨다 — LibreOffice가 입력 포맷을 자동 감지하므로 별도 함수가 필요
  없다는 뜻(주석 "동일 LibreOffice 경로 재사용").
- **L77-85**: HWP/HWPX 관련 10개 매핑. `hwp.py`와 `hwpx.py`가 거의 대칭
  구조(`docx_to_hwp`↔`docx_to_hwpx`, `pdf_to_hwp`↔`pdf_to_hwpx` 등)라는 걸
  이름만 봐도 알 수 있다.
- **L86**: `**{...}` — 딕셔너리 언패킹(unpacking) 문법. `_VIDEO_EXTS`의
  각 확장자에 대해 `(ext, "mp4"): video.video_to_mp4`라는 항목을 만들어
  **`_DISPATCH` 딕셔너리 리터럴 안에 그대로 펼쳐 넣는다**. avi/mov/mkv/
  wmv/flv/m4v 6개 항목이 이 한 줄로 생긴다. (영상 확장자가 TARGETS에
  아예 없는 배포판이라도 `_DISPATCH`에는 이 매핑이 존재한다는 점에
  주의 — `convert()`는 `_DISPATCH`만 조회하지 `TARGETS`에 있는지는
  안 물어본다. 다만 UI가 애초에 TARGETS를 근거로 옵션을 안 보여주므로
  실질적으로 도달 불가능한 코드는 아니다.)
- **L87-88, L89-90**: 이미지·3D 모델도 마찬가지로 이중 for(`for src ...
  for tgt in TARGETS[src]`)로 20~30여 개 매핑을 자동 생성한다. **여기서
  `TARGETS[src]`를 참조한다는 게 중요** — 즉 `_DISPATCH`의 이미지/3D
  섹션은 앞서(L41-47, L52-55) 이미 채워진 `TARGETS`에 의존한다. 파일 안의
  코드 순서(TARGETS 먼저, DISPATCH 나중)가 실행 순서와 정확히 일치해야
  하는 이유가 여기 있다 — 순서를 바꾸면 `TARGETS[src]`가 아직 안 채워져
  `KeyError`가 난다.
- **L91-96**: 마크업 6방향, 손으로 나열(함수가 서로 다 다른 이름이라 반복문으로
  자동화하기보다 명시적으로 쓰는 쪽을 택함).

## L100-101: `def supported(ext: str) -> bool`

```python
def supported(ext: str) -> bool:
    return ext.lower() in TARGETS
```

이 확장자가 (지금 이 실행 환경에서) 변환 가능한 소스인지 확인한다.
`ext.lower()`로 대소문자를 무시한다(`.DOCX`와 `.docx`를 같게 취급). UI가
파일을 드롭했을 때 "이 파일, 처리 가능한가?"를 물을 때 쓴다
(`app/ui/main_window.py`의 `FileRow`가 이걸로 아이콘을 결정).

## L104-105: `def targets_for(ext: str) -> list[str]`

```python
def targets_for(ext: str) -> list[str]:
    return TARGETS.get(ext.lower(), [])
```

이 확장자에서 갈 수 있는 대상 목록. `.get(..., [])`으로 없는 확장자는
빈 리스트를 반환(에러를 던지지 않음) — UI 드롭다운을 채울 때 "선택지가
없으면 그냥 빈 채로 두면 된다"는 방어적 설계.

## L108-112: `def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path`

```python
def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path:
    fn = _DISPATCH.get((src.suffix.lstrip(".").lower(), dst_fmt))
    if fn is None:
        raise ConversionError("err.engine")
    return fn(src, tmpdir)
```

- 이게 이 패키지의 **진짜 진입점** — `app/workers.py`의 `_Task.run()`이
  이 함수 하나만 호출해서 실제 변환을 수행한다.
- `src.suffix.lstrip(".").lower()`: `Path.suffix`는 점을 포함해서
  `.docx`처럼 나오므로, `.lstrip(".")`로 점을 떼고 소문자로 정규화한다 —
  `_DISPATCH`의 키(예: `"docx"`)와 형식을 맞추기 위해서.
- `_DISPATCH.get((src_ext, dst_fmt))`: 튜플 `(소스확장자, 대상포맷)`을 키로
  실제 변환 함수를 찾는다. 못 찾으면(`None`) 지원하지 않는 조합이라는 뜻
  이므로 `err.engine`(엔진 실패, 일반적인 "이 변환은 지원 안 함" 메시지)을
  던진다 — 이론상 UI가 `TARGETS`/`supported()`로 미리 걸러주므로 여기 도달할
  일은 드물지만, 방어적으로 남겨둔 마지막 관문이다.
- `fn(src, tmpdir)`: 실제 변환 함수를 호출한다. 모든 컨버터 함수의 시그니처가
  `(src: Path, tmpdir: Path) -> Path`로 통일돼 있다는 뜻 — 이게 `_DISPATCH`
  dict에 모든 함수를 균일하게 담을 수 있는 이유다(함수마다 파라미터가
  달랐다면 이렇게 하나의 dict로 묶을 수 없었을 것).

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- 새로운 포맷 X를 A→X 방향으로만 추가하고 싶다면 이 파일 어디를 바꿔야 하는가?
- `TARGETS`와 `_DISPATCH`의 키 집합이 어긋나면 어떤 시점에 문제가 드러나는가?
  (즉시 에러? 아니면 특정 변환을 시도할 때만?)
- 영상 확장자가 `TARGETS`에 조건부로만 들어가는 것처럼, 다른 포맷도 "환경에
  따라 조건부로 지원"하게 만들려면 이 파일의 어느 패턴을 따라 하면 되는가?
