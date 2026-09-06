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
    source_fmt: str                 # 소문자 확장자 (점 없음) 또는 내부 canonical type
    target_fmt: str | None = None
    state: ItemState = ItemState.QUEUED
    output: Path | None = None      # done일 때만 확정 (INV-02)
    error_key: str | None = None    # i18n 키 (P-04)
    renamed: bool = field(default=False)  # 자동 리네임 발생 여부 (INV-05 사후 보고)

    def __post_init__(self):
        """알 수 없는 확장자는 콘텐츠 기반 감지로 한 번 보정한다.

        import를 런타임으로 늦춰 converters → UI/models 의존 관계에 순환 import를
        만들지 않는다. 감지에 실패하면 사용자가 넘긴 source_fmt을 그대로 유지해
        기존 unsupported 표시가 유지된다.
        """
        from . import converters

        if not converters.supported(self.source_fmt):
            detected = converters.detect_source_format(self.source)
            if converters.supported(detected):
                self.source_fmt = detected

    @property
    def name(self) -> str:
        return self.source.name
