"""LibreOffice 번들 스모크 — 실제 앱 코드 경로로 DOCX→PDF, HWP→PDF 전체 파이프라인 검증.

CI(Windows)에서 사용. 기본은 FILECONV_SOFFICE / FILECONV_JAVA / FILECONV_HWP_CLASSPATH
환경변수로 엔진 위치를 지정(사전 빌드 경로 검증용 — dist가 아직 없는 시점).

--frozen-exe <exe경로>를 주면 환경변수를 전혀 쓰지 않고, sys.frozen/sys.executable을
그 경로로 흉내내어 app.bundle.engine_dir()의 실제 프로덕션 자동 탐색 로직
(exe 옆 engine/ 폴더)이 진짜로 동작하는지 검증한다 — 이것이 실사용자가
FileConverter.exe를 실행했을 때 실제로 타는 경로다.

PDF 결과는 파일 크기뿐 아니라 %PDF- 매직바이트 + pdfminer 텍스트 추출로
한글 내용까지 확인한다(빈 PDF·깨진 PDF를 파일 크기만으로 오검출하지 않도록).

실패 시 non-zero로 종료 — 이 스크립트를 호출하는 쪽에서 exit code를 반드시 확인할 것.

사용:
  python scripts/smoke_pdf_pipeline.py <hwp_sample_path> [--skip-hwp] [--frozen-exe <exe경로>]
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
from app.converters import office as office_mod  # noqa: E402
from app.converters import hwp as hwp_mod  # noqa: E402


def check(label: str, cond: bool, detail: str = ""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        sys.exit(1)


def verify_pdf_content(path: Path, must_contain: str) -> None:
    check(f"{path.name}: %PDF- 매직바이트", path.read_bytes()[:5] == b"%PDF-")
    from pdfminer.high_level import extract_text
    text = extract_text(str(path))
    check(f"{path.name}: 텍스트 내용('{must_contain}') 포함",
          must_contain in text, repr(text[:120]))


def simulate_frozen(exe_path: str):
    """실제 사용자가 FileConverter.exe를 실행했을 때와 동일하게
    sys.frozen/sys.executable을 흉내내, engine_dir() 자동 탐색을 진짜로 태운다."""
    resolved = Path(exe_path).resolve()
    sys.frozen = True
    sys.executable = str(resolved)
    print(f"[INFO] 프로즌 모드 시뮬레이션: sys.executable={sys.executable}")

    engine = resolved.parent / "engine"
    soffice = office_mod.find_soffice()
    check("자동 탐색: soffice (env 미사용)", soffice is not None and str(engine) in soffice, soffice)
    java = hwp_mod._java()
    check("자동 탐색: java (env 미사용)", java is not None and str(engine) in java, java)
    cp = hwp_mod._classpath()
    check("자동 탐색: hwp classpath (env 미사용)", cp is not None and str(engine) in cp, cp)


def main():
    argv = sys.argv[1:]
    skip_hwp = "--skip-hwp" in argv
    frozen_exe = None
    if "--frozen-exe" in argv:
        frozen_exe = argv[argv.index("--frozen-exe") + 1]
    positional = [a for a in argv if not a.startswith("--") and a != frozen_exe]
    hwp_sample = Path(positional[0]) if positional else None

    if frozen_exe:
        simulate_frozen(frozen_exe)

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
            check("DOCX→PDF 변환 완료", out.exists())
            verify_pdf_content(out, "번들 스모크 테스트")
        except ConversionError as e:
            check("DOCX→PDF 변환 완료", False, f"{e.key}: {e.detail}")
        except Exception as e:
            check("DOCX→PDF 변환 완료", False, f"예상 밖 예외 {type(e).__name__}: {e}")

        # 2) HWP -> PDF (DEC-007 파이프라인: hwplib 구조 추출 → DOCX → LibreOffice)
        if not skip_hwp:
            check("HWP 샘플 존재", hwp_sample is not None and hwp_sample.exists(),
                  str(hwp_sample))
            try:
                out = converters.convert(hwp_sample, "pdf", tmp)
                check("HWP→PDF 변환 완료(전체 파이프라인)", out.exists())
                verify_pdf_content(out, "ABC")  # 표.hwp 알려진 내용 (spike/hwplib/RESULT.md)
            except ConversionError as e:
                check("HWP→PDF 변환 완료(전체 파이프라인)", False, f"{e.key}: {e.detail}")
            except Exception as e:
                check("HWP→PDF 변환 완료(전체 파이프라인)", False,
                      f"예상 밖 예외 {type(e).__name__}: {e}")

        print("스모크 전체 통과")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
