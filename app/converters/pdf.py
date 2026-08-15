"""PDF 읽기 공유 프리미티브 + PDF→TXT/이미지 (REQ-F-004).

PDF→DOCX(pdf_docx.py)·PDF→PPTX(pdf_pptx.py)는 별도 파일이다 — 이 모듈이
제공하는 저수준 추출 함수(_paragraph_candidates·_iter_lines·_container_to_runs·
_iter_visuals·_visual_to_dict 등)를 두 "작성 어댑터"가 나눠 재사용하고,
각자는 DOCX(OOXML)·PPTX(python-pptx 셰이프) 고유의 출력 방식만 담당한다
(구조 감사, 2026-08 — 세 관심사가 원래 pdf.py 한 파일에 섞여 있었음).
`_extract_pdf_blocks_by_page`(HWP 전용, hwp.py/hwpx.py가 소비)도 이 모듈에
남는다 — DOCX/PPTX 어느 쪽 작성 로직에도 속하지 않는 세 번째 소비자다.
"""
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
    text = _fix_symbol_font_pua(text)
    out = tmpdir / (src.stem + ".txt")
    out.write_text(text, encoding="utf-8")
    return out


def _iter_lines(container):
    """컨테이너의 직계 LTTextLine들을 낸다. 줄로 안 묶인 컨테이너(LTFigure
    등, _paragraph_candidates 참고)는 통째로 줄 하나처럼 취급한다."""
    from pdfminer.layout import LTTextLine

    found_line = False
    for item in container:
        if isinstance(item, LTTextLine):
            found_line = True
            yield item
    if not found_line:
        yield container


_ALIGN_TOL = 3.0  # pt — 글자 위치 반올림오차 허용치


def _detect_alignment(container, page_width: float) -> str | None:
    """문단(컨테이너) 안 줄들의 가로 위치(bbox)로 정렬을 추정한다(DEC-040) —
    판정 로직 자체는 _classify_alignment(순수 함수, 단위 테스트 대상)에
    있고, 여기서는 pdfminer 컨테이너에서 줄별 bbox만 뽑아 넘긴다."""
    boxes = [line.bbox for line in _iter_lines(container)]
    return _classify_alignment(boxes, page_width)


