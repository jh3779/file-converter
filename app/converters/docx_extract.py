"""DOCX → 구조 블록 (python-docx). DOCX→HWP 파이프라인 1단계 (docx_build.blocks_to_docx의 역방향).

블록 형식: {"type":"p","text":str} | {"type":"table","rows":[[str,...],...]}
문서 순서(본문에 등장하는 순서)대로 문단·표를 함께 추출한다 — python-docx는
document.paragraphs/document.tables를 각각 따로 주기 때문에 body XML을 직접
순회해야 순서가 보존된다.
"""
from pathlib import Path


def _iter_block_items(document):
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def docx_to_blocks(src: Path) -> list[dict]:
    from docx import Document
    from docx.table import Table

    doc = Document(src)
    blocks: list[dict] = []
    for item in _iter_block_items(doc):
        if isinstance(item, Table):
            rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            if any(cell for row in rows for cell in row):
                blocks.append({"type": "table", "rows": rows})
        else:
            text = item.text.strip()
            if text:
                blocks.append({"type": "p", "text": text})
    return blocks
