"""Vault Teal 디자인 토큰 — 정본: docs/design-system/styles.css (F-02·F-03).

하드코딩 HEX 금지: UI 코드는 반드시 이 dict를 경유한다 (M-01).
"""

LIGHT = {
    "primary": "#00696D", "onPrimary": "#FFFFFF",
    "primaryContainer": "#9CF1F6", "onPrimaryContainer": "#002021",
    "secondary": "#4A6365", "onSecondary": "#FFFFFF",
    "secondaryContainer": "#CCE8E9", "onSecondaryContainer": "#051F21",
    "tertiary": "#3B6939", "onTertiary": "#FFFFFF",
    "error": "#BA1A1A", "onError": "#FFFFFF",
    "errorContainer": "#FFDAD6", "onErrorContainer": "#410002",
    "surface": "#FAFDFC", "onSurface": "#191C1C",
    "surfaceVariant": "#DAE4E5", "onSurfaceVariant": "#3F4949",
    "outline": "#6F7979", "outlineVariant": "#BEC8C9",
    "surfaceContainerLowest": "#FFFFFF", "surfaceContainerLow": "#F4F7F7",
    "surfaceContainer": "#EEF1F1", "surfaceContainerHigh": "#E8EBEB",
    "stQueuedBg": "#DAE4E5", "stQueuedFg": "#3F4949",
    "stConvBg": "#9CF1F6", "stConvFg": "#002021",
    "stDoneBg": "#3B6939", "stDoneFg": "#FFFFFF",
    "stFailBg": "#FFDAD6", "stFailFg": "#410002",
    "stSkipBg": "#EEF1F1", "stSkipFg": "#6F7979",
}

DARK = {
    "primary": "#80D4D9", "onPrimary": "#003739",
    "primaryContainer": "#004F52", "onPrimaryContainer": "#9CF1F6",
    "secondary": "#B1CBCD", "onSecondary": "#1B3436",
    "secondaryContainer": "#324B4D", "onSecondaryContainer": "#CCE8E9",
    "tertiary": "#A1D399", "onTertiary": "#0A390F",
    "error": "#FFB4AB", "onError": "#690005",
    "errorContainer": "#93000A", "onErrorContainer": "#FFDAD6",
    "surface": "#101414", "onSurface": "#DEE3E3",
    "surfaceVariant": "#3F4949", "onSurfaceVariant": "#BEC8C9",
    "outline": "#899393", "outlineVariant": "#3F4949",
    "surfaceContainerLowest": "#0B0F0F", "surfaceContainerLow": "#181C1C",
    "surfaceContainer": "#1C2021", "surfaceContainerHigh": "#262B2B",
    "stQueuedBg": "#3F4949", "stQueuedFg": "#BEC8C9",
    "stConvBg": "#004F52", "stConvFg": "#9CF1F6",
    "stDoneBg": "#A1D399", "stDoneFg": "#0A390F",
    "stFailBg": "#93000A", "stFailFg": "#FFDAD6",
    "stSkipBg": "#1C2021", "stSkipFg": "#899393",
}


def build_qss(t: dict) -> str:
    """토큰 → 앱 전역 QSS. 버튼 변형은 property variant=filled|outlined|text|error."""
    return f"""
QMainWindow, QDialog {{ background: {t['surfaceContainerHigh']}; }}
QWidget {{ color: {t['onSurface']}; font-size: 13px; }}
QFrame#card {{ background: {t['surface']}; border: 1px solid {t['outlineVariant']}; border-radius: 12px; }}
QFrame#fileRow {{ background: {t['surfaceContainerLowest']}; border: 1px solid {t['outlineVariant']}; border-radius: 8px; }}
QFrame#fileRow[failed="true"] {{ border-color: {t['error']}; }}
QLabel#muted, QLabel#shield {{ color: {t['onSurfaceVariant']}; font-size: 11px; }}
QLabel#hint {{ color: {t['error']}; font-size: 11px; }}
QLabel#reason {{ color: {t['error']}; font-size: 11px; }}

QPushButton[variant="filled"] {{
  background: {t['primary']}; color: {t['onPrimary']}; border: 2px solid transparent;
  border-radius: 18px; height: 36px; padding: 0 22px; font-weight: 600; }}
QPushButton[variant="filled"]:disabled {{ background: {t['surfaceVariant']}; color: {t['onSurfaceVariant']}; }}
QPushButton[variant="outlined"] {{
  background: transparent; color: {t['primary']}; border: 1px solid {t['outline']};
  border-radius: 16px; height: 32px; padding: 0 18px; font-weight: 600; }}
QPushButton[variant="text"] {{
  background: transparent; color: {t['primary']}; border: none;
  border-radius: 16px; height: 32px; padding: 0 10px; font-weight: 600; }}
QPushButton[variant="error"] {{
  background: transparent; color: {t['error']}; border: 1px solid {t['error']};
  border-radius: 16px; height: 32px; padding: 0 18px; font-weight: 600; }}
QPushButton[variant="icon"] {{
  background: transparent; border: none; border-radius: 8px; padding: 4px 8px; font-size: 15px; }}
QPushButton[variant="icon"]:hover {{ background: {t['surfaceContainer']}; }}
QPushButton[variant="filled"]:focus {{ border-color: {t['onPrimaryContainer']}; }}
QPushButton[variant="outlined"]:focus, QPushButton[variant="text"]:focus {{ border: 2px solid {t['primary']}; }}
QPushButton[variant="error"]:focus {{ border: 2px solid {t['error']}; }}
QPushButton[variant="icon"]:focus {{ border: 1px solid {t['primary']}; }}

QFrame#footer {{ border-top: 1px solid {t['outlineVariant']}; }}
QFrame#footer QLabel, QFrame#footer QProgressBar {{ border: none; }}
QFrame#historyPanel {{ background: {t['surfaceContainerLow']}; border-left: 1px solid {t['outlineVariant']}; }}
QFrame#historyPanel QLabel {{ border: none; background: transparent; }}

QComboBox {{
  border: 1px solid {t['outline']}; border-radius: 8px; padding: 3px 8px;
  background: {t['surface']}; font-family: "Menlo","Consolas",monospace; font-size: 11px; }}
QComboBox QAbstractItemView {{ background: {t['surfaceContainerLow']}; border: 1px solid {t['outlineVariant']}; }}

QProgressBar {{ background: {t['surfaceVariant']}; border: none; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {t['primary']}; border-radius: 3px; }}

QListWidget {{ background: transparent; border: none; }}
QMenu {{ background: {t['surfaceContainerLow']}; border: 1px solid {t['outlineVariant']}; border-radius: 8px; }}
QMenu::item:selected {{ background: {t['secondaryContainer']}; color: {t['onSecondaryContainer']}; }}
"""
