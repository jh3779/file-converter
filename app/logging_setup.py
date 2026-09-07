"""로컬 진단 로그 — 예상하지 못한 예외를 파일로 남긴다(정밀 구조 감사 후속).

`app/workers.py`의 포괄 `except Exception:`처럼 알려진 실패 종류
(ConversionError·OSError)로 분류되지 않는 예외는 지금까지 i18n 키만
UI에 전달되고 원인이 어디에도 안 남았다 — 사용자 문의만으로는 재현·
진단이 어려웠다. 파일 내용은 절대 기록하지 않는다(REQ-NF-002) — 예외
메시지·스택트레이스·파일 경로만. 저장 위치는 history.py와 같은 원칙
(appdata.py 경유), 네트워크로 전송되지 않는다.
"""
import logging
import logging.handlers
from pathlib import Path

from . import appdata


def _log_path() -> Path | None:
    base = appdata.resolve()
    return base / "app.log" if base else None


def setup():
    """진단 로그 파일 핸들러를 등록한다. 이 기능 자체는 부가적인 진단
    수단일 뿐이라, 초기화가 실패하거나(예: AppData 쓰기 권한 없음) 제
    시간 안에 끝나지 않아도(예: AppData가 응답 없는 네트워크 경로로
    리다이렉트됨 — appdata.py 참고, 실사용 보고로 확인) 그것 때문에 앱
    실행 자체가 막혀서는 안 된다 — 실패하면 조용히 포기하고 로깅 없이
    계속 진행한다."""
    try:
        path = _log_path()
        if path is None:
            return
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=2, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except OSError:
        pass
