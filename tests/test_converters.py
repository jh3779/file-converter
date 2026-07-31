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
from app.converters.docx_extract import docx_to_blocks
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

    def test_xlsx_to_csv_formats_dates_and_whole_number_floats(self):
        """엑셀에서 보던 모습(날짜 "2026-07-31", 정수 "3")과 다르게 파이썬
        객체를 그대로 str()해서 "2026-07-31 00:00:00"·"3.0"처럼 나오던 문제."""
        import datetime
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["날짜", "정수형태float", "일반소수", "문자열"])
        ws.append([datetime.date(2026, 7, 31), 3.0, 3.5, "그대로"])
        src = self.tmp / "d.xlsx"
        wb.save(src)

        out = data.xlsx_to_csv(src, self.tmp)
        rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
        self.assertEqual(rows[1], ["2026-07-31", "3", "3.5", "그대로"])

    def test_xlsx_sheet_count(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["a"])
        wb.create_sheet("두번째")
        src = self.tmp / "multi.xlsx"
        wb.save(src)
        self.assertEqual(data.xlsx_sheet_count(src), 2)

        wb2 = Workbook()
        wb2.active.append(["a"])
        src2 = self.tmp / "single.xlsx"
        wb2.save(src2)
        self.assertEqual(data.xlsx_sheet_count(src2), 1)

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

    def test_csv_to_json_preserves_embedded_newline_and_quotes(self):
        """셀 안에 줄바꿈·이스케이프된 큰따옴표가 있으면 값이 잘리던 버그
        (text.splitlines() 선분할 + Sniffer의 doublequote 오탐)."""
        src = self.tmp / "d.csv"
        with src.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([
                ["이름", "메모"],
                ["김철수", '비고: "특이사항, 있음"'],
                ["이영희", "여러줄\n텍스트 포함"],
            ])
        out = data.csv_to_json(src, self.tmp)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["메모"], '비고: "특이사항, 있음"')
        self.assertEqual(payload[1]["메모"], "여러줄\n텍스트 포함")

    def test_csv_to_json_semicolon_delimiter(self):
        src = self.tmp / "d.csv"
        src.write_text("a;b\n1;2\n", encoding="utf-8")
        out = data.csv_to_json(src, self.tmp)
        self.assertEqual(json.loads(out.read_text()), [{"a": "1", "b": "2"}])


class TestDocxExtractNumbering(Base):
    """코드 리뷰 지적: DOCX 자동 번호·불릿은 numbering.xml 서식일 뿐 문단
    텍스트가 아니므로, item.text만 추출하면 눈에 보이는 마커가 사라진다."""

    def test_style_based_numbered_and_bullet_list(self):
        from docx import Document
        src = self.tmp / "d.docx"
        doc = Document()
        doc.add_paragraph("일반 문단")
        doc.add_paragraph("첫 항목", style="List Number")
        doc.add_paragraph("둘째 항목", style="List Number")
        doc.add_paragraph("불릿 항목", style="List Bullet")
        doc.save(src)

        blocks = docx_to_blocks(src)
        texts = [b["text"] for b in blocks]
        self.assertEqual(texts, [
            "일반 문단", "1. 첫 항목", "2. 둘째 항목", "• 불릿 항목",
        ])

    def test_direct_numpr_without_named_style(self):
        """사용자가 툴바로 번호 매기기를 켠 경우 — 문단 자신의 pPr에 numPr이
        직접 있고(스타일 경유 아님), 목록 사이 일반 문단이 있어도 같은 numId의
        카운터는 이어진다."""
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        def add_numbered(doc, text, num_id="1", ilvl="0"):
            p = doc.add_paragraph(text)
            ppr = p._p.get_or_add_pPr()
            numpr = OxmlElement("w:numPr")
            e_ilvl = OxmlElement("w:ilvl")
            e_ilvl.set(qn("w:val"), ilvl)
            e_num = OxmlElement("w:numId")
            e_num.set(qn("w:val"), num_id)
            numpr.append(e_ilvl)
            numpr.append(e_num)
            ppr.append(numpr)
            return p

        src = self.tmp / "d.docx"
        doc = Document()
        add_numbered(doc, "목록 1")
        add_numbered(doc, "목록 2")
        doc.add_paragraph("목록 사이 일반 문단")
        add_numbered(doc, "목록 3")
        doc.save(src)

        blocks = docx_to_blocks(src)
        texts = [b["text"] for b in blocks]
        self.assertEqual(texts[2], "목록 사이 일반 문단")
        # numId=1의 서식(decimal/bullet 등)은 기본 템플릿에 따라 달라질 수
        # 있으므로 마커 문자 자체보다 "일반 문단은 그대로, 목록 항목에는
        # (스타일 경유 없이도) 접두어가 붙는다"는 불변식을 확인한다.
        self.assertNotEqual(texts[0], "목록 1")
        self.assertTrue(texts[0].endswith("목록 1"))
        self.assertNotEqual(texts[3], "목록 3")
        self.assertTrue(texts[3].endswith("목록 3"))


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
