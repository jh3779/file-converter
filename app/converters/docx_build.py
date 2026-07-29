"""구조 블록 → DOCX 생성 (python-docx). HWP/PDF → DOCX 파이프라인 공용 (DEC-007).

블록 형식: {"type":"p","text":str} | {"type":"table","rows":[[str,...],...]}
레이아웃은 단순화된다 — 기대치 고지는 OQ-003/DEC-010 문안으로 UI에서 안내.
"""
from pathlib import Path


def blocks_to_docx(blocks: list[dict], out_path: Path) -> Path:
    from docx import Document

    doc = Document()
    for block in blocks:
        if block.get("type") == "table":
            rows = block.get("rows") or []
            if not rows:
                continue
            n_cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=n_cols)
            table.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, cell_text in enumerate(row):
                    table.cell(i, j).text = cell_text
        else:
            text = (block.get("text") or "").strip()
            if text:
                doc.add_paragraph(text)
    doc.save(out_path)
    return out_path


def text_to_blocks(text: str) -> list[dict]:
    """평문 → 문단 블록 (빈 줄 기준 분리)."""
    blocks = []
    for para in text.split("\n\n"):
        cleaned = " ".join(line.strip() for line in para.splitlines() if line.strip())
        if cleaned:
            blocks.append({"type": "p", "text": cleaned})
    return blocks
