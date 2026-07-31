"""v0.2 파이프라인 테스트 — HWP→DOCX(사이드카 필요 시 스킵), PDF→TXT/DOCX."""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import converters

REPO = Path(__file__).resolve().parents[1]
HWP_SAMPLE = REPO / "spike" / "hwplib" / "repo" / "sample_hwp" / "basic" / "표.hwp"
HWP_DISTRIBUTION = REPO / "spike" / "hwplib" / "repo" / "sample_hwp" / "distribution.hwp"


def _mini_pdf(path: Path):
    content = b"BT /F1 18 Tf 40 700 Td (Hello Converter) Tj ET"
    stream = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        stream,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buf = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(buf)
    buf += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (b"trailer\n<< /Size " + str(len(objs) + 1).encode() +
            b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF")
    path.write_bytes(buf)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPdf(Base):
    def test_pdf_to_txt(self):
        pdf = self.tmp / "mini.pdf"
        _mini_pdf(pdf)
        out = converters.convert(pdf, "txt", self.tmp)
        self.assertIn("Hello Converter", out.read_text(encoding="utf-8"))

    def test_pdf_to_docx(self):
        from docx import Document
        pdf = self.tmp / "mini.pdf"
        _mini_pdf(pdf)
        out = converters.convert(pdf, "docx", self.tmp)
        texts = [p.text for p in Document(out).paragraphs]
        self.assertTrue(any("Hello Converter" in t for t in texts))


def _find_soffice():
    from app.converters import office
    return office.find_soffice()


@unittest.skipUnless(_find_soffice(), "LibreOffice(soffice) 없음 — 로컬/Windows CI에서만 실행")
class TestOffice(Base):
    """DEC-016: PPTX→PDF는 DOCX→PDF와 동일한 office_to_pdf 경로를 재사용한다."""

    def test_docx_to_pdf(self):
        from docx import Document
        src = self.tmp / "한글.docx"
        doc = Document()
        doc.add_paragraph("한글 DOCX→PDF 테스트")
        doc.save(src)
        out = converters.convert(src, "pdf", self.tmp)
        self.assertEqual(out.read_bytes()[:5], b"%PDF-")

    def test_pptx_to_pdf(self):
        try:
            from pptx import Presentation
        except ImportError:
            self.skipTest("python-pptx 없음 — 테스트 전용 의존성(pip install python-pptx)")
        src = self.tmp / "한글.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "한글 PPTX→PDF 테스트"
        prs.save(src)
        out = converters.convert(src, "pdf", self.tmp)
        self.assertEqual(out.read_bytes()[:5], b"%PDF-")


@unittest.skipUnless(
    HWP_SAMPLE.exists() and shutil.which("java"),
    "hwplib 샘플/JDK 없음 — spike 빌드 후 실행 (RESULT.md)")
class TestHwp(Base):
    def test_hwp_to_docx_preserves_table(self):
        from docx import Document
        out = converters.convert(HWP_SAMPLE, "docx", self.tmp)
        tables = Document(out).tables
        self.assertTrue(tables)
        cells = [c.text for row in tables[0].rows for c in row.cells]
        self.assertTrue(any("ABC" in c for c in cells))

    def test_hwp_to_txt(self):
        out = converters.convert(HWP_SAMPLE, "txt", self.tmp)
        self.assertIn("ABC", out.read_text(encoding="utf-8"))

    @unittest.skipUnless(HWP_DISTRIBUTION.exists(), "distribution.hwp 샘플 없음")
    def test_distribution_protected_hwp_still_readable(self):
        """OQ-006: '배포용(복사방지)' 문서는 편집·인쇄 제한이지 텍스트 암호화가
        아니므로 일반 경로로 정상 추출된다 — err.password로 오분류하지 않는다."""
        out = converters.convert(HWP_DISTRIBUTION, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.strip())
        self.assertNotIn("�", text)

    def test_docx_to_hwp_roundtrip(self):
        """DEC-017: DOCX→HWP는 문단 텍스트를 보존하고, 표는 " | "로 이어붙인
        텍스트 문단으로 단순화한다. 결과 HWP를 다시 hwp_to_txt로 읽어 왕복
        검증한다(희귀 한글 자모·한자 포함)."""
        from docx import Document
        src = self.tmp / "한글.docx"
        doc = Document()
        doc.add_paragraph("뷁 밟 닳 넋 앎 옳 훑 흙 삵 값 넓 얹 앉 닭 없")
        doc.add_paragraph("大韓民國 韓國語 漢字 契約書 委任狀")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "이름"
        table.cell(0, 1).text = "부서"
        table.cell(1, 0).text = "김철수"
        table.cell(1, 1).text = "영업1팀"
        doc.save(src)

        out = converters.convert(src, "hwp", self.tmp)
        self.assertTrue(out.exists())

        back_dir = self.tmp / "back"
        back_dir.mkdir()
        back = converters.convert(out, "txt", back_dir)
        text = back.read_text(encoding="utf-8")
        self.assertIn("뷁 밟 닳 넋 앎 옳 훑 흙 삵 값 넓 얹 앉 닭 없", text)
        self.assertIn("大韓民國 韓國語 漢字 契約書 委任狀", text)
        self.assertIn("이름", text)
        self.assertIn("김철수", text)
        self.assertIn("영업1팀", text)

    def test_docx_to_hwp_preserves_long_wrapped_paragraph(self):
        """긴 문단(여러 줄로 감싸질 정도)이 HWP 레이아웃 캐시(LineSeg) 계산
        누락으로 실제 뷰어에서 겹쳐 보이던 문제 — hwplib 샘플 문서(distribution.hwp)
        구조를 근거로 sidecar/hwp/JsonToHwp.java가 줄바꿈을 계산하도록 수정.
        여기서는 파이썬 쪽에서 확인 가능한 텍스트 보존만 검증(레이아웃 구조
        자체는 로컬 스파이크로 별도 확인함)."""
        from docx import Document
        long_text = (
            "이것은 여러 줄로 감싸질 만큼 긴 문단입니다. " * 8
            + "뷁 밟 닳 넋 앎 옳 — 문단 끝 희귀 자모."
        )
        src = self.tmp / "긴문단.docx"
        doc = Document()
        doc.add_paragraph(long_text)
        doc.add_paragraph("짧은 두 번째 문단.")
        doc.save(src)

        out = converters.convert(src, "hwp", self.tmp)
        back_dir = self.tmp / "back"
        back_dir.mkdir()
        back = converters.convert(out, "txt", back_dir)
        text = back.read_text(encoding="utf-8")
        self.assertIn(long_text, text)
        self.assertIn("짧은 두 번째 문단.", text)

    def test_docx_to_hwp_preserves_numbered_and_bullet_markers(self):
        """코드 리뷰 지적: DOCX 자동 번호·불릿은 문단 텍스트(w:t)가 아니라
        numbering.xml 서식으로 화면에만 그려지므로, item.text만 추출하면
        눈에 보이는 마커가 조용히 사라진다 — docx_extract가 numbering.xml을
        해석해 마커를 문단 앞에 붙이는지 전체 파이프라인으로 검증."""
        from docx import Document
        src = self.tmp / "목록.docx"
        doc = Document()
        doc.add_paragraph("첫 번째 항목", style="List Number")
        doc.add_paragraph("두 번째 항목", style="List Number")
        doc.add_paragraph("불릿 항목", style="List Bullet")
        doc.save(src)

        out = converters.convert(src, "hwp", self.tmp)
        back_dir = self.tmp / "back"
        back_dir.mkdir()
        back = converters.convert(out, "txt", back_dir)
        text = back.read_text(encoding="utf-8")
        self.assertIn("1. 첫 번째 항목", text)
        self.assertIn("2. 두 번째 항목", text)
        self.assertIn("불릿 항목", text)
        self.assertIn("•", text)


if __name__ == "__main__":
    unittest.main()
