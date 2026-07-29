"""UI 문자열 — 한국어·영어만 (DEC-009 · REQ-F-011).

모든 사용자 노출 문자열은 이 모듈의 키를 경유한다. 하드코딩 금지.
오류 문안은 docs/design-system/patterns.html P-04 표가 정본.
"""
from PySide6.QtCore import QLocale, QSettings

LANGS = ("ko", "en")

_S = {
    "app.title": ("파일 변환기", "File Converter"),
    "drop.title": ("파일을 여기에 끌어다 놓으세요", "Drop files here"),
    "drop.sub": ("또는 클릭해서 선택 · DOCX PDF HWP CSV XLSX JSON",
                 "or click to browse · DOCX PDF HWP CSV XLSX JSON"),
    "drop.strip": ("＋ 파일 추가 또는 끌어다 놓기", "＋ Add files or drag & drop"),
    "convert": ("변환하기", "Convert"),
    "cancel": ("취소", "Cancel"),
    "ok": ("확인", "OK"),
    "footer.save": ("저장: 원본 폴더 · 원본은 그대로 둡니다",
                    "Saved next to originals · originals are never modified"),
    "footer.offline": ("모든 변환은 이 컴퓨터 안에서 처리됩니다",
                       "All conversions happen on this computer"),
    "hint.pickformat": ("포맷을 선택해 주세요", "Choose a format for every file"),
    "unsupported": ("지원하지 않는 형식입니다", "Unsupported format"),
    "pick.placeholder": ("선택", "Select"),
    "converting": ("변환 중…", "Converting…"),
    "progress.n": ("{done} / {total} 완료", "{done} / {total} done"),

    "st.queued": ("대기 중", "Queued"),
    "st.converting": ("변환 중", "Converting"),
    "st.done": ("완료", "Done"),
    "st.failed": ("실패", "Failed"),
    "st.skipped": ("건너뜀", "Skipped"),

    "result.allsuccess": ("변환 완료", "Conversion complete"),
    "result.partial": ("일부 파일을 변환하지 못했습니다", "Some files could not be converted"),
    "result.allfail": ("변환하지 못했습니다", "Conversion failed"),
    "result.counts": ("성공 {ok} · 실패 {fail}", "Succeeded {ok} · Failed {fail}"),
    "result.saved_n": ("{n}개 파일을 원본 폴더에 저장했습니다",
                       "Saved {n} file(s) next to the originals"),
    "result.renamed": ("이름이 겹쳐 {name}(으)로 저장했습니다",
                       "Saved as {name} to avoid a name clash"),
    "result.openfolder": ("결과 폴더 열기", "Open folder"),

    "history.title": ("최근 기록", "Recent history"),
    "history.local": ("기록은 이 컴퓨터에만 저장됩니다", "History is stored only on this computer"),
    "history.empty": ("아직 변환 기록이 없습니다", "No conversions yet"),
    "history.clear": ("모두 삭제", "Clear all"),
    "history.notfound": ("파일을 찾을 수 없습니다", "File not found"),
    "history.failed": ("실패", "failed"),

    "dlg.clear.title": ("기록을 모두 삭제할까요?", "Clear all history?"),
    "dlg.clear.body": ("변환 기록만 지워집니다. 변환된 파일은 그대로 남습니다. 이 동작은 되돌릴 수 없습니다.",
                       "Only the history entries are removed. Converted files stay untouched. This cannot be undone."),
    "dlg.clear.confirm": ("삭제", "Clear"),
    "dlg.quit.title": ("변환이 진행 중입니다", "Conversion in progress"),
    "dlg.quit.body": ("지금 종료하면 완료된 파일은 남고, 변환 중이던 파일은 취소됩니다.",
                      "If you quit now, finished files are kept and in-progress files are cancelled."),
    "dlg.quit.stay": ("계속 변환", "Keep converting"),
    "dlg.quit.quit": ("종료", "Quit"),

    "lang.menu": ("언어", "Language"),
    "lang.system": ("시스템 설정 따름", "Follow system"),
    "lang.ko": ("한국어", "한국어"),
    "lang.en": ("English", "English"),

    # 오류 문안 — P-04 (원인 1문장 + 복구 1문장)
    "err.password": ("암호가 걸린 파일입니다. 암호를 해제한 뒤 다시 시도해 주세요.",
                     "This file is password-protected. Remove the password and try again."),
    "err.corrupted": ("파일을 읽을 수 없습니다. 파일이 손상되었을 수 있어요.",
                      "The file could not be read. It may be damaged."),
    "err.encoding": ("한글이 깨질 수 있어 변환을 멈췄습니다. 파일 인코딩을 확인해 주세요.",
                     "Stopped to avoid corrupting text. Please check the file encoding."),
    "err.disk": ("저장 공간이 부족하거나 폴더에 쓸 수 없습니다. 공간·권한을 확인해 주세요.",
                 "Not enough space or no permission to write. Check disk space and folder permissions."),
    "err.engine": ("이 파일은 변환하지 못했습니다. 다시 시도해 주세요.",
                   "This file could not be converted. Please try again."),
    "err.engine_missing": ("문서 변환 엔진을 찾을 수 없습니다. 앱을 다시 설치해 주세요.",
                           "The document engine is missing. Please reinstall the app."),
    "err.hwp_missing": ("HWP 변환 구성 요소를 찾을 수 없습니다. 앱을 다시 설치해 주세요.",
                        "The HWP component is missing. Please reinstall the app."),
    "err.jsonshape": ("이 JSON은 표로 바꿀 수 없는 구조입니다. 목록 형태의 JSON만 지원해요.",
                      "This JSON has no tabular shape. Only list-style JSON is supported."),
    "err.cancelled": ("취소되었습니다", "Cancelled"),
    "note.simplified": ("레이아웃이 단순화될 수 있어요 — 텍스트·표 내용은 유지됩니다",
                        "Layout may be simplified — text and table contents are kept"),
    "err.notyet": ("이 변환은 다음 버전에서 지원될 예정입니다.",
                   "This conversion is coming in a future update."),
}

_settings = None
_lang = None


def _store() -> QSettings:
    global _settings
    if _settings is None:
        _settings = QSettings("file-converter", "app")
    return _settings


def system_lang() -> str:
    return "ko" if QLocale.system().name().startswith("ko") else "en"


def current_lang() -> str:
    global _lang
    if _lang is None:
        saved = _store().value("language", "")
        _lang = saved if saved in LANGS else system_lang()
    return _lang


def set_lang(lang: str | None) -> None:
    """lang=None 이면 시스템 따름."""
    global _lang
    _store().setValue("language", lang or "")
    _lang = lang if lang in LANGS else system_lang()


def saved_pref() -> str:
    """저장된 원시 설정값: '' | 'ko' | 'en'."""
    v = _store().value("language", "")
    return v if v in LANGS else ""


def tr(key: str, **kw) -> str:
    ko, en = _S[key]
    s = ko if current_lang() == "ko" else en
    return s.format(**kw) if kw else s
