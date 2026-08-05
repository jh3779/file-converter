"""문서 변환 — DOCX/PPTX→PDF, 번들 LibreOffice headless (DEC-002·DEC-016 · M-04).

배포판은 엔진을 앱에 번들한다(REQ-NF-005). 개발 환경에서는 시스템 설치본 또는
FILECONV_SOFFICE 환경변수로 위치를 지정한다. LibreOffice의 --convert-to는
입력 포맷을 자동 감지하므로 DOCX·PPTX 모두 동일 경로로 처리한다.
"""
import os
import shutil
import subprocess
from pathlib import Path

from ..bundle import engine_dir
from .base import ConversionError

_DEFAULTS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",             # macOS
    r"C:\Program Files\LibreOffice\program\soffice.exe",                 # Windows
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def find_soffice() -> str | None:
    env = os.environ.get("FILECONV_SOFFICE")
    if env and Path(env).exists():
        return env
    for bundled in (engine_dir() / "libreoffice" / "program" / "soffice.exe",  # Windows (v0.3b)
                    engine_dir() / "libreoffice" / "program" / "soffice",
                    engine_dir() / "libreoffice" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"):  # macOS
        if bundled.exists():
            return str(bundled)
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in _DEFAULTS:
        if Path(candidate).exists():
            return candidate
    return None


def office_to_pdf(src: Path, tmpdir: Path) -> Path:
    soffice = find_soffice()
    if soffice is None:
        raise ConversionError("err.engine_missing")
    profile = tmpdir / "lo-profile"
    cmd = [
        soffice, "--headless", "--norestore",
        # Path.as_uri()로 생성 — Windows에서 f"file://{profile}"은 역슬래시가
        # 섞인 잘못된 URI가 되어 프로필 격리가 깨지고, 동시 변환 시 서로 다른
        # soffice 프로세스가 같은 기본 프로필을 두고 충돌할 수 있다.
        f"-env:UserInstallation={profile.as_uri()}",
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
