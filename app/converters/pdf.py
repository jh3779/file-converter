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
    """PDF → 텍스트+서식 추출 → DOCX (레이아웃 단순화는 여전함 — DEC-010 고지
    문안과 연동. 문자 서식(굵게/기울임/크기)은 DEC-027부터 반영).

    pdf2docx(PyMuPDF)는 AGPL이라 사용 금지(DEC-007과 동일한 라이선스 원칙).
    """
    from .docx_build import blocks_to_docx
    blocks = _extract_pdf_blocks(src)
    return blocks_to_docx(blocks, tmpdir / (src.stem + ".docx"))


def pdf_to_pptx(src: Path, tmpdir: Path) -> Path:
    """PDF → PPTX, 한 페이지=한 이미지로 뭉개지 않고 줄 단위로 위치를 재구성
    (DEC-030). 각 텍스트 줄을 원본과 같은 위치·크기의 개별 텍스트 상자로
    복원하고, 굵게 판정은 pdf_to_docx와 같은 폰트 이름 휴리스틱(_container_to_runs)을
    그대로 재사용한다. 이미지(LTImage)·사각형(LTRect)·직선(LTLine)·일반
    곡선(LTCurve)도 원본과 같은 위치·크기로 재구성한다(DEC-036) — 표 테두리는
    대개 LTLine(또는 LTRect)로 그려지므로 이제 실제로 옮겨진다.

    **알려진 한계(정직하게 문서화, 스파이크로 직접 확인)**: (1) LTCurve(사각형·
    직선이 아닌 일반 곡선, 베지어 등)는 제어점을 그대로 직선으로 이은 다각형
    으로 근사한다 — 정확한 곡률은 재현되지 않는다(드문 경우, 표/도형 대부분은
    LTRect·LTLine). (2) 벡터·텍스트 사이의 원래 z-순서(위/아래 겹침)는 완전히
    보존되지 않는다 — 도형·이미지를 먼저 그리고 텍스트를 그 위에 올리는
    "배경 레이어" 방식으로 단순화(텍스트가 항상 보이는 게 더 흔한 실사용
    요구). (3) 디코딩 실패한 이미지(드문 필터·손상 데이터)는 조용히 건너뛴다
    (텍스트 보존 우선 원칙과 동일, `pdfminer.image.ImageWriter`가 처리 못하는
    포맷). (4) 재구성에 항상 Noto Sans KR을 지정하므로(DEC-015와 같은 이유)
    원본 폰트와 글자 폭이 달라 드물게 줄바꿈이 살짝 밀릴 수 있다. (5) 기울임은
    한글 글꼴 대부분에 별도 이탤릭 글리프가 없어(CJK 타이포그래피 관행)
    감지되지 않는 경우가 흔함(pdf_to_docx와 동일한 제약).
    """
    from pptx import Presentation
    from pptx.util import Emu, Pt
    from pptx.enum.text import MSO_ANCHOR

    EMU_PER_PT = 12700
    image_dir = tmpdir / "_pdf_pptx_images"
    layout = _extract_pdf_layout(src, image_dir)
    if not layout:
        raise ConversionError("err.corrupted", "페이지 없음")

    prs = Presentation()
    prs.slide_width = Emu(round(layout[0]["width"] * EMU_PER_PT))
    prs.slide_height = Emu(round(layout[0]["height"] * EMU_PER_PT))
    blank_layout = prs.slide_layouts[6]

    for page in layout:
        slide = prs.slides.add_slide(blank_layout)
        page_h = page["height"]
        for visual in page["visuals"]:
            _add_visual_to_slide(slide, visual, page_h, EMU_PER_PT)
        for line in page["lines"]:
            x0, y0, x1, y1 = line["bbox"]
            left = Emu(round(x0 * EMU_PER_PT))
            top = Emu(round((page_h - y1) * EMU_PER_PT))
            width = Emu(max(round((x1 - x0) * EMU_PER_PT), 1))
            height = Emu(max(round((y1 - y0) * EMU_PER_PT), 1))
            box = slide.shapes.add_textbox(left, top, width, height)
            tf = box.text_frame
            tf.word_wrap = False
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.TOP
            p = tf.paragraphs[0]
            for r in line["runs"]:
                run = p.add_run()
                run.text = r["text"]
                run.font.bold = r["bold"]
                run.font.italic = r["italic"]
                if r["size"]:
                    run.font.size = Pt(r["size"])
                run.font.name = "Noto Sans KR"

    out = tmpdir / (src.stem + ".pptx")
    prs.save(out)
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


