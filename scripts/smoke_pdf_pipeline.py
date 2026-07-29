"""LibreOffice 번들 스모크 — 실제 앱 코드 경로로 DOCX→PDF, HWP→PDF 전체 파이프라인 검증.

CI(Windows)에서 사용. 엔진 위치는 FILECONV_SOFFICE / FILECONV_JAVA /
FILECONV_HWP_CLASSPATH 환경변수로 지정한다(사전 빌드 경로·패키징 후 경로 양쪽 재사용 가능).
실패 시 non-zero로 종료 — 이 스크립트를 호출하는 쪽에서 exit code를 반드시 확인할 것.

사용:
  python scripts/smoke_pdf_pipeline.py <hwp_sample_path> [--skip-hwp]
"""
import shutil
import sys
import tempfile
from pathlib import Path

# Windows CI 콘솔 기본 인코딩(cp1252)은 화살표(→)·한글을 출력하지 못해
# print()가 UnicodeEncodeError로 죽는다 — 실제 변환 결과와 무관한 순수 출력 버그이므로
# 가장 먼저 UTF-8로 강제 재구성한다.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import converters  # noqa: E402
from app.converters.base import ConversionError  # noqa: E402


def check(label: str, cond: bool, detail: str = ""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        sys.exit(1)


def main():
    hwp_sample = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    skip_hwp = "--skip-hwp" in sys.argv

    tmp = Path(tempfile.mkdtemp())
    try:
        # 1) DOCX -> PDF (번들 LibreOffice 실경로 검증 — DEC-002)
        from docx import Document
        src_docx = tmp / "smoke.docx"
        doc = Document()
        doc.add_paragraph("LibreOffice 번들 스모크 테스트 — 한글 포함 확인")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "항목"
        table.cell(0, 1).text = "값"
        table.cell(1, 0).text = "결과"
        table.cell(1, 1).text = "성공"
        doc.save(src_docx)

        try:
            out = converters.convert(src_docx, "pdf", tmp)
            check("DOCX→PDF 변환", out.exists() and out.stat().st_size > 500,
                  f"{out} ({out.stat().st_size if out.exists() else 0} bytes)")
        except ConversionError as e:
            check("DOCX→PDF 변환", False, f"{e.key}: {e.detail}")

        # 2) HWP -> PDF (DEC-007 파이프라인: hwplib 구조 추출 → DOCX → LibreOffice)
        if not skip_hwp:
            check("HWP 샘플 존재", hwp_sample is not None and hwp_sample.exists(),
                  str(hwp_sample))
            try:
                out = converters.convert(hwp_sample, "pdf", tmp)
                check("HWP→PDF 변환(전체 파이프라인)",
                      out.exists() and out.stat().st_size > 500,
                      f"{out} ({out.stat().st_size if out.exists() else 0} bytes)")
            except ConversionError as e:
                check("HWP→PDF 변환(전체 파이프라인)", False, f"{e.key}: {e.detail}")

        print("스모크 전체 통과")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
