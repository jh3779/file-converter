"""로컬 진단 로그 — 예상하지 못한 예외를 파일로 남긴다(정밀 구조 감사 후속).

`app/workers.py`의 포괄 `except Exception:`처럼 알려진 실패 종류
(ConversionError·OSError)로 분류되지 않는 예외는 지금까지 i18n 키만
UI에 전달되고 원인이 어디에도 안 남았다 — 사용자 문의만으로는 재현·
진단이 어려웠다. 파일 내용은 절대 기록하지 않는다(REQ-NF-002) — 예외
메시지·스택트레이스·파일 경로만. 저장 위치는 history.py와 같은 원칙
(QStandardPaths.AppDataLocation), 네트워크로 전송되지 않는다.
"""
import logging
import logging.handlers
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def _log_path() -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    base.mkdir(parents=True, exist_ok=True)
    return base / "app.log"


def setup():
    handler = logging.handlers.RotatingFileHandler(
        _log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
