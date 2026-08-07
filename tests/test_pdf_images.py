"""PDF→이미지(페이지별, 폴더 결과물) 테스트 — DEC-026(PNG)·DEC-043(JPG 추가).

핵심 검증: 원본 파일명 폴더가 생성되고 그 안에 페이지 수만큼 이미지가
생기는지, PNG/JPG 각각 실제로 그 포맷·확장자로 저장되는지,
output.finalize()가 폴더 결과물을 파일과 동일하게 원자적으로 처리하는지
(충돌 시 자동 리네임 포함).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import converters
from app.converters.base import ConversionError
from app.output import finalize


def _mini_pdf_pages(path: Path, n: int):
    """_mini_pdf(test_pipeline.py)와 같은 원리의 최소 PDF를 페이지 n개로 생성."""
    page_obj_start = 3
    font_obj_num = page_obj_start + 2 * n
    kids, page_bodies, content_bodies = [], [], []
    for i in range(n):
        page_idx = page_obj_start + 2 * i
        content_idx = page_idx + 1
        kids.append(f"{page_idx} 0 R")
        content = f"BT /F1 18 Tf 40 700 Td (Page {i + 1}) Tj ET".encode()
        stream = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        page_bodies.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_idx} 0 R"
            f" /Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>".encode())
        content_bodies.append(stream)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [" + " ".join(kids) + f"] /Count {n} >>").encode(),
    ]
    for pb, cb in zip(page_bodies, content_bodies):
        objs.append(pb)
        objs.append(cb)
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

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


class TestPdfToImages(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_multi_page_pdf_produces_one_png_per_page_in_named_folder(self):
        src = self.tmp / "report.pdf"
        _mini_pdf_pages(src, 3)
        out_dir = converters.convert(src, "png", self.tmp)
        self.assertTrue(out_dir.is_dir())
        self.assertEqual(out_dir.name, "report")
        pages = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(pages, ["page_1.png", "page_2.png", "page_3.png"])

    def test_single_page_pdf_produces_one_image(self):
        src = self.tmp / "single.pdf"
        _mini_pdf_pages(src, 1)
        out_dir = converters.convert(src, "png", self.tmp)
        self.assertEqual([p.name for p in out_dir.iterdir()], ["page_1.png"])

    def test_ten_plus_pages_zero_padded_for_correct_sort(self):
        src = self.tmp / "long.pdf"
        _mini_pdf_pages(src, 11)
        out_dir = converters.convert(src, "png", self.tmp)
        names = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(names[0], "page_01.png")
        self.assertEqual(names[-1], "page_11.png")

    def test_jpg_target_produces_jpeg_files_with_jpg_extension(self):
        """DEC-043: PNG만 지원하던 것을 JPG까지 확장(외부 QA 피드백) —
        확장자·실제 저장 포맷(Pillow가 인식하는 진짜 JPEG인지) 둘 다 확인."""
        from PIL import Image
        src = self.tmp / "report.pdf"
        _mini_pdf_pages(src, 2)
        out_dir = converters.convert(src, "jpg", self.tmp)
        pages = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(pages, ["page_1.jpg", "page_2.jpg"])
        with Image.open(out_dir / "page_1.jpg") as im:
            self.assertEqual(im.format, "JPEG")

    def test_png_target_produces_real_png_files(self):
        from PIL import Image
        src = self.tmp / "single.pdf"
        _mini_pdf_pages(src, 1)
        out_dir = converters.convert(src, "png", self.tmp)
        with Image.open(out_dir / "page_1.png") as im:
            self.assertEqual(im.format, "PNG")

    def test_corrupted_pdf_rejected(self):
        src = self.tmp / "broken.pdf"
        src.write_bytes(b"not a real pdf")
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(src, "png", self.tmp)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_finalize_moves_folder_and_renames_on_collision(self):
        """폴더 결과물도 파일과 동일하게 원자적 이동 + 충돌 시 자동 리네임되는지
        (output.py의 기존 파일 전용 로직을 폴더까지 확장한 부분의 핵심 검증)."""
        src_dir = Path(tempfile.mkdtemp())
        src = src_dir / "doc.pdf"
        _mini_pdf_pages(src, 2)
        try:
            produced1 = converters.convert(src, "png", self.tmp)
            out1, renamed1 = finalize(produced1, src, "png")
            self.assertTrue(out1.is_dir())
            self.assertEqual(out1.name, "doc")
            self.assertFalse(renamed1)

            produced2 = converters.convert(src, "png", self.tmp)
            out2, renamed2 = finalize(produced2, src, "png")
            self.assertTrue(renamed2)
            self.assertEqual(out2.name, "doc (1)")
            self.assertTrue(out2.is_dir())
            self.assertEqual(len(list(out2.iterdir())), 2)
        finally:
            shutil.rmtree(src_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