def _classify_alignment(boxes: list[tuple[float, float, float, float]], page_width: float) -> str | None:
    """줄별 bbox((x0,y0,x1,y1), ...) 목록으로 정렬을 추정하는 순수 판정
    로직(DEC-040) — pdfminer 객체에 의존하지 않아 hand-crafted bbox로
    직접 단위 테스트할 수 있다.

    PDF는 정렬 자체를 담지 않는다 — 글자마다 절대 좌표만 있어, 렌더링된
    좌표에서 역산하는 수밖에 없다. 판단 근거가 약하면(짧은 문단·애매한
    여백) None을 돌려줘 "align" 필드 자체를 생략한다 — 잘못 추정해 원래
    의도와 다른 정렬로 억지로 맞추는 것보다, 아무것도 안 하는(문서 기본
    정렬 유지) 쪽이 안전하다는 원칙(DEC-027의 "서식 불명 시 안전한 기본값"과
    같은 태도).

    한 줄짜리 문단: 좌우 여백이 비슷하면 가운데(페이지 중심 기준이라 문서의
    실제 여백 폭을 몰라도 판단 가능). **오른쪽 정렬도, 왼쪽 정렬도 한
    줄만으로는 확정하지 않는다** — "오른쪽 여백이 작다"는 게 문서의 실제
    오른쪽 여백이 원래 좁아서인지 정말 오른쪽 정렬이라서인지 한 줄만
    봐서는 구분할 근거가 없다(페이지 가장자리에 딱 붙어야만 판단 가능한
    값이 되어 버려 실사용 문서의 정상적인 여백을 가진 오른쪽 정렬을 대부분
    놓친다 — 로컬 검증 중 발견해 범위를 좁힘). 처음엔 "오른쪽으로 확정 안
    하니 왼쪽으로 명시하자"로 구현했었는데, 그러면 한 줄짜리 오른쪽 정렬
    날짜·서명·짧은 제목 같은 실사용 문서의 정상 사례를 "left"로 확정해
    버리는 다른 방향의 오분류가 생겼다(자동 리뷰로 발견,
    `_classify_alignment([(400,700,540,712)], 612)`로 재현 확인 — 왼쪽
    여백 400·오른쪽 여백 72로 명백히 오른쪽에 가까운데 "left"가 나왔음) —
    "왼쪽인지 오른쪽인지 한 줄로는 모른다"가 정확한 상태이므로 None(판단
    보류)이 맞다. 여러 줄 문단의 오른쪽 정렬은 아래처럼 다른 방식(줄마다
    오른쪽 끝이 서로 일치하는지, 문서의 실제 여백 값과 무관)으로 판단해
    이 문제가 없다.
    여러 줄 문단: 마지막 줄을 뺀 "본문 줄"이 최소 2개 있어야 오른쪽·양쪽
    정렬을 판단한다 — 본문 줄이 1개뿐이면(전체 2줄 문단) 그 한 줄의 오른쪽
    끝과 "일치 비교"할 대상이 자기 자신뿐이라 항상 참이 되어, 평범한 2줄
    왼쪽 정렬 문단이 양쪽 정렬로 잘못 분류되는 회귀가 있었다(자동 리뷰로
    발견, `_classify_alignment([(72,700,300,712),(72,680,500,692)], 612)`로
    재현 확인 — 2줄 왼쪽 정렬인데 "justify"가 나왔음). 본문 줄이 부족하면
    오른쪽·양쪽 판정은 포기하고 왼쪽·가운데만 확인한다(부족한 근거로
    확정하지 않는다는 이 함수의 기본 원칙과 일치). 왼쪽 끝만 일치하면
    "left"를 명시적으로 돌려준다 — 왼쪽·오른쪽 끝이 둘 다 일치하면 양쪽,
    오른쪽만 일치하면 오른쪽, 어느 쪽도 아니면 각 줄의 중심이 일치하는지로
    가운데 정렬만 추가로 확인한다."""
    if not boxes:
        return None

    if len(boxes) == 1:
        x0, _, x1, _ = boxes[0]
        left_margin = x0
        right_margin = page_width - x1
        if left_margin <= _ALIGN_TOL:
            return None  # 왼쪽 여백이 거의 없음 — 판단 근거 부족
        if abs(left_margin - right_margin) <= _ALIGN_TOL * 2:
            return "center"
        return None  # 왼쪽인지 오른쪽인지 한 줄만으로는 판단 안 함(위 설명)

    lefts = [b[0] for b in boxes]
    rights_body = [b[2] for b in boxes[:-1]]  # 마지막 줄은 양쪽 정렬이어도 보통 짧다
    left_consistent = (max(lefts) - min(lefts)) <= _ALIGN_TOL
    # 본문 줄이 최소 2개는 있어야 "일치"가 의미 있다 — 1개뿐이면 항상 자기
    # 자신과 같아 무조건 참이 되므로(2줄 문단 오분류 버그, 위 설명) 오른쪽·
    # 양쪽 판정 자체를 포기한다.
    right_consistent = len(rights_body) >= 2 and (max(rights_body) - min(rights_body)) <= _ALIGN_TOL

    if left_consistent and right_consistent:
        # 알려진 한계(자동 리뷰 지적, 재현 확인·의도적으로 안 고침): 모든
        # 줄의 폭이 우연히 똑같은 가운데 정렬 문단은 좌우 끝이 둘 다
        # 일치해 버려 여기서 "justify"로 잘못 나올 수 있다. "좌우 여백이
        # 페이지 중심 기준으로 대칭인지"를 추가 판별 신호로 써서 가운데로
        # 우선시키는 방안도 검토했으나, 좌우 여백이 똑같은(예: 1인치 표준
        # 여백) 페이지의 흔한 진짜 양쪽 정렬 문단까지 가운데로 오분류하는
        # 더 나쁜 회귀가 생김을 재현으로 확인해 채택하지 않았다(희귀한
        # 엣지 케이스 하나보다 흔한 케이스를 깨뜨리지 않는 쪽을 택함).
        return "justify"
    if left_consistent:
        return "left"  # 왼쪽 정렬 — 명시적으로 반환(생략하면 HWP 기본값인 양쪽 정렬로 해석됨)
    if right_consistent:
        return "right"
    centers = [(b[0] + b[2]) / 2 for b in boxes]
    if max(centers) - min(centers) <= _ALIGN_TOL:
        return "center"
    return None


