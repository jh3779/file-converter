"""변환기 레지스트리 — 정본: docs/01_requirements.md REQ-F-002~006·REQ-F-012.

TARGETS: 확장자별 선택 가능한 대상 포맷(가능한 것만 노출 — C-03).
convert(src, dst_fmt, tmpdir) → 임시 산출물 Path. 실패 시 ConversionError(i18n 키).
"""
from pathlib import Path

from .base import ConversionError
from . import data, pdf, office, hwp

TARGETS: dict[str, list[str]] = {
    "docx": ["pdf", "hwp"],  # DEC-017 — 표는 텍스트로 단순화되어 저장됨
    "pptx": ["pdf"],   # DEC-016
    "pdf": ["txt", "docx", "hwp"],  # DEC-023 — HWP도 텍스트 기반(DEC-010과 같은 원칙)
    "hwp": ["txt", "pdf", "docx"],
    "csv": ["xlsx", "json"],
    "xlsx": ["csv"],
    "json": ["csv"],
}

_DISPATCH = {
    ("csv", "xlsx"): data.csv_to_xlsx,
    ("xlsx", "csv"): data.xlsx_to_csv,
    ("csv", "json"): data.csv_to_json,
    ("json", "csv"): data.json_to_csv,
    ("pdf", "txt"): pdf.pdf_to_txt,
    ("pdf", "docx"): pdf.pdf_to_docx,      # 텍스트 기반 (DEC-010 고지)
    ("pdf", "hwp"): hwp.pdf_to_hwp,        # 텍스트 기반 (DEC-023, DEC-010과 같은 원칙)
    ("docx", "pdf"): office.office_to_pdf,
    ("pptx", "pdf"): office.office_to_pdf,  # DEC-016 — 동일 LibreOffice 경로 재사용
    ("docx", "hwp"): hwp.docx_to_hwp,      # DEC-017 — 문단 텍스트만, 표는 텍스트로 단순화
    ("hwp", "txt"): hwp.hwp_to_txt,
    ("hwp", "pdf"): hwp.hwp_to_pdf,        # DOCX 경유 → LibreOffice
    ("hwp", "docx"): hwp.hwp_to_docx,      # 구조 JSON → python-docx
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
