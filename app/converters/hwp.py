"""HWP 변환 — hwplib(Apache-2.0) + JRE 사이드카 (DEC-007·DEC-017 · M-04).

사이드카: sidecar/hwp/HwpToText.java(평문) · HwpToJson.java(구조 — 문단+표) ·
JsonToHwp.java(구조 JSON → HWP 생성, HwpToJson의 역방향).
파이프라인: HWP→TXT 직접 / HWP→DOCX 구조 JSON→python-docx / HWP→PDF DOCX→LibreOffice /
DOCX→HWP python-docx→구조 JSON→JsonToHwp.
배포판은 JRE·클래스를 번들. 개발 환경 빌드는 sidecar/hwp/build.sh 참고.
파일 경로만 인자로 주고받는다 — 파일 내용의 소켓/네트워크 전송 없음(REQ-NF-002).

DEC-017: DOCX→HWP는 문단 텍스트만 지원한다. hwplib에는 표를 처음부터 새로
만드는 도구가 없어(기존 표를 읽어 그대로 다시 저장하는 라운드트립만
검증됨 — spike/hwplib/RESULT.md), 낮은 신뢰도로 표 컨트롤을 직접 조립하는
대신 DOCX의 표는 각 행을 " | "로 이어붙인 한 줄 텍스트 문단으로 안전하게
표현한다. 내용은 보존되고 표 구조만 단순화된다(PDF→DOCX의 DEC-010과 같은
원칙: 검증되지 않은 시도보다 검증된 단순화를 택함).
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
    """DOCX → 구조 JSON → HWP (문단 텍스트 보존, 표는 텍스트로 단순화 — DEC-017)."""
    from .docx_extract import docx_to_blocks

    blocks = docx_to_blocks(src)
    blocks_json = tmpdir / (src.stem + ".blocks.json")
    blocks_json.write_text(json.dumps({"blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    out = tmpdir / (src.stem + ".hwp")
    _run_sidecar("JsonToHwp", blocks_json, out)
    return out
