"""HWPX 변환 — hwpxlib(Apache-2.0) + 기존 HWP JRE 사이드카 재사용
(QA(h) Phase 1: 읽기, 외부 QA 요청).

HWPX(확장자 .hwpx)는 한글과컴퓨터의 최신 표준 문서 포맷으로, hwplib이
다루는 기존 바이너리 .hwp와는 완전히 다른 스펙(OWPML, ZIP+XML 기반)이다.
hwplib과 같은 저자(neolord0)가 만든 별도 라이브러리 hwpxlib(Apache-2.0,
순수 JDK라 외부 런타임 의존성 없음)을 사이드카(sidecar/hwp/HwpxToText.java·
HwpxToJson.java)에서 쓴다 — 패키지명이 겹치지 않아(kr.dogfoot.hwplib vs
kr.dogfoot.hwpxlib) 기존 hwplib 사이드카·엔진 번들에 그대로 같이 넣었고,
app.converters.hwp의 _run_sidecar()를 그대로 재사용한다(새 엔진 디렉터리·
새 JVM 실행 경로 불필요).

Phase 1(이번)은 읽기만 지원한다: HWPX→TXT/DOCX/PDF. 쓰기(DOCX→HWPX 등)는
사용자와 합의한 후속 phase. HwpxToJson.java가 내는 구조 JSON은
HwpToJson.java(HWP용)와 스키마가 같아 docx_build.blocks_to_docx를 그대로
재사용한다. 표 셀 병합·문단 정렬·머리말/꼬리말 텍스트는 이번 phase
범위 밖(문서화된 단순화, DEC-028과 같은 원칙 — hwplib 쪽도 처음엔 이
범위로 시작해 이후 phase에서 하나씩 넓혀왔다).
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
