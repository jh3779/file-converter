class ConversionError(Exception):
    """사용자에게 보여줄 실패 — i18n 키로 전달한다 (P-04 문안 규칙)."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key = key
        self.detail = detail
