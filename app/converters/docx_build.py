"""구조 블록 → DOCX 생성 (python-docx). HWP/PDF → DOCX 파이프라인 공용 (DEC-007).

블록 형식: {"type":"p","text":str} | {"type":"table","rows":[[str,...],...]}
레이아웃은 단순화된다 — 기대치 고지는 OQ-003/DEC-010 문안으로 UI에서 안내.

한글 글꼴을 모든 run에 명시적으로 지정한다(DEC-015) — python-docx 기본
스타일(Calibri)은 한글 글리프가 없고, 지정을 생략하면 뷰어·OS별로 대체
글꼴이 달라져 렌더링이 일관되지 않는다(실사용 중 글자 깨짐 재현·확인됨).

글꼴은 번들 "Noto Sans KR"(OFL-1.1, engine/libreoffice에 동봉)을 쓴다.
**이 보장 범위는 우리 앱 자신의 렌더링 경로(DOCX/HWP→PDF)에 한정된다** —
그 경로에서는 이 폰트가 항상 사용 가능함을 실제로 검증했다. 결과 DOCX를
사용자가 자신의 Word/한글(HWP)에서 직접 열 때는 그 프로그램에 "Noto Sans
KR"이 설치돼 있지 않으면 다른 대체가 일어난다 — 대안으로 어느 Windows에나
있는 "맑은 고딕"을 1순위로 지정하는 시도를 로컬에서 검증했으나, 그 폰트가
없는 환경(예: 개발용 mac)에서 LibreOffice의 대체 로직이 무지정 상태보다
더 나쁜 대체를 골라 희귀 글자(뷁 등)의 매핑이 깨지는 회귀가 실측 확인되어
채택하지 않았다. 검증되지 않은 "개선"보다 검증된 현재 상태를 유지한다
(docs/06_open_questions.md 리스크 표에 외부 뷰어 잔여 리스크로 기록).
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
