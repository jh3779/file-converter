"""FileItem 모델·상태 — 정본: docs/04_data_model.md ENT-002 · docs/05_state_machine.md STATE-002."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ItemState(Enum):
    QUEUED = "queued"
    CONVERTING = "converting"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileItem:
    id: int
    source: Path
    source_fmt: str                 # 소문자 확장자 (점 없음)
    target_fmt: str | None = None
    state: ItemState = ItemState.QUEUED
    output: Path | None = None      # done일 때만 확정 (INV-02)
    error_key: str | None = None    # i18n 키 (P-04)
    renamed: bool = field(default=False)  # 자동 리네임 발생 여부 (INV-05 사후 보고)

    @property
    def name(self) -> str:
        return self.source.name
