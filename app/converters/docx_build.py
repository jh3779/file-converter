"""구조 블록 → DOCX 생성 (python-docx). HWP/PDF → DOCX 파이프라인 공용 (DEC-007).

블록 형식: {"type":"p","text":str} | {"type":"table","rows":[[str,...],...]}
레이아웃은 단순화된다 — 기대치 고지는 OQ-003/DEC-010 문안으로 UI에서 안내.

한글 글꼴을 모든 run에 명시적으로 지정한다(DEC-015) — python-docx 기본
스타일(Calibri)은 한글 글리프가 없고, 지정을 생략하면 뷰어·OS별로 대체
글꼴이 달라져 렌더링이 일관되지 않는다(실사용 중 글자 깨짐 재현·확인됨).
번들 글꼴 "Noto Sans KR"(OFL-1.1)을 앱·LibreOffice 양쪽에 동봉해 호스트
환경의 글꼴 설치 여부와 무관하게 항상 동일하게 렌더링되도록 한다.
"""
from pathlib import Path

EAST_ASIAN_FONT = "Noto Sans KR"


def _set_font(run):
    run.font.name = EAST_ASIAN_FONT
    # python-docx는 run.font.name을 서양(ascii) 글꼴에만 반영한다 — 동아시아
    # 문자 렌더링에 쓰이는 w:eastAsia는 별도로 XML에 직접 지정해야 한다.
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
    if rfonts is None:
        from docx.oxml.ns import qn
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    from docx.oxml.ns import qn
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), EAST_ASIAN_FONT)


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
                    cell = table.cell(i, j)
                    cell.text = cell_text
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            _set_font(run)
        else:
            text = (block.get("text") or "").strip()
            if text:
                p = doc.add_paragraph()
                run = p.add_run(text)
                _set_font(run)
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
