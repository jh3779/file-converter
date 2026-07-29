"""번들 리소스 경로 — 배포판(frozen)은 exe 옆 engine/, 개발은 저장소 기준."""
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def engine_dir() -> Path:
    return app_root() / "engine"
