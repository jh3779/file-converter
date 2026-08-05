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
