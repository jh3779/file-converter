"""HWPX 변환 테스트 — QA(h) Phase 1(읽기, 외부 QA 요청).

hwpxlib(spike/hwpxlib/RESULT.md) 로컬 빌드가 있을 때만 실행된다(사이드카가
필요 없는 다른 테스트들과 달리 실제 JRE + hwpxlib 클래스로 sidecar를
실행해야 함 — tests/test_pipeline.py의 TestHwp와 같은 조건).
hwpxlib 저장소 자체의 테스트 픽스처(testFile/tool/textextractor/*.hwpx)를
그대로 쓴다 — 이 프로젝트 저장소에는 hwpx 샘플을 직접 넣지 않는다(제3자
문서를 저장소에 넣지 않는다는 기존 관례, DEC-032와 같은 원칙).
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app import converters

REPO = Path(__file__).resolve().parents[1]
HWPX_SAMPLE = REPO / "spike" / "hwpxlib" / "repo" / "testFile" / "tool" / "textextractor" / "multipara.hwpx"
HWPX_TABLE_SAMPLE = REPO / "spike" / "hwpxlib" / "repo" / "testFile" / "tool" / "textextractor" / "Table.hwpx"


def _find_soffice():
    from app.converters import office
    return office.find_soffice()


def _make_tab_hwpx(out_path: Path):
    """MakeTabHwpx(테스트 전용 디버그 도구, sidecar/hwp/MakeTabHwpx.java)를
    실행해 "가나"+Tab+"다라" 문단 하나짜리 최소 HWPX를 만든다 — test_pipeline.py의
    _run_linesegdebug와 같은 패턴(로컬 build.sh 산출물을 subprocess로 직접 실행)."""
    from app.converters import hwp as hwp_mod
    java = hwp_mod._java()
    cp = hwp_mod._classpath()
    proc = subprocess.run([java, "-cp", cp, "MakeTabHwpx", str(out_path)],
                           capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


@unittest.skipUnless(
    HWPX_SAMPLE.exists() and shutil.which("java"),
    "hwpxlib 샘플/JDK 없음 — spike/hwpxlib/RESULT.md 절차로 로컬 빌드 후 실행")
class TestHwpx(Base):
    def test_hwpx_to_txt(self):
        out = converters.convert(HWPX_SAMPLE, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertIn("김하성", text)

    def test_hwpx_to_docx_preserves_paragraphs(self):
        from docx import Document
        out = converters.convert(HWPX_SAMPLE, "docx", self.tmp)
        texts = [p.text for p in Document(out).paragraphs]
        self.assertTrue(any("김하성" in t for t in texts))
        self.assertGreater(len(texts), 1)  # 여러 문단으로 나뉘어 있어야 함(한 덩어리로 뭉개지면 안 됨)

    def test_hwpx_to_docx_preserves_table(self):
        from docx import Document
        out = converters.convert(HWPX_TABLE_SAMPLE, "docx", self.tmp)
        tables = Document(out).tables
        self.assertTrue(tables)
        rows = [[c.text for c in row.cells] for row in tables[0].rows]
        self.assertEqual(rows[0], ["이름", "국어", "영어", "수학"])
        self.assertIn(["개똥이", "89", "65", "78"], rows)

    def test_hwpx_to_docx_preserves_char_formatting(self):
        """Table.hwpx의 "날짜" 문단은 기울임+빨간색으로 서식이 지정돼 있다
        (로컬 조사로 확인, spike/hwpxlib/RESULT.md) — HwpxToJson의 CharPr
        추출이 실제로 동작하는지 회귀 확인."""
        from docx import Document
        out = converters.convert(HWPX_TABLE_SAMPLE, "docx", self.tmp)
        runs = [r for p in Document(out).paragraphs for r in p.runs if r.text.strip()]
        by_text = {r.text.strip(): r for r in runs}
        self.assertIn("날짜", by_text)
        self.assertTrue(by_text["날짜"].font.italic)

    def test_hwpx_tab_normalized_to_space_not_dropped(self):
        """HwpxToJson(HWPX→DOCX/PDF 경로, HWPX→TXT는 hwpxlib 자체
        TextExtractor를 써서 별도)의 extractTextFrom이 Tab(TItem)을 조용히
        건너뛰면 탭 앞뒤 텍스트가 공백 없이 그대로 붙어버리는 회귀가
        있었다(수정 확인용) — "가나"+Tab+"다라"가 "가나다라"로 뭉개지지
        않고 "가나 다라"로 나와야 한다."""
        from docx import Document
        src = self.tmp / "tab.hwpx"
        _make_tab_hwpx(src)
        out = converters.convert(src, "docx", self.tmp)
        texts = [p.text for p in Document(out).paragraphs]
        self.assertIn("가나 다라", texts)
        self.assertNotIn("가나다라", texts)

    @unittest.skipUnless(_find_soffice(), "LibreOffice(soffice) 없음 — 로컬/Windows CI에서만 실행")
    def test_hwpx_to_pdf(self):
        out = converters.convert(HWPX_SAMPLE, "pdf", self.tmp)
        self.assertEqual(out.read_bytes()[:5], b"%PDF-")


if __name__ == "__main__":
    unittest.main()
