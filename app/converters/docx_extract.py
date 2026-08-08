"""DOCX → 구조 블록 (python-docx). DOCX→HWP 파이프라인 1단계 (docx_build.blocks_to_docx의 역방향).

블록 형식: {"type":"p","text":str,"align":"left"|"center"|"right"|"justify"(선택)} |
{"type":"table","rows":[[str,...],...]}
문서 순서(본문에 등장하는 순서)대로 문단·표를 함께 추출한다 — python-docx는
document.paragraphs/document.tables를 각각 따로 주기 때문에 body XML을 직접
순회해야 순서가 보존된다.

문단 정렬(DEC-040): 문단에 직접 지정된 정렬(w:jc)만 읽고, 없으면 "align"
필드 자체를 생략한다 — HWP 쪽 문서 기본 정렬(양쪽 정렬)을 그대로 두고,
사용자가 실제로 지정한 정렬만 덮어쓰기 위함.

번호·불릿 목록 주의: DOCX의 자동 번호("1.", "가.")·불릿("•")은 문단의 실제
텍스트(w:t)가 아니라 numbering.xml에 정의된 서식이 뷰어에 의해 화면에만
그려지는 것이라, item.text만 추출하면 눈에 보이는 마커가 조용히 사라진다
(코드 리뷰 지적, 실제 재현 확인 후 보완). 소수(decimal)·로마자·알파벳·불릿
서식은 numbering.xml을 해석해 마커 문자열을 만들어 문단 앞에 붙인다.
다단계 중첩 목록의 상위 레벨 변경 시 하위 레벨 카운터 재시작 등 OOXML
번호 매기기의 전체 규칙(요소 restart·startOverride 등)까지는 재현하지
않는다 — (numId, ilvl) 쌍별로 문서 순서대로 단순 증가하는 카운터를 쓴다.
지원하지 않는 서식(예: 사용자 정의 다단계 서식)은 마커 없이 본문만 유지한다
(내용 유실은 없음 — 마커만 생략).
"""
from pathlib import Path

_ROMAN_VALUES = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def _to_roman(n: int) -> str:
    out = []
    for value, symbol in _ROMAN_VALUES:
        count, n = divmod(n, value)
        out.append(symbol * count)
    return "".join(out)


def _to_letter(n: int) -> str:
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("a") + rem))
    return "".join(reversed(letters))


def _format_marker(numfmt: str, lvltext: str, n: int) -> str | None:
    if numfmt == "bullet":
        return "•"
    if numfmt == "decimal":
        value = str(n)
    elif numfmt == "decimalZero":
        value = f"{n:02d}"
    elif numfmt == "upperRoman":
        value = _to_roman(n)
    elif numfmt == "lowerRoman":
        value = _to_roman(n).lower()
    elif numfmt == "upperLetter":
        value = _to_letter(n).upper()
    elif numfmt == "lowerLetter":
        value = _to_letter(n)
    else:
        return None  # 지원하지 않는 서식 — 마커 생략(본문 텍스트는 유지)
    if lvltext and "%" in lvltext:
        import re
        return re.sub(r"%\d+", value, lvltext, count=1)
    return value + "."


def _numbering_levels(document):
    """{numId: {ilvl: (numFmt, lvlText, start)}} — numId는 문자열(w:val 원문)."""
    from docx.oxml.ns import qn

    try:
        numbering_el = document.part.numbering_part.element
    except Exception:
        return {}

    abstract_levels: dict[str, dict[str, tuple]] = {}
    for abstract_num in numbering_el.findall(qn("w:abstractNum")):
        abstract_id = abstract_num.get(qn("w:abstractNumId"))
        levels = {}
        for lvl in abstract_num.findall(qn("w:lvl")):
            ilvl = lvl.get(qn("w:ilvl"))
            numfmt_el = lvl.find(qn("w:numFmt"))
            lvltext_el = lvl.find(qn("w:lvlText"))
            start_el = lvl.find(qn("w:start"))
            numfmt = numfmt_el.get(qn("w:val")) if numfmt_el is not None else "decimal"
            lvltext = lvltext_el.get(qn("w:val")) if lvltext_el is not None else "%1."
            try:
                start = int(start_el.get(qn("w:val"))) if start_el is not None else 1
            except (TypeError, ValueError):
                start = 1
            levels[ilvl] = (numfmt, lvltext, start)
        abstract_levels[abstract_id] = levels

    result: dict[str, dict[str, tuple]] = {}
    for num in numbering_el.findall(qn("w:num")):
        num_id = num.get(qn("w:numId"))
        abstract_id_el = num.find(qn("w:abstractNumId"))
        if abstract_id_el is None:
            continue
        abstract_id = abstract_id_el.get(qn("w:val"))
        if abstract_id in abstract_levels:
            result[num_id] = abstract_levels[abstract_id]
    return result


