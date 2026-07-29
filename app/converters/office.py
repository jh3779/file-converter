"""문서 변환 — DOCX→PDF, 번들 LibreOffice headless (DEC-002 · M-04).

배포판은 엔진을 앱에 번들한다(REQ-NF-005). 개발 환경에서는 시스템 설치본 또는
FILECONV_SOFFICE 환경변수로 위치를 지정한다.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .base import ConversionError

_MAC_DEFAULT = "/Applications/LibreOffice.app/Contents/MacOS/soffice"


def find_soffice() -> str | None:
    env = os.environ.get("FILECONV_SOFFICE")
    if env and Path(env).exists():
        return env
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "engine" / "soffice"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("soffice")
    if found:
        return found
    if Path(_MAC_DEFAULT).exists():
        return _MAC_DEFAULT
    return None


def docx_to_pdf(src: Path, tmpdir: Path) -> Path:
    soffice = find_soffice()
    if soffice is None:
        raise ConversionError("err.engine_missing")
    profile = tmpdir / "lo-profile"
    cmd = [
        soffice, "--headless", "--norestore",
        f"-env:UserInstallation=file://{profile}",
        "--convert-to", "pdf", "--outdir", str(tmpdir), str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    out = tmpdir / (src.stem + ".pdf")
    if proc.returncode != 0 or not out.exists():
        raise ConversionError("err.engine", proc.stderr.decode(errors="replace")[:200])
    return out
