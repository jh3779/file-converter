"""PDF 변환 — PDF→TXT (REQ-F-004). PDF→DOCX는 v0.2."""
from pathlib import Path

from .base import ConversionError


def pdf_to_txt(src: Path, tmpdir: Path) -> Path:
    from pdfminer.high_level import extract_text
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.psparser import PSException
    try:
        text = extract_text(str(src))
    except PDFPasswordIncorrect:
        raise ConversionError("err.password")
    except (PSException, ValueError, OSError) as e:
        raise ConversionError("err.corrupted", str(e))
    out = tmpdir / (src.stem + ".txt")
    out.write_text(text, encoding="utf-8")
    return out


def pdf_to_docx(src: Path, tmpdir: Path) -> Path:
    """PDF → 텍스트 추출 → DOCX (레이아웃 단순화 — DEC-010 고지 문안과 연동).

    pdf2docx(PyMuPDF)는 AGPL이라 사용 금지(DEC-007과 동일한 라이선스 원칙).
    """
    from .docx_build import blocks_to_docx, text_to_blocks
    txt = pdf_to_txt(src, tmpdir)
    blocks = text_to_blocks(txt.read_text(encoding="utf-8"))
    return blocks_to_docx(blocks, tmpdir / (src.stem + ".docx"))