def _paragraph_numpr(paragraph):
    """문단 자신 또는(직접 지정이 없으면) 적용된 스타일 체인에서 numPr을 찾는다.
    "List Number"·"List Bullet" 같은 내장 스타일은 문단이 아니라 스타일 쪽에
    numPr이 있다 — 실제 생성 DOCX로 확인함."""
    from docx.oxml.ns import qn

    ppr = paragraph._p.find(qn("w:pPr"))
    numpr = ppr.find(qn("w:numPr")) if ppr is not None else None
    if numpr is None:
        style = paragraph.style
        seen = set()
        while style is not None and id(style) not in seen:
            seen.add(id(style))
            style_ppr = style.element.find(qn("w:pPr"))
            if style_ppr is not None:
                numpr = style_ppr.find(qn("w:numPr"))
                if numpr is not None:
                    break
            style = getattr(style, "base_style", None)
    if numpr is None:
        return None
    num_id_el = numpr.find(qn("w:numId"))
    ilvl_el = numpr.find(qn("w:ilvl"))
    if num_id_el is None:
        return None
    num_id = num_id_el.get(qn("w:val"))
    if num_id == "0":  # 0은 "목록 아님"(번호 제거)을 뜻하는 예약값
        return None
    ilvl = ilvl_el.get(qn("w:val")) if ilvl_el is not None else "0"
    return num_id, ilvl


_ALIGN_TO_STR = {
    "LEFT": "left", "CENTER": "center", "RIGHT": "right",
    "JUSTIFY": "justify", "JUSTIFY_MED": "justify", "JUSTIFY_HI": "justify",
    "JUSTIFY_LOW": "justify", "DISTRIBUTE": "justify", "THAI_JUSTIFY": "justify",
}


def _paragraph_align(paragraph) -> str | None:
    """문단에 직접 지정된 정렬만 읽는다(스타일에서 물려받는 값은 안 봄 —
    style.paragraph_format.alignment까지 걸어야 하는데, 이 프로젝트가
    다루는 실사용 문서에서 정렬은 거의 항상 문단에 직접 지정돼 있어
    범위 밖으로 둠, DEC-040). None이면 이 필드 자체를 블록에 안 실어
    HWP 쪽 문서 기본 정렬(양쪽 정렬)을 그대로 따르게 한다 — 명시적으로
    지정된 경우만 덮어쓴다."""
    alignment = paragraph.alignment
    if alignment is None:
        return None
    return _ALIGN_TO_STR.get(alignment.name)


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
    levels = _numbering_levels(doc)
    counters: dict[tuple, int] = {}
    blocks: list[dict] = []
    for item in _iter_block_items(doc):
        if isinstance(item, Table):
            rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            if any(cell for row in rows for cell in row):
                blocks.append({"type": "table", "rows": rows})
        else:
            text = item.text.strip()
            if not text:
                continue
            numpr = _paragraph_numpr(item)
            if numpr is not None:
                num_id, ilvl = numpr
                level = levels.get(num_id, {}).get(ilvl)
                if level is not None:
                    numfmt, lvltext, start = level
                    key = (num_id, ilvl)
                    counters[key] = counters.get(key, start - 1) + 1
                    marker = _format_marker(numfmt, lvltext, counters[key])
                    if marker:
                        text = f"{marker} {text}"
            block = {"type": "p", "text": text}
            align = _paragraph_align(item)
            if align:
                block["align"] = align
            blocks.append(block)
    return blocks
