"""HWP 변환 — hwplib(Apache-2.0) + JRE 사이드카 (DEC-007 · M-04).

사이드카: sidecar/hwp/HwpToText.java(평문) · HwpToJson.java(구조 — 문단+표).
파이프라인: HWP→TXT 직접 / HWP→DOCX 구조 JSON→python-docx / HWP→PDF DOCX→LibreOffice.
배포판은 JRE·클래스를 번들. 개발 환경 빌드는 sidecar/hwp/build.sh 참고.
파일 경로만 인자로 주고받는다 — 파일 내용의 소켓/네트워크 전송 없음(REQ-NF-002).
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
    try:
        proc = subprocess.run(
            [java, "-cp", cp, main_class, str(src), str(out)],
            capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not out.exists():
        stderr = proc.stderr.decode(errors="replace")
        key = "err.password" if "distribution" in stderr.lower() else "err.corrupted"
        raise ConversionError(key, stderr[:200])


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
    return office.docx_to_pdf(intermediate, tmpdir)