def _iter_visuals(container):
    """레이아웃 트리를 재귀 순회하며 이미지·벡터 도형(LTImage/LTRect/LTLine/
    LTCurve)을 찾는다. 텍스트 추출(_paragraph_candidates)과는 별개의 순회다
    — 이미지는 LTFigure 안에 중첩돼 있고 선/사각형은 대개 페이지 최상위에
    바로 있어(로컬 스파이크로 확인), 같은 트리를 목적에 맞게 두 번 걷는 편이
    하나로 합치는 것보다 단순하다."""
    from pdfminer.layout import LTContainer, LTCurve, LTImage

    for item in container:
        if isinstance(item, LTImage):
            yield item
        elif isinstance(item, LTCurve):  # LTRect·LTLine도 LTCurve의 하위 클래스
            yield item
        if isinstance(item, LTContainer):
            yield from _iter_visuals(item)


def _pdf_color_to_rgb(color) -> tuple[int, int, int] | None:
    """PDF 색상값(그레이스케일 float, RGB/CMYK 튜플)을 (r,g,b) 0~255 정수
    튜플로 변환한다. 이름 있는 색상(문자열)은 로컬 재현 범위 밖이라 변환
    실패 시 None을 돌려주고 호출자가 기본값(선 없음/채움 없음)으로 처리한다
    — 색상 미표현이 도형 자체의 유실로 이어지지는 않는다."""
    if color is None:
        return None
    try:
        if isinstance(color, (int, float)):
            v = round(color * 255)
            return (v, v, v)
        if isinstance(color, (list, tuple)):
            if len(color) == 3:
                return tuple(round(c * 255) for c in color)
            if len(color) == 4:
                c, m, y, k = color
                return (
                    round(255 * (1 - c) * (1 - k)),
                    round(255 * (1 - m) * (1 - k)),
                    round(255 * (1 - y) * (1 - k)),
                )
    except (TypeError, ValueError):
        pass
    return None


def _visual_to_dict(item, writer, image_dir: Path) -> dict | None:
    from pdfminer.layout import LTImage, LTLine, LTRect

    if isinstance(item, LTImage):
        try:
            name = writer.export_image(item)
        except Exception:
            return None  # 디코딩 실패(드문 필터·손상 데이터) — 조용히 건너뜀
        return {"kind": "image", "bbox": item.bbox, "path": str(image_dir / name)}

    stroke = _pdf_color_to_rgb(item.stroking_color) if item.stroke else None
    fill = _pdf_color_to_rgb(item.non_stroking_color) if item.fill else None
    if isinstance(item, LTRect):
        return {"kind": "rect", "bbox": item.bbox, "stroke": stroke, "fill": fill,
                "linewidth": item.linewidth}
    if isinstance(item, LTLine):
        return {"kind": "line", "bbox": item.bbox, "p0": item.pts[0], "p1": item.pts[1],
                "stroke": stroke, "linewidth": item.linewidth}
    # 사각형·직선이 아닌 일반 LTCurve — 제어점을 직선으로 이은 다각형으로 근사.
    return {"kind": "curve", "bbox": item.bbox, "pts": list(item.pts),
            "stroke": stroke, "fill": fill, "linewidth": item.linewidth}


