# image.py — 이미지 포맷 상호 변환

원본: `app/converters/image.py` (63줄)

Pillow(HPND 라이선스)로 JPG/PNG/BMP/GIF/WEBP/TIFF를 서로 변환한다. 짧은
파일이지만 "EXIF 회전"·"알파 채널 합성"·"애니메이션 첫 프레임만" 세 가지
실사용 함정을 전부 처리한다.

---

## L1-12: 모듈 docstring — 이 파일이 해결하는 3가지 문제

1. **EXIF 방향**: 스마트폰 사진은 실제 픽셀은 회전 안 된 채로 저장하고
   "이 방향으로 돌려서 봐라"라는 메타데이터(EXIF Orientation)만 갖고
   있는 경우가 흔하다. 이 메타데이터를 무시하고 그냥 저장하면, 원래
   보던 사진(세로)과 달리 변환된 파일이 옆으로 누워 보인다.
2. **알파(투명) → 무알파 포맷**: PNG의 투명 배경을 JPG(투명 미지원)로
   저장하면, 뷰어에 따라 검게 나오거나 예측 불가능한 색이 채워질 수
   있다 — 흰 배경으로 명시적으로 합성해야 한다.
3. **애니메이션 → 정적 포맷**: GIF/WEBP는 여러 프레임(움짤)을 가질 수
   있는데, 이 앱은 대상 포맷이 애니메이션을 지원하든 안 하든 **항상
   첫 프레임만** 저장한다 — "동작을 단순하고 일관되게 유지"하려는
   의도적 범위 제한이고, XLSX 다중 시트를 첫 시트만 쓰는 것(`data.py`)
   과 같은 원칙(조용한 유실 대신 UI 사전 고지)이다.

## L13-21: import와 매핑 테이블

```python
from pathlib import Path
from .base import ConversionError

_PILLOW_FORMAT = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "bmp": "BMP",
    "gif": "GIF", "webp": "WEBP", "tiff": "TIFF",
}
_NO_ALPHA_FORMATS = {"JPEG", "BMP"}
```

- `_PILLOW_FORMAT`: 이 앱이 쓰는 소문자 확장자(`"jpg"`)를 Pillow가
  요구하는 대문자 포맷 이름(`"JPEG"`)으로 매핑한다 — Pillow의
  `Image.save(format=...)`는 확장자가 아니라 이 정식 이름을 받는다.
  `jpg`와 `jpeg` 둘 다 `"JPEG"`로 매핑되는 점에 주의(`__init__.py`의
  `_IMAGE_CANON`과 같은 정규화).
- `_NO_ALPHA_FORMATS = {"JPEG", "BMP"}`: 투명(알파 채널)을 지원하지
  않는 포맷 집합. PNG/GIF/WEBP/TIFF는 투명을 지원하므로 이 집합에
  없다 — 즉 대상이 JPEG나 BMP일 때만 아래(L47-56)의 흰 배경 합성
  로직이 발동한다.

## L24-32: `is_animated` — UI 고지 판단용 조회 함수

```python
def is_animated(src: Path) -> bool:
    from PIL import Image
    try:
        with Image.open(src) as im:
            return getattr(im, "n_frames", 1) > 1
    except Exception:
        return False
```

- `xlsx_sheet_count`(data.py)와 같은 성격의 함수 — **변환을 수행하지
  않고**, 실제 변환 전에 UI가 "애니메이션이라 첫 프레임만 저장돼요"
  고지를 보여줄지 판단하는 데만 쓰인다.
- `getattr(im, "n_frames", 1)`: Pillow의 `Image` 객체는 다중 프레임
  포맷(GIF, 애니메이션 WEBP, 일부 TIFF)일 때만 `n_frames` 속성을
  갖는다. 정적 이미지(JPG, PNG 등)는 이 속성이 아예 없으므로
  `getattr(..., 1)`로 기본값 1(프레임 1개 = 애니메이션 아님)을 준다.
- `except Exception: return False`: 파일을 열지 못하는 등 어떤 이유로든
  실패하면 "애니메이션 아님"으로 간주하고 조용히 넘어간다 — 실제 실패는
  진짜 변환 시도(`convert_image`)에서 `err.corrupted`로 다시 드러나므로,
  이 함수는 오류를 정확히 보고할 책임이 없다(`xlsx_sheet_count`와 동일한
  설계 철학).

## L35-63: `convert_image` — 실제 변환

```python
def convert_image(src: Path, tmpdir: Path, target_ext: str) -> Path:
    from PIL import Image, ImageOps
    from PIL import UnidentifiedImageError

    fmt = _PILLOW_FORMAT[target_ext]
    try:
        im = Image.open(src)
    except (UnidentifiedImageError, OSError):
        raise ConversionError("err.corrupted")

    with im:
        im = ImageOps.exif_transpose(im)
        if fmt in _NO_ALPHA_FORMATS:
            has_alpha = im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info)
            if has_alpha:
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode not in ("RGB", "L"):
                im = im.convert("RGB")

        out = tmpdir / (src.stem + "." + target_ext)
        try:
            im.save(out, format=fmt)
        except OSError as e:
            raise ConversionError("err.engine", str(e))
        return out
```