def _extract_pdf_layout(src: Path, image_dir: Path) -> list[dict]:
    """PDF → 페이지별 [{"width","height","lines":[{"bbox","runs"}],"visuals":[...]}]
    — pdf_to_pptx 전용, 줄 단위 위치(bbox)까지 필요해 문단 단위로 합치는
    _extract_pdf_blocks와는 분리했다(서식 판정 로직 자체는 _container_to_runs를
    그대로 재사용). image_dir은 임베디드 이미지를 디코딩해 저장할 폴더
    (호출자의 tmpdir 하위 — 변환 종료 후 자동 정리됨)."""
    from pdfminer.high_level import extract_pages
    from pdfminer.image import ImageWriter
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.psparser import PSException

    image_dir.mkdir(parents=True, exist_ok=True)
    writer = ImageWriter(str(image_dir))

    pages = []
    try:
        for page in extract_pages(str(src)):
            lines = []
            for container in _paragraph_candidates(page):
                for line in _iter_lines(container):
                    runs = _container_to_runs(line)
                    if runs:
                        lines.append({"bbox": line.bbox, "runs": runs})
            visuals = [
                v for item in _iter_visuals(page)
                if (v := _visual_to_dict(item, writer, image_dir)) is not None
            ]
            pages.append({"width": page.width, "height": page.height, "lines": lines, "visuals": visuals})
    except PDFPasswordIncorrect:
        raise ConversionError("err.password")
    except (PSException, ValueError, OSError) as e:
        raise ConversionError("err.corrupted", str(e))
    return pages


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


def _add_visual_to_slide(slide, visual: dict, page_h: float, emu_per_pt: int):
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Emu, Pt

    kind = visual["kind"]
    x0, y0, x1, y1 = visual["bbox"]

    if kind == "image":
        left = Emu(round(x0 * emu_per_pt))
        top = Emu(round((page_h - y1) * emu_per_pt))
        width = Emu(max(round((x1 - x0) * emu_per_pt), 1))
        height = Emu(max(round((y1 - y0) * emu_per_pt), 1))
        try:
            slide.shapes.add_picture(visual["path"], left, top, width, height)
        except Exception:
            pass  # 저장은 됐지만 python-pptx가 못 여는 포맷 — 조용히 생략
        return

    linewidth = max(visual.get("linewidth") or 0.75, 0.25)

    if kind == "line":
        lx0, ly0 = visual["p0"]
        lx1, ly1 = visual["p1"]
        conn = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Emu(round(lx0 * emu_per_pt)), Emu(round((page_h - ly0) * emu_per_pt)),
            Emu(round(lx1 * emu_per_pt)), Emu(round((page_h - ly1) * emu_per_pt)),
        )
        if visual["stroke"]:
            conn.line.color.rgb = RGBColor(*visual["stroke"])
        conn.line.width = Pt(linewidth)
        return

    if kind == "rect":
        left = Emu(round(x0 * emu_per_pt))
        top = Emu(round((page_h - y1) * emu_per_pt))
        width = Emu(max(round((x1 - x0) * emu_per_pt), 1))
        height = Emu(max(round((y1 - y0) * emu_per_pt), 1))
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    else:  # curve — 다각형 근사(freeform)
        pts = visual["pts"]
        if len(pts) < 2:
            return
        start_x, start_y = pts[0][0] * emu_per_pt, (page_h - pts[0][1]) * emu_per_pt
        fb = slide.shapes.build_freeform(start_x=start_x, start_y=start_y, scale=1.0)
        fb.add_line_segments(
            [(px * emu_per_pt, (page_h - py) * emu_per_pt) for px, py in pts[1:]], close=True)
        shape = fb.convert_to_shape()

    if visual.get("fill"):
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*visual["fill"])
    else:
        shape.fill.background()

    if visual.get("stroke"):
        shape.line.color.rgb = RGBColor(*visual["stroke"])
        shape.line.width = Pt(linewidth)
    else:
        shape.line.fill.background()


