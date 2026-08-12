"""HWPX 변환 — hwpxlib(Apache-2.0) + 기존 HWP JRE 사이드카 재사용
(Phase 1: 읽기, QA(h) 외부 요청 · Phase 2: 쓰기, DEC-049).

HWPX(확장자 .hwpx)는 한글과컴퓨터의 최신 표준 문서 포맷으로, hwplib이
다루는 기존 바이너리 .hwp와는 완전히 다른 스펙(OWPML, ZIP+XML 기반)이다.
hwplib과 같은 저자(neolord0)가 만든 별도 라이브러리 hwpxlib(Apache-2.0,
순수 JDK라 외부 런타임 의존성 없음)을 사이드카(sidecar/hwp/HwpxToText.java·
HwpxToJson.java·JsonToHwpx.java)에서 쓴다 — 패키지명이 겹치지 않아
(kr.dogfoot.hwplib vs kr.dogfoot.hwpxlib) 기존 hwplib 사이드카·엔진 번들에
그대로 같이 넣었고, app.converters.hwp의 _run_sidecar()를 그대로
재사용한다(새 엔진 디렉터리·새 JVM 실행 경로 불필요).

Phase 1은 읽기만 지원했다: HWPX→TXT/DOCX/PDF. Phase 2(이번)에서 DOCX/
PDF→HWPX 쓰기를 추가한다 — hwp.py의 docx_to_hwp/pdf_to_hwp/_blocks_to_hwp와
완전히 같은 패턴(JsonToHwp.java 대신 JsonToHwpx.java를 호출)이며,
docx_extract.docx_to_blocks()·pdf._extract_pdf_blocks_by_page()는 이미
align/colSpan/rowSpan/pageBreakBefore를 다 내보내고 있어(HWP 쓰기와
공유) 수정 없이 그대로 재사용한다.

HwpxToJson.java가 내는 구조 JSON은 HwpToJson.java(HWP용)와 스키마가 같아
(Phase 2에서 align·colSpan/rowSpan 읽기도 대칭으로 확장) docx_build.
blocks_to_docx를 그대로 재사용한다. 표 셀 안 서식·머리말/꼬리말
텍스트는 여전히 범위 밖(문서화된 단순화, DEC-028과 같은 원칙).
"""
import json
from pathlib import Path

from .base import ConversionError
from .docx_build import blocks_to_docx
from .hwp import _run_sidecar


def hwpx_to_txt(src: Path, tmpdir: Path) -> Path:
    out = tmpdir / (src.stem + ".txt")
    _run_sidecar("HwpxToText", src, out)
    return out


def hwpx_to_docx(src: Path, tmpdir: Path) -> Path:
    """HWPX → 구조 JSON → DOCX (문단 + 표 내용 + 문자 서식 보존)."""
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    _run_sidecar("HwpxToJson", src, blocks_json)
    try:
        blocks = json.loads(blocks_json.read_text(encoding="utf-8"))["blocks"]
    except (json.JSONDecodeError, KeyError) as e:
        raise ConversionError("err.corrupted", str(e))
    return blocks_to_docx(blocks, tmpdir / (src.stem + ".docx"))


def hwpx_to_pdf(src: Path, tmpdir: Path) -> Path:
    """HWPX → DOCX → LibreOffice → PDF (hwp.hwp_to_pdf와 같은 파이프라인)."""
    from . import office
    intermediate = hwpx_to_docx(src, tmpdir)
    return office.office_to_pdf(intermediate, tmpdir)


def docx_to_hwpx(src: Path, tmpdir: Path) -> Path:
    """DOCX → 구조 JSON → HWPX (hwp.docx_to_hwp와 같은 파이프라인, DEC-049).
    문단 문자 서식·정렬·표 병합까지 반영한다(표 셀 안 서식은 범위 밖)."""
    from .docx_extract import docx_to_blocks

    blocks = docx_to_blocks(src)
    return _blocks_to_hwpx(blocks, src, tmpdir)


def pdf_to_hwpx(src: Path, tmpdir: Path) -> Path:
    """PDF → 텍스트 추출 → HWPX (hwp.pdf_to_hwp와 같은 파이프라인, DEC-049).
    페이지 경계(pageBreakBefore)·정렬 추정을 함께 반영한다."""
    from . import pdf as pdf_mod

    blocks = pdf_mod._extract_pdf_blocks_by_page(src)
    return _blocks_to_hwpx(blocks, src, tmpdir)


def _blocks_to_hwpx(blocks: list[dict], src: Path, tmpdir: Path) -> Path:
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    blocks_json.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    out = tmpdir / (src.stem + ".hwpx")
    _run_sidecar("JsonToHwpx", blocks_json, out)
    return out
