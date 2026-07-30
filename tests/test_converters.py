"""데이터 변환기·출력 규칙 테스트: python -m unittest discover tests"""
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.converters import data
from app.converters.base import ConversionError
from app.converters.docx_build import EAST_ASIAN_FONT, blocks_to_docx
from app.output import unique_output_path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestCsvXlsx(Base):
    def test_roundtrip_korean(self):
        src = self.tmp / "한글데이터.csv"
        rows = [["이름", "수량"], ["김철수", "3"], ["이영희", "5"]]
        with src.open("w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)
        xlsx = data.csv_to_xlsx(src, self.tmp)
        self.assertTrue(xlsx.exists())
        back_dir = self.tmp / "back"
        back_dir.mkdir()
        back = data.xlsx_to_csv(xlsx, back_dir)
        text = back.read_text(encoding="utf-8-sig")
        self.assertIn("김철수", text)
        self.assertIn("이영희", text)

    def test_cp949_read(self):
        src = self.tmp / "euckr.csv"
        src.write_bytes("제품,가격\n노트북,1200000\n".encode("cp949"))
        out = data.csv_to_json(src, self.tmp)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["제품"], "노트북")


class TestCsvJson(Base):
    def test_csv_to_json_headers(self):
        src = self.tmp / "d.csv"
        src.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        out = data.csv_to_json(src, self.tmp)
        self.assertEqual(json.loads(out.read_text()), [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])

    def test_json_to_csv_dicts_union_keys(self):
        src = self.tmp / "d.json"
        src.write_text(json.dumps([{"a": 1}, {"a": 2, "b": "x"}]), encoding="utf-8")
        out = data.json_to_csv(src, self.tmp)
        rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
        self.assertEqual(rows[0], ["a", "b"])
        self.assertEqual(rows[2], ["2", "x"])

    def test_json_bad_shape(self):
        src = self.tmp / "d.json"
        src.write_text('{"not": "a list"}', encoding="utf-8")
        with self.assertRaises(ConversionError) as ctx:
            data.json_to_csv(src, self.tmp)
        self.assertEqual(ctx.exception.key, "err.jsonshape")


class TestDocxBuildFont(Base):
    """DEC-015: 생성 DOCX는 한글 글꼴을 모든 run에 명시해야 한다 — 실사용 중
    글자 깨짐이 재현된 근본 원인(글꼴 미지정 → 뷰어별 대체 글꼴 불일치)."""

    def test_paragraph_and_table_runs_declare_east_asian_font(self):
        blocks = [
            {"type": "p", "text": "한글 문단"},
            {"type": "table", "rows": [["셀1", "셀2"]]},
        ]
        out = blocks_to_docx(blocks, self.tmp / "out.docx")

        import zipfile
        with zipfile.ZipFile(out) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn(f'w:eastAsia="{EAST_ASIAN_FONT}"', xml)
        self.assertIn(f'w:ascii="{EAST_ASIAN_FONT}"', xml)

        from docx import Document
        doc = Document(out)
        for p in doc.paragraphs:
            for run in p.runs:
                self.assertEqual(run.font.name, EAST_ASIAN_FONT)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            self.assertEqual(run.font.name, EAST_ASIAN_FONT)


class TestOutputNaming(Base):
    def test_auto_rename_never_overwrites(self):
        (self.tmp / "r.pdf").write_text("existing")
        p1 = unique_output_path(self.tmp, "r", "pdf")
        self.assertEqual(p1.name, "r (1).pdf")
        p1.write_text("second")
        p2 = unique_output_path(self.tmp, "r", "pdf")
        self.assertEqual(p2.name, "r (2).pdf")


if __name__ == "__main__":
    unittest.main()
