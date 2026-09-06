"""변환기 레지스트리 — 정본: docs/01_requirements.md REQ-F-002~006·REQ-F-012·REQ-F-014.

TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
"""
from functools import partial
from pathlib import Path

from .base import ConversionError
from . import data, pdf, pdf_docx, pdf_pptx, office, hwp, hwpx, video, image, model3d, markup

TARGETS: dict[str, list[str]] = {
    "docx": ["pdf", "hwp", "hwpx"], "pptx": ["pdf"],
    "pdf": ["txt", "docx", "hwp", "hwpx", "png", "jpg", "pptx"],
    "hwp": ["txt", "pdf", "docx"], "hwpx": ["txt", "pdf", "docx"],
    "csv": ["xlsx", "json"], "xlsx": ["csv"], "json": ["csv"],
}

_VIDEO_EXTS = ("avi", "mov", "mkv", "wmv", "flv", "m4v")
_VIDEO_AVAILABLE = video.find_ffmpeg() is not None
_CONTENT_VIDEO_KEY = "@video"  # 실제 확장자 namespace와 충돌하지 않는 내부 routing key

if _VIDEO_AVAILABLE:
    for _ext in _VIDEO_EXTS:
        TARGETS[_ext] = ["mp4"]
    del _ext

_IMAGE_SRC_EXTS = ("jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff")
_IMAGE_CANON = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "bmp": "bmp", "gif": "gif", "webp": "webp", "tiff": "tiff"}
_IMAGE_TARGET_EXTS = ("jpg", "png", "bmp", "gif", "webp", "tiff")
for _src in _IMAGE_SRC_EXTS:
    TARGETS[_src] = [t for t in _IMAGE_TARGET_EXTS if t != _IMAGE_CANON[_src]]
del _src

_MODEL3D_EXTS = ("obj", "stl", "ply", "glb", "gltf")
for _src in _MODEL3D_EXTS:
    TARGETS[_src] = [t for t in _MODEL3D_EXTS if t != _src]
del _src

_MARKUP_EXTS = ("txt", "md", "html")
for _src in _MARKUP_EXTS:
    TARGETS[_src] = [t for t in _MARKUP_EXTS if t != _src]
del _src

_DISPATCH = {
    ("csv", "xlsx"): data.csv_to_xlsx, ("xlsx", "csv"): data.xlsx_to_csv,
    ("csv", "json"): data.csv_to_json, ("json", "csv"): data.json_to_csv,
    ("pdf", "txt"): pdf.pdf_to_txt, ("pdf", "docx"): pdf_docx.pdf_to_docx,
    ("pdf", "hwp"): hwp.pdf_to_hwp, ("pdf", "png"): partial(pdf.pdf_to_images, ext="png"),
    ("pdf", "jpg"): partial(pdf.pdf_to_images, ext="jpg"), ("pdf", "pptx"): pdf_pptx.pdf_to_pptx,
    ("docx", "pdf"): office.office_to_pdf, ("pptx", "pdf"): office.office_to_pdf,
    ("docx", "hwp"): hwp.docx_to_hwp, ("docx", "hwpx"): hwpx.docx_to_hwpx,
    ("pdf", "hwpx"): hwpx.pdf_to_hwpx, ("hwp", "txt"): hwp.hwp_to_txt,
    ("hwp", "pdf"): hwp.hwp_to_pdf, ("hwp", "docx"): hwp.hwp_to_docx,
    ("hwpx", "txt"): hwpx.hwpx_to_txt, ("hwpx", "pdf"): hwpx.hwpx_to_pdf,
    ("hwpx", "docx"): hwpx.hwpx_to_docx,
    **{(ext, "mp4"): video.video_to_mp4 for ext in _VIDEO_EXTS},
    **{(src, tgt): partial(image.convert_image, target_ext=tgt) for src in _IMAGE_SRC_EXTS for tgt in TARGETS[src]},
    **{(src, tgt): partial(model3d.convert_3d, target_ext=tgt) for src in _MODEL3D_EXTS for tgt in TARGETS[src]},
    ("txt", "html"): markup.txt_to_html, ("txt", "md"): markup.txt_to_md,
    ("md", "html"): markup.md_to_html, ("md", "txt"): markup.md_to_txt,
    ("html", "txt"): markup.html_to_txt, ("html", "md"): markup.html_to_md,
}


def supported(ext: str) -> bool:
    key = ext.lower()
    return key == _CONTENT_VIDEO_KEY or key in TARGETS


def targets_for(ext: str) -> list[str]:
    key = ext.lower()
    if key == _CONTENT_VIDEO_KEY:
        return ["mp4"] if _VIDEO_AVAILABLE else []
    return TARGETS.get(key, [])


def content_video_key() -> str:
    return _CONTENT_VIDEO_KEY


def is_content_detected_video(src: Path) -> bool:
    ext = src.suffix.lstrip(".").lower()
    if ext == "mp4":
        return False  # 이미 대상 포맷과 같은 확장자 — 자기 자신으로의 변환 노출 방지
    return ext not in TARGETS and _VIDEO_AVAILABLE and video.can_convert_to_mp4(src)


def targets_for_source(src: Path) -> list[str]:
    ext = src.suffix.lstrip(".").lower()
    if ext in TARGETS:
        return TARGETS[ext]
    return ["mp4"] if is_content_detected_video(src) else []


def supported_source(src: Path) -> bool:
    return bool(targets_for_source(src))


def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path:
    ext = src.suffix.lstrip(".").lower()
    fn = _DISPATCH.get((ext, dst_fmt))
    if fn is not None:
        return fn(src, tmpdir)
    if dst_fmt == "mp4" and is_content_detected_video(src):
        return video.video_to_mp4(src, tmpdir)
    raise ConversionError("err.engine")
