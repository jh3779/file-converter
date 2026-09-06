"""변환기 레지스트리 — 정본: docs/01_requirements.md REQ-F-002~006·REQ-F-012·REQ-F-014.

TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
"""
from functools import partial
from pathlib import Path

from .base import ConversionError
from . import data, pdf, pdf_docx, pdf_pptx, office, hwp, hwpx, video, image, model3d, markup

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

_VIDEO_EXTS = ("avi", "mov", "mkv", "wmv", "flv", "m4v")
_VIDEO_AVAILABLE = video.find_ffmpeg() is not None

# DEC-024/DEC-029 — 기존 확장자 기반 계약은 그대로 유지한다. 콘텐츠 기반
# 영상 감지는 TARGETS namespace에 가상 확장자를 추가하지 않고 아래의
# targets_for_source()/is_content_detected_video()에서 경로 단위로 처리한다.
if _VIDEO_AVAILABLE:
    for _ext in _VIDEO_EXTS:
        TARGETS[_ext] = ["mp4"]
    del _ext

_IMAGE_SRC_EXTS = ("jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff")
_IMAGE_CANON = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "bmp": "bmp",
                "gif": "gif", "webp": "webp", "tiff": "tiff"}
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
    ("csv", "xlsx"): data.csv_to_xlsx,
    ("xlsx", "csv"): data.xlsx_to_csv,
    ("csv", "json"): data.csv_to_json,
    ("json", "csv"): data.json_to_csv,
    ("pdf", "txt"): pdf.pdf_to_txt,
    ("pdf", "docx"): pdf_docx.pdf_to_docx,
    ("pdf", "hwp"): hwp.pdf_to_hwp,
    ("pdf", "png"): partial(pdf.pdf_to_images, ext="png"),
    ("pdf", "jpg"): partial(pdf.pdf_to_images, ext="jpg"),
    ("pdf", "pptx"): pdf_pptx.pdf_to_pptx,
    ("docx", "pdf"): office.office_to_pdf,
    ("pptx", "pdf"): office.office_to_pdf,
    ("docx", "hwp"): hwp.docx_to_hwp,
    ("docx", "hwpx"): hwpx.docx_to_hwpx,
    ("pdf", "hwpx"): hwpx.pdf_to_hwpx,
    ("hwp", "txt"): hwp.hwp_to_txt,
    ("hwp", "pdf"): hwp.hwp_to_pdf,
    ("hwp", "docx"): hwp.hwp_to_docx,
    ("hwpx", "txt"): hwpx.hwpx_to_txt,
    ("hwpx", "pdf"): hwpx.hwpx_to_pdf,
    ("hwpx", "docx"): hwpx.hwpx_to_docx,
    **{(ext, "mp4"): video.video_to_mp4 for ext in _VIDEO_EXTS},
    **{(src, tgt): partial(image.convert_image, target_ext=tgt)
       for src in _IMAGE_SRC_EXTS for tgt in TARGETS[src]},
    **{(src, tgt): partial(model3d.convert_3d, target_ext=tgt)
       for src in _MODEL3D_EXTS for tgt in TARGETS[src]},
    ("txt", "html"): markup.txt_to_html,
    ("txt", "md"): markup.txt_to_md,
    ("md", "html"): markup.md_to_html,
    ("md", "txt"): markup.md_to_txt,
    ("html", "txt"): markup.html_to_txt,
    ("html", "md"): markup.html_to_md,
}


def supported(ext: str) -> bool:
    return ext.lower() in TARGETS


def targets_for(ext: str) -> list[str]:
    return TARGETS.get(ext.lower(), [])


def is_content_detected_video(src: Path) -> bool:
    """지원 확장자가 아닌 파일이 실제로 MP4 변환 가능한 영상인지 확인.

    `26.09.06`처럼 `.06`이 확장자로 해석되는 파일, 확장자가 전혀 없는 파일,
    `foo.video`처럼 알 수 없는 확장자를 가진 파일 모두 실제 내용을 ffprobe로
    검증한다. 따라서 내부 타입과 실제 확장자 namespace가 섞이지 않는다.
    """
    ext = src.suffix.lstrip(".").lower()
    return not supported(ext) and _VIDEO_AVAILABLE and video.can_convert_to_mp4(src)


def targets_for_source(src: Path) -> list[str]:
    """파일 경로 기준으로 실제 노출 가능한 대상 포맷을 반환."""
    ext = src.suffix.lstrip(".").lower()
    if supported(ext):
        return targets_for(ext)
    return ["mp4"] if is_content_detected_video(src) else []


def supported_source(src: Path) -> bool:
    return bool(targets_for_source(src))


def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path:
    ext = src.suffix.lstrip(".").lower()
    fn = _DISPATCH.get((ext, dst_fmt))
    if fn is not None:
        return fn(src, tmpdir)

    # 확장자 기반 dispatch가 없을 때만 콘텐츠 기반 영상 경로를 허용한다.
    # 실제 지원 가능 여부는 video.can_convert_to_mp4()가 video_to_mp4()와 같은
    # 코덱/폴백 기준으로 검증한다.
    if dst_fmt == "mp4" and is_content_detected_video(src):
        return video.video_to_mp4(src, tmpdir)

    raise ConversionError("err.engine")
