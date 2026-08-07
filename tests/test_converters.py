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
from app.converters.pdf import _classify_alignment
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

    def test_xlsx_to_csv_uses_first_sheet_not_active_tab(self):
        """코드 리뷰 지적: wb.active는 "첫 번째 시트"가 아니라 파일이 마지막
        저장 시점에 열려 있던 탭이다. UI 고지 문구는 "첫 번째 시트만
        변환돼요"이므로, 두 번째 시트가 활성 탭이어도 실제로는 첫 번째
        시트가 나가야 한다."""
        from openpyxl import Workbook
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "첫번째"
        ws1.append(["첫번째시트데이터"])
        ws2 = wb.create_sheet("두번째")
        ws2.append(["두번째시트데이터"])
        wb.active = 1  # 두 번째 시트를 활성 탭으로 저장(실사용에서 흔한 상태)
        src = self.tmp / "d.xlsx"
        wb.save(src)

        out = data.xlsx_to_csv(src, self.tmp)
        text = out.read_text(encoding="utf-8-sig")
        self.assertIn("첫번째시트데이터", text)
        self.assertNotIn("두번째시트데이터", text)

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


class TestDocxExtractAlignment(Base):
    """DEC-040: 문단에 직접 지정된 정렬만 읽는다(스타일 상속은 범위 밖).
    명시적으로 지정 안 된 문단은 "align" 필드 자체를 안 실어 HWP 쪽 문서
    기본 정렬(양쪽 정렬)을 그대로 따르게 한다."""

    def test_explicit_alignment_extracted(self):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        src = self.tmp / "d.docx"
        doc = Document()
        doc.add_paragraph("기본")
        p_center = doc.add_paragraph("가운데")
        p_center.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_right = doc.add_paragraph("오른쪽")
        p_right.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_left = doc.add_paragraph("왼쪽 명시")
        p_left.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_justify = doc.add_paragraph("양쪽")
        p_justify.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        doc.save(src)

        blocks = docx_to_blocks(src)
        by_text = {b["text"]: b.get("align") for b in blocks}
        self.assertIsNone(by_text["기본"])
        self.assertNotIn("align", next(b for b in blocks if b["text"] == "기본"))
        self.assertEqual(by_text["가운데"], "center")
        self.assertEqual(by_text["오른쪽"], "right")
        self.assertEqual(by_text["왼쪽 명시"], "left")
        self.assertEqual(by_text["양쪽"], "justify")


class TestPdfAlignmentClassification(unittest.TestCase):
    """DEC-040: _classify_alignment는 pdfminer 객체 없이 줄별 bbox만으로
    판정하는 순수 함수라 hand-crafted bbox로 직접 검증할 수 있다(실제
    pdfminer 파싱을 거친 end-to-end 검증은 tests/test_format_fidelity.py에
    별도로 있음)."""

    PAGE_W = 612.0

    def test_single_line_no_signal_returns_none(self):
        self.assertIsNone(_classify_alignment([(72, 700, 200, 712)], self.PAGE_W))

    def test_single_line_centered(self):
        self.assertEqual(_classify_alignment([(206, 700, 406, 712)], self.PAGE_W), "center")

    def test_single_line_right_not_detected(self):
        """한 줄만으로는 오른쪽 정렬을 판단하지 않는다 — "오른쪽 여백이
        작다"가 문서의 정상적인 여백인지 진짜 오른쪽 정렬인지 한 줄만
        봐서는 구분할 근거가 없다(로컬 검증 중 발견해 범위를 좁힘)."""
        self.assertIsNone(_classify_alignment([(400, 700, 540, 712)], self.PAGE_W))

    def test_single_line_flush_with_left_edge_returns_none(self):
        self.assertIsNone(_classify_alignment([(0, 700, 200, 712)], self.PAGE_W))

    def test_multi_line_left_aligned_returns_none(self):
        boxes = [(72, 700, 300, 712), (72, 680, 500, 692), (72, 660, 150, 672)]
        self.assertIsNone(_classify_alignment(boxes, self.PAGE_W))

    def test_multi_line_right_aligned(self):
        boxes = [(300, 700, 540, 712), (100, 680, 540, 692), (400, 660, 540, 672)]
        self.assertEqual(_classify_alignment(boxes, self.PAGE_W), "right")

    def test_multi_line_justified_last_line_short(self):
        boxes = [(72, 700, 540, 712), (72, 680, 540, 692), (72, 660, 200, 672)]
        self.assertEqual(_classify_alignment(boxes, self.PAGE_W), "justify")

    def test_multi_line_centered(self):
        boxes = [(200, 700, 412, 712), (150, 680, 462, 692), (250, 660, 362, 672)]
        self.assertEqual(_classify_alignment(boxes, self.PAGE_W), "center")

    def test_multi_line_ambiguous_returns_none(self):
        boxes = [(50, 700, 200, 712), (300, 680, 500, 692), (80, 660, 550, 672)]
        self.assertIsNone(_classify_alignment(boxes, self.PAGE_W))

    def test_empty_boxes_returns_none(self):
        self.assertIsNone(_classify_alignment([], self.PAGE_W))


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


