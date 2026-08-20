"""공유 QSettings 저장소 — 앱 전역 설정(언어·업데이트 체크 옵트인 등)이 이 모듈
하나를 거쳐 저장된다. i18n.py·update_check.py가 각자 QSettings("file-converter",
"app")를 독립적으로 열지 않도록 접근점을 하나로 모은다(구조 감사 후속 조치).
"""
from PySide6.QtCore import QSettings

_settings = None


def store() -> QSettings:
    global _settings
    if _settings is None:
        _settings = QSettings("file-converter", "app")
    return _settings
