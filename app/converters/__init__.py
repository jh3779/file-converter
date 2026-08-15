"""변환기 레지스트리 — 정본: docs/01_requirements.md REQ-F-002~006·REQ-F-012·REQ-F-014.

TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
"""
from functools import partial
from pathlib import Path

from .base import ConversionError
from . import data, pdf, pdf_docx, pdf_pptx, office, hwp, hwpx, video, image, model3d

TARGETS: dict[str, list[str]] = {
    "docx": ["pdf", "hwp", "hwpx"],  # DEC-017/DEC-028 — 표는 실제 HWP/HWPX 표로 생성됨(셀 안 서식 제외). hwpx: DEC-049
    "pptx": ["pdf"],   # DEC-016
    "pdf": ["txt", "docx", "hwp", "hwpx", "png", "jpg", "pptx"],  # DEC-023 — HWP/HWPX도 텍스트 기반(DEC-010과 같은 원칙, hwpx는 DEC-049). png/jpg: DEC-026, 페이지별 이미지를 폴더에 저장(jpg 옵션은 DEC-043). pptx: DEC-030, 줄 단위 위치 재구성(이미지로 뭉개지 않음)
    "hwp": ["txt", "pdf", "docx"],
    "hwpx": ["txt", "pdf", "docx"],  # 읽기(Phase 1, 외부 QA 요청) — hwplib이 아닌 별도 라이브러리 hwpxlib 사용
    "csv": ["xlsx", "json"],
    "xlsx": ["csv"],
    "json": ["csv"],
}

_VIDEO_EXTS = ("avi", "mov", "mkv", "wmv", "flv", "m4v")

# DEC-024 — 영상 스트림이 H.264/HEVC일 때만 지원(그 외 코덱은 변환 시 오류).
# webm은 목록에서 제외 — 표준 WEBM은 VP8/VP9/AV1만 담아 H.264/HEVC를 실을 수
# 없으므로 "지원"으로 노출하면 사실상 항상 실패한다(가능한 것만 노출한다는
# TARGETS 원칙 위반, 코드 리뷰 지적으로 발견).
# DEC-029 — FFmpeg는 macOS 빌드에서 번들하지 않는다(검증된 사전 빌드
# LGPL macOS 바이너리가 없었음). find_ffmpeg()가 못 찾으면(엔진이 애초에
# 없는 배포판) 영상 확장자를 TARGETS에서 아예 뺀다 — "재설치하세요"라는
# 엉뚱한 오류를 보여주는 대신, 지원 안 하는 형식으로 자연스럽게 처리된다
# (가능한 것만 노출한다는 원칙을 여기에도 그대로 적용).
if video.find_ffmpeg() is not None:
    for _ext in _VIDEO_EXTS:
        TARGETS[_ext] = ["mp4"]
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

# 3D 모델 상호 변환(trimesh) — 스파이크로 5개 포맷 전 조합(20쌍)의 정점·면·
# 부피 보존을 직접 확인(model3d.py 참고). 자기 자신으로의 "변환"은
# 노출하지 않는다(이미지와 같은 원칙).
_MODEL3D_EXTS = ("obj", "stl", "ply", "glb", "gltf")
for _src in _MODEL3D_EXTS:
    TARGETS[_src] = [t for t in _MODEL3D_EXTS if t != _src]
del _src

_DISPATCH = {
    ("csv", "xlsx"): data.csv_to_xlsx,
    ("xlsx", "csv"): data.xlsx_to_csv,
    ("csv", "json"): data.csv_to_json,
    ("json", "csv"): data.json_to_csv,
    ("pdf", "txt"): pdf.pdf_to_txt,
    ("pdf", "docx"): pdf_docx.pdf_to_docx,  # 텍스트 기반 (DEC-010 고지)
    ("pdf", "hwp"): hwp.pdf_to_hwp,        # 텍스트 기반 (DEC-023, DEC-010과 같은 원칙)
    ("pdf", "png"): partial(pdf.pdf_to_images, ext="png"),  # 페이지별 이미지, 폴더 결과물 (DEC-026)
    ("pdf", "jpg"): partial(pdf.pdf_to_images, ext="jpg"),  # 위와 동일, JPG(DEC-043)
    ("pdf", "pptx"): pdf_pptx.pdf_to_pptx,  # 줄 단위 위치 재구성 (DEC-030)
    ("docx", "pdf"): office.office_to_pdf,
    ("pptx", "pdf"): office.office_to_pdf,  # DEC-016 — 동일 LibreOffice 경로 재사용
    ("docx", "hwp"): hwp.docx_to_hwp,      # DEC-017/DEC-028 — 문단+표(실제 표로 신규 생성)
    ("docx", "hwpx"): hwpx.docx_to_hwpx,   # DEC-049 — hwp.docx_to_hwp와 대칭
    ("pdf", "hwpx"): hwpx.pdf_to_hwpx,     # DEC-049 — hwp.pdf_to_hwp와 대칭
    ("hwp", "txt"): hwp.hwp_to_txt,
    ("hwp", "pdf"): hwp.hwp_to_pdf,        # DOCX 경유 → LibreOffice
    ("hwp", "docx"): hwp.hwp_to_docx,      # 구조 JSON → python-docx
    ("hwpx", "txt"): hwpx.hwpx_to_txt,     # 읽기(Phase 1) — hwpxlib 사이드카
    ("hwpx", "pdf"): hwpx.hwpx_to_pdf,     # DOCX 경유 → LibreOffice
    ("hwpx", "docx"): hwpx.hwpx_to_docx,   # 구조 JSON → python-docx
    **{(ext, "mp4"): video.video_to_mp4 for ext in _VIDEO_EXTS},  # DEC-024
    **{(src, tgt): partial(image.convert_image, target_ext=tgt)
       for src in _IMAGE_SRC_EXTS for tgt in TARGETS[src]},
    **{(src, tgt): partial(model3d.convert_3d, target_ext=tgt)
       for src in _MODEL3D_EXTS for tgt in TARGETS[src]},
}


def supported(ext: str) -> bool:
    return ext.lower() in TARGETS


def targets_for(ext: str) -> list[str]:
    return TARGETS.get(ext.lower(), [])


def convert(src: Path, dst_fmt: str, tmpdir: Path) -> Path:
    fn = _DISPATCH.get((src.suffix.lstrip(".").lower(), dst_fmt))
    if fn is None:
        raise ConversionError("err.engine")
    return fn(src, tmpdir)
