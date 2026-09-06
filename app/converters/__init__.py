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

# DEC-024/DEC-029 — 기존과 동일하게 FFmpeg가 사용 가능한 배포판에서만 영상
# 변환을 노출한다. "video"는 확장자가 없거나 지원하지 않는 확장자를 가진
# 파일을 ffprobe로 검사해 실제 영상 스트림이 확인됐을 때 사용하는 내부
# canonical type이다. ffprobe 존재 여부는 실제 콘텐츠 감지 시 별도로 확인한다.
if _VIDEO_AVAILABLE:
    for _ext in _VIDEO_EXTS:
        TARGETS[_ext] = ["mp4"]
    TARGETS["video"] = ["mp4"]
    del _ext

# 이미지 상호 변환 — jpg/jpeg는 같은 포맷(JPEG)으로 취급해 서로를 대상
# 목록에서 제외한다(자기 자신으로의 "변환" 노출 방지, TARGETS 원칙).
_IMAGE_SRC_EXTS = ("jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff")
_IMAGE_CANON = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "bmp": "bmp",
                "gif": "gif", "webp": "webp", "tiff": "tiff"}
_IMAGE_TARGET_EXTS = ("jpg", "png", "bmp", "gif", "webp", "tiff")
for _src in _IMAGE_SRC_EXTS:
    TARGETS[_src] = [t for t in _IMAGE_TARGET_EXTS if t != _IMAGE_CANON[_src]]
del _src

# 3D 모델 상호 변환(trimesh)
_MODEL3D_EXTS = ("obj", "stl", "ply", "glb", "gltf")
for _src in _MODEL3D_EXTS:
    TARGETS[_src] = [t for t in _MODEL3D_EXTS if t != _src]
del _src

# TXT/MD/HTML 상호 변환(DEC-061)
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
    ("video", "mp4"): video.video_to_mp4,
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


def detect_source_format(src: Path) -> str:
    """확장자를 우선 사용하되, 확장자가 없거나 알 수 없는 파일은 ffprobe로
    실제 영상 스트림을 검사한다.

    `26.09.06`처럼 파일명에 점이 있어 Path가 `.06`을 확장자로 오인하는 경우도
    지원하지 않는 확장자이므로 이 경로로 들어와 정상적으로 영상으로 감지된다.
    검사 실패는 오류로 승격하지 않고 원래 확장자를 반환해 기존 unsupported
    동작을 유지한다.
    """
    ext = src.suffix.lstrip(".").lower()
    if supported(ext):
        return ext
    if not _VIDEO_AVAILABLE:
        return ext

    ffprobe = video.find_ffprobe()
    if ffprobe is None:
        return ext
    try:
        streams = video._probe_streams(ffprobe, src)
    except (ConversionError, OSError):
        return ext

    has_real_video = any(
        s.get("codec_type") == "video"
        and not s.get("disposition", {}).get("attached_pic")
        for s in streams
    )
    return "video" if has_real_video else ext


def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path:
    source_fmt = detect_source_format(src)
    fn = _DISPATCH.get((source_fmt, dst_fmt))
    if fn is None:
        raise ConversionError("err.engine")

    out = fn(src, tmpdir)

    # 알 수 없는/없는 확장자를 콘텐츠 기반으로 영상 감지한 경우 src.stem을 쓰면
    # `26.09.06` → `26.09.mp4`처럼 파일명 일부가 사라진다. 원래 이름 전체를
    # 보존해 `26.09.06.mp4`로 만든다.
    if source_fmt == "video" and dst_fmt == "mp4":
        desired = tmpdir / f"{src.name}.mp4"
        if out != desired:
            if desired.exists():
                desired.unlink()
            out.replace(desired)
            out = desired
    return out
