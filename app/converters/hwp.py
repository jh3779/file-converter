"""HWP 변환 — hwplib(Apache-2.0) + JRE 사이드카 (DEC-007·DEC-017·DEC-028 · M-04).

사이드카: sidecar/hwp/HwpToText.java(평문) · HwpToJson.java(구조 — 문단+표+문자 서식) ·
JsonToHwp.java(구조 JSON → HWP 생성, HwpToJson의 역방향).
파이프라인: HWP→TXT 직접 / HWP→DOCX 구조 JSON→python-docx / HWP→PDF DOCX→LibreOffice /
DOCX→HWP python-docx→구조 JSON→JsonToHwp / PDF→HWP pdfminer 텍스트 추출→구조 JSON→JsonToHwp.
배포판은 JRE·클래스를 번들. 개발 환경 빌드는 sidecar/hwp/build.sh 참고.
파일 경로만 인자로 주고받는다 — 파일 내용의 소켓/네트워크 전송 없음(REQ-NF-002).

DEC-017 정정(DEC-028): "hwplib에는 표를 처음부터 새로 만드는 도구가
전혀 없다"는 이전 기록이 틀렸음이 확인됨 — hwplib 공식 샘플
`src/test/sample/Inserting_Table.java`가 정확히 그 방법을 보여준다(이전
조사에서 놓침). DOCX의 표는 이제 실제 HWP 표 컨트롤로 새로 생성된다
(spike/hwplib/SpikeTable.java에서 왕복 검증 후 sidecar/hwp/JsonToHwp.java에
일반화 — 셀 병합은 아직 미지원, 셀 텍스트는 평문 한 문단). 문단 텍스트
서식(굵게 등)은 이미 Phase 3(DEC-027)에서 HWP→DOCX 읽기 방향에 반영됨 —
DOCX→HWP 쓰기 방향의 문자 서식은 아직 범위 밖.

번호·불릿 목록(docx_extract.docx_to_blocks): DOCX의 자동 번호("1.")·불릿("•")은
문단의 실제 텍스트가 아니라 numbering.xml 서식으로 뷰어가 화면에만 그리는
것이라, 별도 처리 없이는 결과 HWP에서 조용히 사라진다(코드 리뷰 지적,
재현 확인 후 보완) — numbering.xml을 해석해 마커를 문단 앞에 텍스트로
붙인다. 다단계 중첩 목록의 상위 레벨 변경 시 하위 레벨 재시작 등 OOXML
번호 매기기 전체 규칙까지는 재현하지 않는 문서화된 단순화다.

문단 정렬(DEC-040): DOCX→HWP는 python-docx의 paragraph.alignment(직접
지정된 값만, 스타일 상속은 범위 밖)를, PDF→HWP는 pdfminer 줄 위치(bbox)
기반 휴리스틱을 각각 JsonToHwp.java에 "align" 필드로 넘긴다. HWP→DOCX는
HwpToJson.java가 ParaShape의 정렬을 항상 읽어 docx_build.py가
paragraph.alignment에 반영한다. HWP 문서 기본 정렬은 "양쪽 정렬"이라(hwplib
실측 확인), align이 없으면 그 기본값을 그대로 따른다.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..bundle import engine_dir
from .base import ConversionError
from .docx_build import blocks_to_docx

_REPO = Path(__file__).resolve().parents[2]


def _java() -> str | None:
    env = os.environ.get("FILECONV_JAVA")
    if env and Path(env).exists():
        return env
    bundled = engine_dir() / "jre" / "bin" / ("java.exe" if sys.platform == "win32" else "java")
    if bundled.exists():
        return str(bundled)
    return shutil.which("java")


def _classpath() -> str | None:
    env = os.environ.get("FILECONV_HWP_CLASSPATH")
    if env:
        return env
    bundled = engine_dir() / "hwp"          # 배포판: hwplib+사이드카 클래스 단일 폴더
    if bundled.exists():
        return str(bundled)
    hwplib = _REPO / "spike" / "hwplib" / "libs" / "hwplib-main"
    sidecar = _REPO / "sidecar" / "hwp" / "out"
    if hwplib.exists() and sidecar.exists():
        return f"{sidecar}{os.pathsep}{hwplib}"
    return None


def _run_sidecar(main_class: str, src: Path, out: Path):
    java = _java()
    cp = _classpath()
    if java is None or cp is None:
        raise ConversionError("err.hwp_missing")
    # JVM의 네이티브 argv 디코딩(sun.jnu.encoding)은 OS 로캘의 기본 코드페이지를
    # 따른다. 영어 로캘 Windows(코드페이지 1252)에서 한글이 포함된 경로를 그대로
    # 넘기면 표현 불가 문자가 '?'로 뭉개져 JVM이 다른 파일을 찾게 된다 — 실제
    # CI(en-US 러너)에서 "표.hwp" 입력으로 재현됨. ASCII 별칭 경로로 완전히 우회한다.
    safe_src = out.parent / f"_hwp_in{src.suffix}"
    safe_out = out.parent / f"_hwp_out{out.suffix}"
    shutil.copy(src, safe_src)
    try:
        proc = subprocess.run(
            [java, "-cp", cp, main_class, str(safe_src), str(safe_out)],
            capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not safe_out.exists():
        stderr = proc.stderr.decode(errors="replace")
        key = "err.password" if "distribution" in stderr.lower() else "err.corrupted"
        raise ConversionError(key, stderr[:200])
    # out으로의 이동은 순수 Python/OS 파일 API(Windows에서도 wide-char 경로 지원)라
    # 한글 경로에 안전하다 — 문제는 오직 JVM argv 디코딩 구간에만 있었다.
    shutil.move(str(safe_out), out)


def hwp_to_txt(src: Path, tmpdir: Path) -> Path:
    out = tmpdir / (src.stem + ".txt")
    _run_sidecar("HwpToText", src, out)
    return out


def hwp_to_docx(src: Path, tmpdir: Path) -> Path:
    """HWP → 구조 JSON → DOCX (문단 + 표 내용 보존, 서식 단순화 — DEC-010 고지)."""
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    _run_sidecar("HwpToJson", src, blocks_json)
    try:
        blocks = json.loads(blocks_json.read_text(encoding="utf-8"))["blocks"]
    except (json.JSONDecodeError, KeyError) as e:
        raise ConversionError("err.corrupted", str(e))
    return blocks_to_docx(blocks, tmpdir / (src.stem + ".docx"))


def hwp_to_pdf(src: Path, tmpdir: Path) -> Path:
    """HWP → DOCX → LibreOffice → PDF (DEC-007 파이프라인)."""
    from . import office
    intermediate = hwp_to_docx(src, tmpdir)
    return office.office_to_pdf(intermediate, tmpdir)


def docx_to_hwp(src: Path, tmpdir: Path) -> Path:
    """DOCX → 구조 JSON → HWP (문단 텍스트 보존, 표는 실제 HWP 표로 새로 생성 —
    DEC-017 정정, DEC-028. 셀 병합·서식은 아직 범위 밖)."""
    from .docx_extract import docx_to_blocks

    blocks = docx_to_blocks(src)
    return _blocks_to_hwp(blocks, src, tmpdir)


def pdf_to_hwp(src: Path, tmpdir: Path) -> Path:
    """PDF → 텍스트 추출 → HWP (레이아웃 단순화 — PDF→DOCX의 DEC-010과 같은 원칙).
    PDF는 표 구조 자체를 담고 있지 않으므로(추출 결과가 이미 평문) 문단
    텍스트만 옮긴다. 정렬(DEC-040)은 문단 줄 위치(bbox)로 추정해 반영한다
    (이전엔 pdfminer의 extract_text()로 문서 전체를 한 문자열로 뽑아 페이지·
    줄 위치 정보 자체가 없었음)."""
    from . import pdf as pdf_mod

    blocks = pdf_mod._extract_pdf_paragraphs(src)
    return _blocks_to_hwp(blocks, src, tmpdir)


def _blocks_to_hwp(blocks: list[dict], src: Path, tmpdir: Path) -> Path:
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    blocks_json.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    out = tmpdir / (src.stem + ".hwp")
    _run_sidecar("JsonToHwp", blocks_json, out)
    return out
