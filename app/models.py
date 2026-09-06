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
    source_fmt: str                 # 소문자 확장자(점 없음), 콘텐츠 감지 시 내부 routing key
    target_fmt: str | None = None
    state: ItemState = ItemState.QUEUED
    output: Path | None = None      # done일 때만 확정 (INV-02)
    error_key: str | None = None    # i18n 키 (P-04)
    renamed: bool = field(default=False)  # 자동 리네임 발생 여부 (INV-05 사후 보고)

    def __post_init__(self):
        """알 수 없는 확장자가 실제 지원 가능한 영상일 때만 내부 routing key 사용.

        실제 `.video` 확장자 등과 충돌하지 않도록 TARGETS에 가상 확장자를 넣지
        않고 `@video` 전용 key를 사용한다. 지원 불가 파일은 원래 확장자 값을
        그대로 유지한다.
        """
        from . import converters
        if not converters.supported(self.source_fmt) and converters.is_content_detected_video(self.source):
            self.source_fmt = converters.content_video_key()

    @property
    def name(self) -> str:
        return self.source.name
