"""앱 버전 — packaging/VERSION이 유일한 정본(DEC-013). 여기서 그 파일을
읽기만 한다(값을 복제하지 않음 — 두 곳에 값을 두면 릴리스마다 하나를
깜빡 안 바꿔서 어긋날 위험이 있다).

개발 환경: app_root()가 저장소 루트라 packaging/VERSION을 바로 찾는다.
배포판(frozen): PyInstaller는 임의 파일을 자동으로 담지 않으므로, CI가
packaging/VERSION을 exe 옆(VERSION)에 복사해 둔다(build.yml).
"""
from .bundle import app_root


def current_version() -> str:
    for candidate in (app_root() / "VERSION", app_root() / "packaging" / "VERSION"):
        if candidate.exists():
            v = candidate.read_text(encoding="utf-8").strip()
            if v:
                return v
    return "0.0.0"