def _extract_pdf_blocks(src: Path) -> list[dict]:
    """PDF → 문단 블록(서식 포함, DEC-027). pdfminer의 레이아웃 트리를 재귀
    순회해 "문단 하나"로 볼 수 있는 단위마다 글자 단위로 훑어 굵게/기울임/
    크기가 바뀌는 지점마다 run을 새로 만든다.

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
    아니라 원본 자체에 감지할 서식이 없는 것. **밑줄은 감지하지 않는다** —
    PDF는 밑줄을 폰트 속성이 아니라 별도의 벡터 선(그림)으로 그리는 경우가
    많아 이 휴리스틱(폰트 이름 기반)으로는 원천적으로 판별할 수 없다(모든
    PDF run은 항상 underline=False — HWP→DOCX만 밑줄을 지원, DEC-027).
    텍스트 보존은 서식 감지 실패와 무관하게 항상 보장한다(서식 불명 시
    bold=False/italic=False로 안전하게 처리).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfminer.psparser import PSException

    blocks = []
    try:
        for page in extract_pages(str(src)):
            for container in _paragraph_candidates(page):
                runs = _container_to_runs(container)
                if runs:
                    blocks.append({"type": "p", "runs": runs})
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


def _container_to_runs(container) -> list[dict]:
    from pdfminer.layout import LTChar

    runs = []
    cur_text = []
    cur_style = (False, False, None)  # (bold, italic, size) — 셋 중 하나라도 바뀌면 run 분리

    def flush():
        if cur_text:
            bold, italic, size = cur_style
            runs.append({"text": "".join(cur_text), "bold": bool(bold),
                         "italic": bool(italic), "underline": False,
                         "size": size, "color": None})

    for ch in _iter_chars(container):
        if isinstance(ch, LTChar):
            fontname = ch.fontname.lower()
            style = ("bold" in fontname, "italic" in fontname or "oblique" in fontname,
                     round(ch.size, 1))
            text = ch.get_text()
        else:
            # LTAnno(가상 문자 — 줄바꿈·자간 보정 등, 폰트 정보 없음): 현재
            # run에 그대로 이어붙이고 서식 전환은 트리거하지 않는다. PDF의
            # 줄바꿈은 문단 내부 개행일 뿐이라(문단 경계는 컨테이너 단위로
            # 이미 나뉨) 공백으로 정규화한다(text_to_blocks()와 같은 원칙).
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


def pdf_to_images(src: Path, tmpdir: Path) -> Path:
    """PDF → 페이지별 PNG, 원본 파일명 폴더 안에 저장 (DEC-025).

    pypdfium2(Apache-2.0/BSD-3-Clause, permissive) 사용 — LibreOffice의
    `--convert-to png`는 다중 페이지 PDF에서 첫 페이지 1장만 내보내는 것을
    직접 확인해 채택하지 않았다(엔진 조사 기록: DEC-025).

    반환값이 폴더 경로라는 점에서 다른 컨버터와 다르다 — output.py의
    finalize()가 결과가 폴더인지 파일인지 자동으로 판단해 처리한다.
    """
    import pypdfium2 as pdfium
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
                bitmap.to_pil().save(out_dir / f"page_{i:0{width}d}.png")
            finally:
                bitmap.close()
                page.close()
        return out_dir
    finally:
        doc.close()
