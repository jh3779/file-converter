"""변환기 레지스트리 — 정본: docs/01_requirements.md REQ-F-002~006·REQ-F-012·REQ-F-014.

TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
"""
from functools import lru_cache, partial
from pathlib import Path

from .base import ConversionError
from . import data, pdf, pdf_docx, pdf_pptx, office, hwp, hwpx, video, image, model3d, markup
# fbx는 여기서 직접 참조하지 않는다 — model3d.convert_3d가 소스 확장자로
# 내부 분기해 호출한다(model3d.py 참고), __init__.py는 dispatch만 재사용.

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
_VIDEO_AVAILABLE = video.find_ffmpeg() is not None
# DEC-066 — 실제 확장자(avi/mov/... 위 튜플)와 다른 내부 routing key. TARGETS에
# 가상 확장자로 넣으면 진짜 ".video" 확장자 파일과 충돌해 지원 노출 계약이
# 흐려진다는 자동 리뷰 지적으로, 확장자 namespace와 완전히 분리했다.
_CONTENT_VIDEO_KEY = "@video"

# DEC-024 — 영상 스트림이 H.264/HEVC일 때만 지원(그 외 코덱은 변환 시 오류,
# DEC-060부터는 Windows에서 h264_mf 재인코딩도 시도). webm은 목록에서 제외 —
# 표준 WEBM은 VP8/VP9/AV1만 담아 H.264/HEVC를 실을 수 없으므로 "지원"으로
# 노출하면 사실상 항상 실패한다(가능한 것만 노출한다는 TARGETS 원칙 위반,
# 코드 리뷰 지적으로 발견).
# DEC-029 — FFmpeg는 macOS 빌드에서 번들하지 않는다(검증된 사전 빌드
# LGPL macOS 바이너리가 없었음). find_ffmpeg()가 못 찾으면(엔진이 애초에
# 없는 배포판) 영상 확장자를 TARGETS에서 아예 뺀다 — "재설치하세요"라는
# 엉뚱한 오류를 보여주는 대신, 지원 안 하는 형식으로 자연스럽게 처리된다
# (가능한 것만 노출한다는 원칙을 여기에도 그대로 적용).
if _VIDEO_AVAILABLE:
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

# FBX(Autodesk) — 읽기 전용(DEC-069 · OQ-007, app/converters/fbx.py 참고).
# `ufbx`(네이티브 확장)가 세그폴트로 채택 불가해 순수 Python 자체 파서로
# 직접 구현했는데, 그 파서는 쓰기(export)를 아예 구현하지 않았다(`ufbx`
# 자체도 로더 전용이었던 것과 같은 제약). 그래서 위 `_MODEL3D_EXTS`
# 루프처럼 대칭적으로 넣지 않고, "fbx" 소스에서만 단방향으로 나머지
# 4개 포맷을 노출한다 — 다른 4개 포맷(OBJ/STL/PLY/GLB/GLTF)의 TARGETS에는
# "fbx"가 절대 들어가면 안 된다(대상으로 노출하면 존재하지 않는 FBX
# 쓰기 기능을 약속하는 셈이라 TARGETS의 "가능한 것만 노출" 원칙 위반).
TARGETS["fbx"] = list(_MODEL3D_EXTS)

# TXT/MD/HTML 상호 변환(DEC-061) — 이미지·3D 모델과 같은 "포맷 집합 내
# 전원이 서로 변환 가능" 패턴. 자기 자신으로의 "변환"은 노출하지 않는다.
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
    # FBX → 5개 포맷(단방향, 위 TARGETS["fbx"] 주석 참고) — model3d.convert_3d가
    # 소스 확장자 ".fbx"를 보고 내부적으로 fbx.load_trimesh()로 분기한다
    # (model3d.py 참고), 그 이후 내보내기 경로는 다른 4개 포맷과 동일해
    # 여기 dispatch 자체는 동일한 함수를 재사용한다.
    **{("fbx", tgt): partial(model3d.convert_3d, target_ext=tgt) for tgt in TARGETS["fbx"]},
    ("txt", "html"): markup.txt_to_html,  # DEC-061
    ("txt", "md"): markup.txt_to_md,
    ("md", "html"): markup.md_to_html,
    ("md", "txt"): markup.md_to_txt,
    ("html", "txt"): markup.html_to_txt,
    ("html", "md"): markup.html_to_md,
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


@lru_cache(maxsize=256)
def is_content_detected_video(src: Path) -> bool:
    """확장자로 판단 안 되는 파일이 실제로는 영상인지 ffprobe로 확인한다.

    이 판정을 파일 하나당 여러 지점(FileItem 생성, 워커의 사전 판정,
    convert()의 라우팅 재확인)에서 각각 독립적으로 다시 호출하면 매번 새
    ffprobe 서브프로세스가 실행돼 느릴 뿐 아니라, 순간적 I/O 오류 등으로
    두 호출이 서로 다른 결과를 낼 수 있어 같은 파일의 확장·라우팅 판정이
    어긋나는 위험이 있었다(정밀 검증에서 발견 — 어긋나면 finalize()가 원본
    파일명 보존용 stem을 못 받아 확장자 없는 파일명이 조용히 잘려 저장될
    수 있음). `_encoder_available`(video.py)과 같은 원칙으로 캐시해 같은
    파일에 대해서는 항상 동일한 값을 재사용한다.

    **트레이드오프**: 앱을 켜둔 채로 같은 경로에 다른 내용의 파일이
    놓이면(드문 케이스 — 예: 같은 이름으로 다른 파일을 다시 저장) 캐시가
    이전 판정을 그대로 반환할 수 있다. 파일 하나의 수명 동안 여러 지점의
    판정이 서로 어긋나지 않는 게 이런 드문 경우보다 우선순위가 높다고
    판단해 무효화 로직은 두지 않았다."""
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
