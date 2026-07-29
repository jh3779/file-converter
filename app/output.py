"""출력 경로 규칙 — INV-01·02·05: 임시 폴더에 변환 후 원자적 이동, 덮어쓰기 경로 없음."""
import shutil
import tempfile
from pathlib import Path


def unique_output_path(directory: Path, stem: str, ext: str) -> Path:
    """원본 폴더 안에서 충돌하지 않는 경로. 충돌 시 '이름 (1).ext' 자동 리네임 (REQ-F-008)."""
    candidate = directory / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}).{ext}"
        n += 1
    return candidate


def finalize(tmp_file: Path, source: Path, ext: str) -> tuple[Path, bool]:
    """임시 산출물을 원본 폴더로 이동. (최종 경로, 리네임 발생 여부) 반환."""
    out = unique_output_path(source.parent, source.stem, ext)
    renamed = out.name != f"{source.stem}.{ext}"
    shutil.move(str(tmp_file), out)
    return out, renamed


def make_tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="fileconv-"))
