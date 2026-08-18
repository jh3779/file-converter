from pathlib import Path


class ConversionError(Exception):
    """사용자에게 보여줄 실패 — i18n 키로 전달한다 (P-04 문안 규칙)."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key
        self.detail = detail


_TEXT_ENCODINGS = ("utf-8-sig", "cp949", "utf-8")


def read_text_auto_encoding(path: Path) -> str:
    """한글 인코딩 자동 감지 텍스트 읽기(REQ-F-009 Should) — UTF-8(BOM 유무)·
    CP949(EUC-KR 상위 호환) 순으로 시도. 원래 data.py(CSV) 전용이었는데
    markup.py(TXT/MD/HTML, DEC-061) 도입으로 두 번째 소비자가 생겨 공유
    모듈로 승격했다."""
    for enc in _TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError:
            raise ConversionError("err.corrupted")
    raise ConversionError("err.encoding")
