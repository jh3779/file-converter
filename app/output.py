"""출력 경로 규칙 — INV-01·02·05: 임시 폴더에 변환 후 원자적 이동, 덮어쓰기 경로 없음."""
import shutil
import tempfile
import threading
from pathlib import Path

# finalize()는 QThreadPool의 여러 워커 스레드에서 동시에 호출된다(workers.py,
# 최대 4개 동시). "이름이 비어있는지 확인 → 그 이름으로 이동"이 원자적이지
# 않으면(TOCTOU), 같은 stem+ext로 끝나는 두 파일이 동시에 완료될 때 둘 다
# 같은 "충돌 없음" 경로를 계산해버려 한쪽이 다른 쪽 결과물을 조용히
# 덮어쓸 수 있다 — 실제 두 스레드 동시 호출로 재현·확인함(REQ-F-008/INV-01
# "덮어쓰기 경로 없음" 위반). 이름 예약과 이동을 하나의 임계 구역으로 묶는다.
_finalize_lock = threading.Lock()


def unique_output_path(directory: Path, stem: str, ext: str) -> Path:
    """원본 폴더 안에서 충돌하지 않는 경로. 충돌 시 '이름 (1).ext' 자동 리네임 (REQ-F-008).
    호출자가 동시성 보장이 필요하면 _finalize_lock 등으로 감싸야 한다 — 이 함수
    자체는 파일 존재 확인만 하고 예약(생성)하지 않는다."""
    candidate = directory / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}).{ext}"
        n += 1
    return candidate


def finalize(tmp_file: Path, source: Path, ext: str) -> tuple[Path, bool]:
    """임시 산출물을 원본 폴더로 이동. (최종 경로, 리네임 발생 여부) 반환."""
    with _finalize_lock:
        out = unique_output_path(source.parent, source.stem, ext)
        renamed = out.name != f"{source.stem}.{ext}"
        shutil.move(str(tmp_file), out)
    return out, renamed


def make_tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="fileconv-"))
