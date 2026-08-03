"""업데이트 확인 — 선택 기능, 기본 꺼짐 (OQ-002 해소, DEC-022).

"완전 오프라인·네트워크 요청 0건"(REQ-NF-002)과 정면으로 부딪히는 기능이라
오래 미결로 남아 있었다. 사용자가 설정에서 직접 켜야만 동작하고(옵트인,
기본 꺼짐), 켜져 있어도 GitHub Releases API에 **버전 번호만** 물어본다 —
파일 내용·경로·사용자 식별 정보는 절대 전송하지 않는다. 자동 다운로드·설치는
하지 않고, 새 버전이 있으면 조용한 안내만 띄운다(클릭하면 릴리스 페이지를
브라우저로 연다). 오프라인이거나 요청이 실패하면 조용히 무시 — 사용자에게
오류로 보이지 않아야 한다(선택 기능이 필수 기능의 오류처럼 보이면 안 됨).
"""
import json
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, QSettings, Signal

from .version import current_version

REPO = "jh3779/file-converter"
_API_URL = f"https://api.github.com/repos/{REPO}/releases"
_TIMEOUT = 5

_settings = None


def _store() -> QSettings:
    global _settings
    if _settings is None:
        _settings = QSettings("file-converter", "app")
    return _settings


def is_enabled() -> bool:
    return _store().value("update_check_enabled", False, type=bool)


def set_enabled(value: bool) -> None:
    _store().setValue("update_check_enabled", bool(value))


def _parse(v: str) -> tuple:
    """"v0.3.10" 같은 태그를 (0,3,10)으로. 숫자가 아닌 조각은 0 취급 —
    완벽한 semver 파서가 아니라 이 프로젝트의 vX.Y.Z 태그 규칙 전용."""
    parts = v.strip().lstrip("vV").split(".")
    out = []
    for p in parts:
        digits = "".join(ch for ch in p if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def fetch_latest_version() -> str | None:
    """실패(오프라인·API 오류 등)하면 None — 절대 예외를 밖으로 던지지 않는다."""
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "file-converter-update-check"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if not releases or not isinstance(releases, list):
        return None
    tag = releases[0].get("tag_name") if isinstance(releases[0], dict) else None
    return tag.lstrip("vV") if tag else None


class UpdateChecker(QObject):
    """백그라운드 스레드에서 확인 후 결과를 시그널로 UI 스레드에 전달한다
    (workers.py의 JobSignals와 같은 패턴 — 워커 스레드가 emit해도 Qt가
    연결된 슬롯을 수신 객체의 스레드로 안전하게 큐잉한다)."""
    found = Signal(str)  # 새 버전이 있으면 버전 문자열, 없거나 실패하면 ""

    def check(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        latest = fetch_latest_version()
        if latest and _parse(latest) > _parse(current_version()):
            self.found.emit(latest)
        else:
            self.found.emit("")