def _extract_pdf_blocks_by_page(src: Path) -> list[dict]:
    """PDF → 문단 블록(평문, 페이지 경계 보존 — DEC-039). pdf_to_hwp 전용
    (app/converters/hwp.py·hwpx.py가 소비).

    기존 pdf_to_hwp는 pdf_to_txt()(pdfminer extract_text())로 문서 전체를
    한 문자열로 뽑은 뒤 빈 줄 기준으로만 문단을 나눴는데, extract_text()가
    페이지가 바뀌는 지점을 별도로 표시하지 않아 PDF 여러 페이지의 텍스트가
    HWP 안에서 페이지 구분 없이 한 페이지처럼 이어 붙어 보였다(외부 QA
    피드백으로 재현 확인). extract_pages()로 페이지 단위로 직접 순회해 각
    페이지 첫 문단에 pageBreakBefore를 표시한다(JsonToHwp.java가 이를 실제
    쪽 나눔으로 반영). 서식(굵게 등)은 이 경로에서 필요 없어
    _container_to_runs로 뽑은 run들의 텍스트만 이어붙인다. 정렬(DEC-040)은
    _detect_alignment로 함께 추정해 JsonToHwp.java에 전달한다.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.psparser import PSException

    blocks = []
    try:
        for page_index, page in enumerate(extract_pages(str(src))):
            first_on_page = True
            for container in _paragraph_candidates(page):
                text = "".join(r["text"] for r in _container_to_runs(container))
                # JsonToHwp.java는 text.trim().isEmpty()인 문단을 버린다
                # (sidecar/hwp/JsonToHwp.java) — 여기서 공백뿐인 컨테이너를
                # "의미 있는 첫 문단"으로 인정하면, pageBreakBefore가 그
                # 컨테이너에 붙었다가 JsonToHwp 쪽에서 통째로 버려져 실제
                # 첫 문단에는 쪽 나눔이 반영되지 않는 버그가 있었다(자동
                # 리뷰로 발견) — 같은 기준(strip 후 빈 문자열)으로 걸러
                # first_on_page를 소비하지 않게 한다.
                if not text.strip():
                    continue
                block = {"type": "p", "text": text}
                if page_index > 0 and first_on_page:
                    block["pageBreakBefore"] = True
                align = _detect_alignment(container, page.width)
                if align:
                    block["align"] = align
                blocks.append(block)
                first_on_page = False
    except PDFPasswordIncorrect:
        raise ConversionError("err.password")
    except (PSException, ValueError, OSError) as e:
        raise ConversionError("err.corrupted", str(e))
    return blocks


def _paragraph_candidates(obj):
    """레이아웃 트리를 재귀 순회하며 "문단 하나"로 취급할 컨테이너를 찾는다.

    페이지 최상위 텍스트는 pdfminer가 이미 LTTextContainer(문단)로 잘
    묶어주지만, Form XObject(LTFigure — 예: 벡터 그래픽 안에 그려진 텍스트,
    일부 PDF 생성기가 텍스트 박스를 XObject로 감싸는 경우) 내부는 그렇게
    묶이지 않고 LTChar가 그대로 흩어져 있다(로컬 재현 확인: extract_text()는
    이 텍스트를 잡아내는데 LTTextContainer만 훑는 순회는 조용히 놓침 —
    코드 리뷰로 발견). LTFigure를 재귀적으로 더 훑어 중첩된 텍스트까지
    문단 후보로 모은다.
    """
    from pdfminer.layout import LTAnno, LTChar, LTContainer, LTTextContainer

    if isinstance(obj, LTTextContainer):
        yield obj
        return
    if isinstance(obj, LTContainer):
        if any(isinstance(c, (LTChar, LTAnno)) for c in obj):
            yield obj  # LTFigure처럼 글자를 직접 담은(줄로 안 묶인) 컨테이너
        for child in obj:
            if not isinstance(child, (LTChar, LTAnno)):
                yield from _paragraph_candidates(child)


_UNDERLINE_MAX_SLOPE_PT = 2.0  # pt — 이보다 기울면 밑줄 후보에서 제외(표 테두리 대각선 등)
_UNDERLINE_MAX_GAP_PT = 4.0  # pt — 글자 bbox 아래로 이 거리 안에 있는 선만 밑줄로 인정
_UNDERLINE_MIN_OVERLAP_RATIO = 0.4  # 글자 폭 대비 선과 겹치는 비율 최소치


def _underline_candidates(visuals: list[dict]) -> list[dict]:
    """페이지 visuals(pdf_docx.py의 이미지·표 테두리 반영 개선이 이미
    뽑아둔 것)에서 밑줄 후보만 {"x0","x1","y","visual"} 딕셔너리로
    추린다 — LTLine 중 거의 수평(기울기가 작은)인 선만 후보다. 표
    테두리·구분선 등 다른 용도의 수평선도 섞여 나올 수 있지만, 실제
    밑줄 판정은 텍스트 바로 아래 짧은 거리 안에 있는지로 한 번 더
    거른다(_char_is_underlined). "visual"에는 원본 visual dict를 그대로
    담아둬, 실제로 밑줄로 쓰인 선은 나중에 그 dict에 표시(_char_is_underlined
    참고)해 표 테두리 도형으로 중복 렌더링(w:pBdr)되지 않게 한다 — 밑줄은
    이미 run의 underline=True(python-docx의 실제 밑줄 서식)로 반영되므로
    같은 선을 도형으로도 그리면 겹쳐 보인다. `_container_to_runs`(이
    파일)가 직접 호출하는 `_char_is_underlined`와 짝을 이루므로, DOCX
    전용 기능이지만(호출자는 pdf_docx.py뿐) 순환 import를 피하려 이
    공유 모듈에 둔다."""
    out = []
    for v in visuals:
        if v["kind"] != "line":
            continue
        (lx0, ly0), (lx1, ly1) = v["p0"], v["p1"]
        if abs(ly1 - ly0) > _UNDERLINE_MAX_SLOPE_PT:
            continue
        out.append({"x0": min(lx0, lx1), "x1": max(lx0, lx1), "y": (ly0 + ly1) / 2, "visual": v})
    return out


def _char_is_underlined(ch, segments: list[dict]) -> bool:
    """글자 하나의 bbox 아래쪽(밑줄이 실제로 그려지는 자리)에 겹치는
    벡터 선이 있는지 본다. 기준점은 bbox 중간이 아니라 bbox 아래쪽
    끝(y0)이다 — pdfminer가 표준 14 폰트(Helvetica 등)의 glyph bbox를
    실제 잉크 범위가 아니라 폰트 자체의 ascent/descent로 균일하게 매겨
    (로컬 검증으로 확인), y0가 대략 폰트 디센트 라인(베이스라인보다
    약간 아래)과 같다 — 실제 밑줄은 베이스라인 바로 아래에 그려지므로
    y0 근방(살짝 위·아래 모두 허용)에 있어야 한다. 다만 글자 중간
    높이(bbox 세로 중앙)보다 위에 있는 선은 취소선일 가능성이 높아
    제외한다. 매치되면 그 선의 원본 visual dict에 "_used_as_underline"
    표시를 남긴다(호출자가 이 표시로 표 테두리 도형 렌더링에서 걸러낼
    수 있게)."""
    x0, y0, x1, y1 = ch.bbox
    mid_y = (y0 + y1) / 2
    for seg in segments:
        seg_x0, seg_x1, seg_y = seg["x0"], seg["x1"], seg["y"]
        if seg_y > mid_y:
            continue  # 취소선 등 글자 중간·위쪽 높이 — 밑줄 아님
        if y0 - seg_y > _UNDERLINE_MAX_GAP_PT:
            continue  # bbox 아래쪽 끝보다 너무 많이 처져 있으면 다른 용도의 선
        overlap = min(x1, seg_x1) - max(x0, seg_x0)
        if overlap > 0 and overlap >= (x1 - x0) * _UNDERLINE_MIN_OVERLAP_RATIO:
            seg["visual"]["_used_as_underline"] = True
            return True
    return False


# LibreOffice/Word가 목록 기호를 Symbol 글꼴로 그려 PDF에 구울 때, 임베드된
# 서브셋 폰트가 (3,0) "Microsoft Symbol" cmap 관례에 따라 문자 코드를 그대로
# 0xF000+코드로 인코딩하는 경우가 흔하다(실사용 문서 재현: LibreOffice가 Word
# "List Bullet" 스타일을 구울 때 JAAAAA+SymbolMT 서브셋 폰트의 0xB7을 U+F0B7로
# 내보냄). pdfminer는 이 사설 영역(PUA) 코드를 있는 그대로 넘겨줘서, 원본 글꼴이
# 없는 뷰어(Word/Google Docs 등)에서는 빈 칸(tofu)으로 보인다. Adobe Symbol
# 인코딩은 어느 OS·오피스 버전에서도 동일한 고정 표준이라(PDF를 만든 환경에
# 따라 달라지지 않음) 알려진 코드만 안전하게 원래 유니코드 기호로 되돌린다.
_SYMBOL_FONT_PUA_MAP = {
    "": "•",  # Symbol 글꼴 0xB7 "bullet" — MS Office "List Bullet" 스타일 기본 기호
}


def _fix_symbol_font_pua(text: str) -> str:
    for pua, real in _SYMBOL_FONT_PUA_MAP.items():
        if pua in text:
            text = text.replace(pua, real)
    return text


def _iter_chars(container):
    """컨테이너 안의 LTChar/LTAnno를 순서대로 낸다. LTTextContainer(문단)
    안의 LTTextLine(줄) 한 겹, 또는 LTFigure처럼 줄로 안 묶이고 글자를
    바로 담은 컨테이너 둘 다 처리한다."""
    from pdfminer.layout import LTAnno, LTChar, LTTextLine

    for item in container:
        if isinstance(item, LTTextLine):
            yield from _iter_chars(item)
        elif isinstance(item, (LTChar, LTAnno)):
            yield item


def _container_to_runs(container, underline_segments: list[dict] | None = None) -> list[dict]:
    """컨테이너(문단 또는 줄)를 글자 단위로 훑어 굵게/기울임/크기/밑줄이
    바뀌는 지점마다 run을 새로 만든다(DEC-027, pdf_docx.py·pdf_pptx.py 공용).

    굵게/기울임 판정은 pdfminer가 넘겨주는 폰트 리소스 이름(LTChar.fontname,
    예: "Caladea-Bold")에 "Bold"/"Italic"/"Oblique" 문자열이 포함되는지 보는
    휴리스틱이다 — PDF 자체에 "이 글자가 굵다"는 명시적 플래그가 없어 폰트
    이름에 의존할 수밖에 없다. **로컬 검증 결과, 이 휴리스틱은 굵기별로
    폰트 파일이 실제로 분리돼 있을 때만(한글 폰트 포함, 예: NotoSansKR-Bold·
    AppleSDGothicNeo-Bold 등 — 실사용 문서 대부분이 이런 폰트를 씀) 정확히
    동작함을 확인했다.** 다만 두 가지 알려진 한계가 있다: (1) 문서에 동아시아
    글꼴을 명시하지 않아 렌더러가 임의의 대체 글꼴 하나로 뭉뚱그려 그리면
    굵기 정보 자체가 사라져 감지 불가(로컬 재현 확인), (2) 기울임은 한글
    글꼴 대부분이 별도 이탤릭 글리프가 없어(CJK 타이포그래피 관행) 애초에
    렌더러가 반영하지 않는 경우가 흔함 — 이 경우 우리 휴리스틱의 실패가
    아니라 원본 자체에 감지할 서식이 없는 것.

    밑줄은 폰트 속성이 아니라 별도의 벡터 선(그림)으로 그려지는 경우가
    많아 굵게/기울임과 같은 폰트 이름 휴리스틱으로는 원천적으로 판별할
    수 없다(PDF→DOCX 밑줄 감지 개선) — 호출자가 `underline_segments`
    (페이지의 근사-수평 벡터 선을 (x0,x1,y) 튜플로 미리 추린 목록,
    `_underline_candidates` 참고)를 넘겨주면 각 글자의 bbox 바로 아래에
    겹치는 선이 있는지로 판별한다(`_char_is_underlined`). 넘기지 않으면
    (기본값 None, pdf_pptx.py·pdf_to_hwp 등 다른 호출자) 항상
    underline=False — 이 판정 자체가 필요 없는 경로에서 매 글자마다
    선 목록을 대조하는 비용을 안 치르게 한다. 텍스트 보존은 서식 감지
    실패와 무관하게 항상 보장한다(서식 불명 시 bold=False/italic=False/
    underline=False로 안전하게 처리).
    """
    from pdfminer.layout import LTChar

    runs = []
    cur_text = []
    cur_style = (False, False, None, False)  # (bold, italic, size, underline) — 넷 중 하나라도 바뀌면 run 분리

    def flush():
        if cur_text:
            bold, italic, size, underline = cur_style
            runs.append({"text": "".join(cur_text), "bold": bool(bold),
                         "italic": bool(italic), "underline": bool(underline),
                         "size": size, "color": None})

    for ch in _iter_chars(container):
        if isinstance(ch, LTChar):
            fontname = ch.fontname.lower()
            underline = (_char_is_underlined(ch, underline_segments)
                         if underline_segments else False)
            style = ("bold" in fontname, "italic" in fontname or "oblique" in fontname,
                     round(ch.size, 1), underline)
            text = _fix_symbol_font_pua(ch.get_text())
        else:
            # LTAnno(가상 문자 — 줄바꿈·자간 보정 등, 폰트 정보 없음): 현재
            # run에 그대로 이어붙이고 서식 전환은 트리거하지 않는다. PDF의
            # 줄바꿈은 문단 내부 개행일 뿐이라(문단 경계는 컨테이너 단위로
            # 이미 나뉨) 공백으로 정규화한다.
            text = ch.get_text()
            text = " " if text == "\n" else text
            style = cur_style

        if style != cur_style and cur_text:
            flush()
            cur_text = []
        cur_style = style
        cur_text.append(text)
    flush()

    if runs:
        runs[0]["text"] = runs[0]["text"].lstrip()
        runs[-1]["text"] = runs[-1]["text"].rstrip()
        runs = [r for r in runs if r["text"]]
    return runs


_PDF_IMAGE_PILLOW_FORMAT = {"png": "PNG", "jpg": "JPEG"}


def pdf_to_images(src: Path, tmpdir: Path, ext: str = "png") -> Path:
    """PDF → 페이지별 이미지(PNG 또는 JPG), 원본 파일명 폴더 안에 저장
    (DEC-026, JPG 옵션은 DEC-043 — 외부 QA 피드백: PNG만 지원하던 것을 확장).

    pypdfium2(Apache-2.0/BSD-3-Clause, permissive) 사용 — LibreOffice의
    `--convert-to png`는 다중 페이지 PDF에서 첫 페이지 1장만 내보내는 것을
    직접 확인해 채택하지 않았다(엔진 조사 기록: DEC-026). PDF 페이지 렌더링
    결과(`bitmap.to_pil()`)는 항상 알파 채널 없는 RGB라 JPEG 저장 시 다른
    이미지 변환(image.py)처럼 투명 배경을 흰색으로 합성하는 처리가 필요
    없음을 로컬에서 직접 확인했다.

    반환값이 폴더 경로라는 점에서 다른 컨버터와 다르다 — output.py의
    finalize()가 결과가 폴더인지 파일인지 자동으로 판단해 처리한다.
    """
    import pypdfium2 as pdfium
    fmt = _PDF_IMAGE_PILLOW_FORMAT[ext]
    try:
        doc = pdfium.PdfDocument(src)
    except pdfium.PdfiumError as e:
        key = "err.password" if "password" in str(e).lower() else "err.corrupted"
        raise ConversionError(key, str(e))
    try:
        n_pages = len(doc)
        if n_pages == 0:
            raise ConversionError("err.corrupted", "페이지 없음")
        out_dir = tmpdir / src.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        width = len(str(n_pages))
        for i, page in enumerate(doc, start=1):
            bitmap = page.render(scale=2.0)
            try:
                bitmap.to_pil().save(out_dir / f"page_{i:0{width}d}.{ext}", format=fmt)
            finally:
                bitmap.close()
                page.close()
        return out_dir
    finally:
        doc.close()
