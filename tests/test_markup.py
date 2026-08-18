"""TXT/MD/HTML 상호 변환 테스트 (DEC-061) — 6방향(TXT↔MD, TXT↔HTML, MD↔HTML)
전부 + 구현 중 실제로 발견해 수정한 회귀(제목 태그 유출, 인라인 태그로 인한
줄바꿈 깨짐, TXT→MD 이스케이프)를 함께 검증한다.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import converters


class TestMarkupConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- TARGETS 등록 ---

    def test_markup_exts_mutually_target_each_other_excluding_self(self):
        for ext in ("txt", "md", "html"):
            targets = converters.targets_for(ext)
            self.assertNotIn(ext, targets)
            for other in ("txt", "md", "html"):
                if other != ext:
                    self.assertIn(other, targets)

    # --- TXT → HTML ---

    def test_txt_to_html_paragraphs_and_linebreaks(self):
        src = self.tmp / "a.txt"
        src.write_text("첫 줄\n두 번째 줄\n\n다음 문단", encoding="utf-8")
        out = converters.convert(src, "html", self.tmp)
        html = out.read_text(encoding="utf-8")
        self.assertIn("<p>첫 줄<br>\n두 번째 줄</p>", html)
        self.assertIn("<p>다음 문단</p>", html)

    def test_txt_to_html_escapes_special_chars(self):
        src = self.tmp / "b.txt"
        src.write_text("<script>alert(1)</script> & 문단", encoding="utf-8")
        out = converters.convert(src, "html", self.tmp)
        html = out.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)

    # --- TXT → MD ---

    def test_txt_to_md_escapes_markdown_syntax(self):
        import markdown

        src = self.tmp / "c.txt"
        text = "# 안내\n* 목록처럼 보이는 줄\n1. 숫자로 시작하는 줄\n[각주]처럼 보이는 텍스트"
        src.write_text(text, encoding="utf-8")
        out = converters.convert(src, "md", self.tmp)
        escaped = out.read_text(encoding="utf-8")
        self.assertNotEqual(escaped, text)  # 실제로 이스케이프가 일어났는지

        rendered = markdown.markdown(escaped, extensions=["extra"])
        # 원본이 진짜 제목/목록/링크로 재해석되지 않아야 한다
        self.assertNotIn("<h1>", rendered)
        self.assertNotIn("<li>", rendered)
        self.assertNotIn("<a href", rendered)
        # 원본 텍스트가 눈에 보이는 형태로는 그대로 남아 있어야 한다
        for fragment in ("안내", "목록처럼 보이는 줄", "숫자로 시작하는 줄", "각주"):
            self.assertIn(fragment, rendered)

    # --- MD → HTML ---

    def test_md_to_html_renders_table_and_emphasis(self):
        src = self.tmp / "d.md"
        src.write_text(
            "# 제목\n\n**굵게** 텍스트\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
            encoding="utf-8",
        )
        out = converters.convert(src, "html", self.tmp)
        html = out.read_text(encoding="utf-8")
        self.assertIn("<h1>제목</h1>", html)
        self.assertIn("<strong>굵게</strong>", html)
        self.assertIn("<table>", html)

    # --- MD → TXT (MD→HTML→TXT 파이프라인 재사용) ---

    def test_md_to_txt_strips_markup(self):
        src = self.tmp / "e.md"
        src.write_text("# 제목\n\n**굵게** 문단.\n", encoding="utf-8")
        out = converters.convert(src, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("#", text)
        self.assertNotIn("**", text)
        self.assertIn("제목", text)
        self.assertIn("굵게", text)

    # --- HTML → TXT ---

    def test_html_to_txt_excludes_title_tag(self):
        src = self.tmp / "f.html"
        src.write_text(
            "<html><head><title>페이지 제목</title></head>"
            "<body><p>본문 문단</p></body></html>",
            encoding="utf-8",
        )
        out = converters.convert(src, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("페이지 제목", text)
        self.assertIn("본문 문단", text)

    def test_html_to_txt_inline_tags_do_not_break_flow(self):
        src = self.tmp / "g.html"
        src.write_text(
            "<html><body><p>두 번째 문단, <b>굵게</b> 포함.</p></body></html>",
            encoding="utf-8",
        )
        out = converters.convert(src, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertIn("두 번째 문단, 굵게 포함.", text)

    def test_html_to_txt_br_produces_linebreak(self):
        src = self.tmp / "h.html"
        src.write_text(
            "<html><body><p>첫 줄<br>둘째 줄</p></body></html>", encoding="utf-8"
        )
        out = converters.convert(src, "txt", self.tmp)
        text = out.read_text(encoding="utf-8")
        self.assertIn("첫 줄\n둘째 줄", text)

    # --- HTML → MD ---

    def test_html_to_md_excludes_title_tag(self):
        src = self.tmp / "i.html"
        src.write_text(
            "<html><head><title>페이지 제목</title></head>"
            "<body><h1>본문 제목</h1><p>문단</p></body></html>",
            encoding="utf-8",
        )
        out = converters.convert(src, "md", self.tmp)
        md = out.read_text(encoding="utf-8")
        self.assertNotIn("페이지 제목", md)
        self.assertIn("# 본문 제목", md)

    def test_html_to_md_uses_atx_heading_style(self):
        src = self.tmp / "j.html"
        src.write_text(
            "<html><body><h1>대제목</h1><h3>소제목</h3></body></html>",
            encoding="utf-8",
        )
        out = converters.convert(src, "md", self.tmp)
        md = out.read_text(encoding="utf-8")
        self.assertIn("# 대제목", md)
        self.assertIn("### 소제목", md)

    # --- 인코딩 자동 감지 (REQ-F-009) ---

    def test_txt_to_html_reads_euc_kr_encoded_source(self):
        src = self.tmp / "k.txt"
        src.write_bytes("한글 인코딩 테스트".encode("cp949"))
        out = converters.convert(src, "html", self.tmp)
        html = out.read_text(encoding="utf-8")
        self.assertIn("한글 인코딩 테스트", html)

    # --- 빈 파일 ---

    def test_empty_txt_to_html(self):
        src = self.tmp / "empty.txt"
        src.write_text("", encoding="utf-8")
        out = converters.convert(src, "html", self.tmp)
        self.assertTrue(out.exists())

    def test_empty_html_to_md(self):
        src = self.tmp / "empty.html"
        src.write_text("<html><body></body></html>", encoding="utf-8")
        out = converters.convert(src, "md", self.tmp)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
