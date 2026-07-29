"""최근 기록 — ENT-003 · REQ-F-010. 로컬 SQLite, 최대 50건 (OQ-004 잠정)."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

LIMIT = 50


@dataclass
class Entry:
    id: int
    source_name: str
    target_fmt: str
    output_path: str
    converted_at: str
    success: bool


def _db_path() -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    base.mkdir(parents=True, exist_ok=True)
    return base / "history.db"


class History:
    def __init__(self, path: Path | None = None):
        self._conn = sqlite3.connect(path or _db_path())
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, source_name TEXT, target_fmt TEXT,"
            "output_path TEXT, converted_at TEXT, success INTEGER)"
        )

    def add(self, source_name: str, target_fmt: str, output_path: str, success: bool):
        self._conn.execute(
            "INSERT INTO history (source_name, target_fmt, output_path, converted_at, success)"
            " VALUES (?,?,?,?,?)",
            (source_name, target_fmt, output_path,
             datetime.now().strftime("%Y-%m-%d %H:%M"), int(success)),
        )
        # 오래된 것부터 정리
        self._conn.execute(
            "DELETE FROM history WHERE id NOT IN "
            "(SELECT id FROM history ORDER BY id DESC LIMIT ?)", (LIMIT,))
        self._conn.commit()

    def list(self) -> list[Entry]:
        rows = self._conn.execute(
            "SELECT id, source_name, target_fmt, output_path, converted_at, success"
            " FROM history ORDER BY id DESC LIMIT ?", (LIMIT,)).fetchall()
        return [Entry(r[0], r[1], r[2], r[3], r[4], bool(r[5])) for r in rows]

    def delete(self, entry_id: int):
        self._conn.execute("DELETE FROM history WHERE id=?", (entry_id,))
        self._conn.commit()

    def clear(self):
        self._conn.execute("DELETE FROM history")
        self._conn.commit()
