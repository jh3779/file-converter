"""이미지 포맷 변환 — JPG/PNG/BMP/GIF/WEBP/TIFF 상호 변환 (Pillow, HPND 라이선스).

EXIF 방향 정보를 반영해 회전된 사진이 옆으로 눕는 문제를 방지한다. 알파
채널(투명)이 있는 이미지를 JPG/BMP처럼 투명을 지원하지 않는 포맷으로 저장할
때는 흰 배경으로 합성한다(검게 나오는 문제 방지).

애니메이션 GIF/WEBP → 다른 포맷 변환 시 항상 첫 프레임만 저장한다(대상
포맷이 애니메이션을 지원하더라도 마찬가지 — 동작을 단순하고 일관되게
유지하기 위한 의도적 범위 제한). XLSX 다중 시트(DEC-019)와 같은 원칙으로
조용한 유실을 막기 위해 변환 전 UI에 고지한다(main_window.py
note.image_first_frame).
"""
from pathlib import Path

from .base import ConversionError

_PILLOW_FORMAT = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "bmp": "BMP",
    "gif": "GIF", "webp": "WEBP", "tiff": "TIFF",
}
_NO_ALPHA_FORMATS = {"JPEG", "BMP"}


def is_animated(src: Path) -> bool:
    """다중 프레임(애니메이션) 이미지인지 — UI 고지 판단용. 못 열면 False(실제
    실패는 변환 시도 시 err.corrupted로 다시 드러남)."""
    from PIL import Image
    try:
        with Image.open(src) as im:
            return getattr(im, "n_frames", 1) > 1
    except Exception:
        return False


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
