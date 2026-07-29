"""HWP 변환 — hwplib(Apache-2.0) + JRE 사이드카 (DEC-007 · M-04).

사이드카: sidecar/hwp/HwpToText.java (hwplib TextExtractor 래퍼).
배포판은 JRE·클래스를 번들. 개발 환경 빌드는 sidecar/hwp/build.sh 참고.
파일 경로만 인자로 주고받는다 — 파일 내용의 소켓/네트워크 전송 없음(REQ-NF-002).
"""
import os
import shutil
import subprocess
from pathlib import Path

from .base import ConversionError

_REPO = Path(__file__).resolve().parents[2]


def _classpath() -> str | None:
    env = os.environ.get("FILECONV_HWP_CLASSPATH")
    if env:
        return env
    hwplib = _REPO / "spike" / "hwplib" / "libs" / "hwplib-main"
    sidecar = _REPO / "sidecar" / "hwp" / "out"
    if hwplib.exists() and sidecar.exists():
        return f"{sidecar}{os.pathsep}{hwplib}"
    return None


def hwp_to_txt(src: Path, tmpdir: Path) -> Path:
    java = os.environ.get("FILECONV_JAVA") or shutil.which("java")
    cp = _classpath()
    if java is None or cp is None:
        raise ConversionError("err.hwp_missing")
    out = tmpdir / (src.stem + ".txt")
    try:
        proc = subprocess.run(
            [java, "-cp", cp, "HwpToText", str(src), str(out)],
            capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not out.exists():
        stderr = proc.stderr.decode(errors="replace")
        key = "err.password" if "distribution" in stderr.lower() else "err.corrupted"
        raise ConversionError(key, stderr[:200])
    return out


def hwp_to_pdf(src: Path, tmpdir: Path) -> Path:
    raise ConversionError("err.notyet")   # v0.2: 구조 추출 → DOCX → LibreOffice (DEC-007)


def hwp_to_docx(src: Path, tmpdir: Path) -> Path:
    raise ConversionError("err.notyet")