- **L39**: `target_ext`(예: `"png"`)를 Pillow 포맷 이름(`"PNG"`)으로
  변환. 이 함수는 `app/converters/__init__.py`에서
  `partial(image.convert_image, target_ext=tgt)`로 호출되므로,
  `src`·`tmpdir` 두 인자만 `_DISPATCH` 호출 시점에 채워지고
  `target_ext`는 이미 고정돼 있다.
- **L40-43**: `Image.open(src)`는 실제로 파일을 읽어 헤더를 파싱하기
  **전까지는** 예외를 던지지 않을 수도 있지만(지연 로딩), 손상되거나
  이미지가 아닌 파일이면 `UnidentifiedImageError`(Pillow가 포맷을
  인식 못 함) 또는 `OSError`(파일 자체를 못 읽음)가 난다. 둘 다
  `err.corrupted`로 통일해서 사용자에게 보여준다.
- **L45**: `with im:` — `PIL.Image`는 컨텍스트 매니저를 지원해서, 이
  블록을 벗어나면 내부 파일 핸들이 자동으로 닫힌다(리소스 정리).
- **L46**: `ImageOps.exif_transpose(im)` — EXIF Orientation 태그를
  읽어서 실제로 픽셀을 회전/뒤집기하고, 그 결과로 **새로운** `Image`
  객체를 돌려준다(원본 `im`을 그 자리에서 바꾸는 게 아니라 반환값을
  다시 `im`에 대입 — 이후 코드는 이 "회전 반영된" 이미지를 기준으로
  동작한다). EXIF 정보가 없는 이미지는 그대로(변화 없이) 반환된다.
- **L47-56: 알파 채널 처리 (대상이 JPEG/BMP일 때만)**:
  - **L48-49**: `has_alpha` 판정 — 이미지 모드(`im.mode`)가 `"RGBA"`
    (일반 투명 컬러) 또는 `"LA"`(그레이스케일+알파)이거나, `"P"`
    (팔레트 모드, GIF에서 흔함)이면서 `info` 딕셔너리에
    `"transparency"` 키가 있으면(팔레트 기반 투명, GIF 특유의 방식)
    투명이 있다고 판단한다. Pillow는 투명을 표현하는 방식이 여러
    가지라 이 세 가지를 다 확인해야 놓치지 않는다.
  - **L50-54**: 투명이 있으면:
    1. `im.convert("RGBA")` — 팔레트 모드(P+transparency)든 뭐든
       일단 표준 RGBA로 통일한다.
    2. `Image.new("RGB", im.size, (255, 255, 255))` — 같은 크기의
       순백색(255,255,255) 배경 이미지를 새로 만든다.
    3. `bg.paste(im, mask=im.split()[-1])` — `im.split()`은 이미지를
       채널별(R, G, B, A)로 쪼갠 튜플을 반환하는데, `[-1]`은 마지막
       채널인 **알파 채널**을 가리킨다. 이걸 `mask`로 써서 `im`을
       `bg` 위에 붙여넣으면, 알파값이 높은(불투명한) 부분은 원본
       색이 그대로 오고, 알파값이 낮은(투명한) 부분은 흰 배경이
       비쳐 보이는 합성이 이뤄진다 — 이게 "흰 배경으로 합성"의
       실제 구현.
    4. `im = bg`: 합성된 결과를 다시 `im`에 대입해 이후 저장 대상으로
       삼는다.
  - **L55-56**: 투명이 없지만 모드가 `"RGB"`나 `"L"`(그레이스케일)도
    아닌 경우(예: `"CMYK"`, `"P"`인데 투명 정보가 없는 경우 등)는
    그냥 RGB로 변환한다 — JPEG/BMP 저장기가 이해할 수 있는 색공간으로
    맞추는 안전장치.
- **L58**: 출력 경로는 `src.stem + "." + target_ext` — 예를 들어
  `photo.png`를 jpg로 바꾸면 `photo.jpg`가 된다.
- **L59-62**: `im.save(out, format=fmt)`가 실패하면(디스크 공간 부족,
  권한 문제 등 `OSError`) `err.engine` 키로 예외 원문(`str(e)`)을
  detail에 담아 던진다 — L40-43의 "입력을 못 읽음"과는 다른 실패
  지점(출력을 못 씀)이라 다른 키를 쓴다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `ImageOps.exif_transpose(im)`가 원본 객체를 제자리에서 바꾸는가,
  아니면 새 객체를 반환하는가? 이게 코드에 어떤 영향을 주는가?
- `has_alpha` 판정에서 `"P"` 모드(팔레트)를 별도로 확인하는 이유는?
  RGBA/LA만 확인하면 어떤 이미지가 누락되는가?
- 왜 `is_animated`와 `xlsx_sheet_count`(data.py)가 같은 패턴
  (`except Exception: 안전한 기본값`)을 쓰는가? 이 패턴이 적절하지
  않은 경우는 언제일까?
- 대상이 PNG(알파 지원)인데 원본이 알파가 있는 JPG(원래 없음)라면
  이 함수는 어떻게 동작하는가?