class TestDocxBuildAlignment(Base):
    """DEC-040: "align"이 있는 블록만 명시적으로 정렬을 설정하고, 없으면
    DOCX 기본 정렬(왼쪽, python-docx의 None)을 그대로 둔다."""

    def test_align_field_sets_paragraph_alignment(self):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        blocks = [
            {"type": "p", "text": "기본"},
            {"type": "p", "text": "가운데", "align": "center"},
            {"type": "p", "text": "오른쪽", "align": "right"},
            {"type": "p", "text": "왼쪽", "align": "left"},
            {"type": "p", "text": "양쪽", "align": "justify"},
        ]
        out = blocks_to_docx(blocks, self.tmp / "out.docx")
        doc = Document(out)
        by_text = {p.text: p.alignment for p in doc.paragraphs}
        self.assertIsNone(by_text["기본"])
        self.assertEqual(by_text["가운데"], WD_ALIGN_PARAGRAPH.CENTER)
        self.assertEqual(by_text["오른쪽"], WD_ALIGN_PARAGRAPH.RIGHT)
        self.assertEqual(by_text["왼쪽"], WD_ALIGN_PARAGRAPH.LEFT)
        self.assertEqual(by_text["양쪽"], WD_ALIGN_PARAGRAPH.JUSTIFY)


class TestOutputNaming(Base):
    def test_auto_rename_never_overwrites(self):
        (self.tmp / "r.pdf").write_text("existing")
        p1 = unique_output_path(self.tmp, "r", "pdf")
        self.assertEqual(p1.name, "r (1).pdf")
        p1.write_text("second")
        p2 = unique_output_path(self.tmp, "r", "pdf")
        self.assertEqual(p2.name, "r (2).pdf")

    def test_finalize_concurrent_same_stem_never_overwrites(self):
        """숨은 버그(내부 감사): 같은 파일을 두 번 추가해 같은 포맷으로 동시
        변환하면(QThreadPool, 최대 4개 동시 — workers.py) 두 워커가 거의
        동시에 finalize()를 호출한다. "이름 충돌 확인 → 이동"이 원자적이지
        않으면(TOCTOU) 둘 다 같은 "충돌 없음" 경로를 계산해 한쪽이 다른 쪽
        결과물을 조용히 덮어쓴다 — 실제 스레드로 재현 확인 후 락으로 수정."""
        import threading
        from app.output import finalize

        source = self.tmp / "r.docx"
        source.write_text("원본")
        tmp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)

        results = []
        barrier = threading.Barrier(4)

        def worker(label):
            tmp_out = tmp_root / f"produced_{label}.pdf"
            tmp_out.write_text(label)
            barrier.wait()
            out, renamed = finalize(tmp_out, source, "pdf")
            results.append(str(out))

        threads = [threading.Thread(target=worker, args=(c,)) for c in "ABCD"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(set(results)), 4)  # 네 결과 경로가 전부 달라야 함
        pdfs = [p for p in self.tmp.iterdir() if p.suffix == ".pdf"]
        self.assertEqual(len(pdfs), 4)  # 실제로 4개 파일 모두 생성(덮어쓰기 없음)


if __name__ == "__main__":
    unittest.main()
