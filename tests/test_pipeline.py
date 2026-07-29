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


if __name__ == "__main__":
    unittest.main()
