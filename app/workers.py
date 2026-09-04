"""변환 작업 실행 — STATE-001·002 · M-03.

UI 스레드는 변환하지 않는다. FileItem 1개 = QRunnable 1개.
워커 → UI는 시그널로만 통신하고, 모델 상태 전이는 UI 스레드에서 수행한다.
"""
import logging
import os
import shutil
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import converters
from .converters.base import ConversionError
from .models import FileItem
from .output import finalize, make_tmpdir

logger = logging.getLogger(__name__)


class JobSignals(QObject):
    item_started = Signal(int)
    item_done = Signal(int, str, bool)      # id, output_path, renamed
    item_failed = Signal(int, str)          # id, error i18n key
    item_skipped = Signal(int)
    job_finished = Signal()


class _Task(QRunnable):
    def __init__(self, job: "Job", item: FileItem):
        super().__init__()
        self.job = job
        self.item = item

    def run(self):
        job, item = self.job, self.item
        if job.cancelled:
            job.signals.item_skipped.emit(item.id)
            job._one_finished()
            return
        job.signals.item_started.emit(item.id)
        tmpdir = make_tmpdir()
        try:
            produced = converters.convert(item.source, item.target_fmt, tmpdir)
            if job.cancelled:
                # 취소: 결과 폐기 + 임시파일 삭제 (STATE-002 전이)
                job.signals.item_failed.emit(item.id, "err.cancelled")
            else:
                out, renamed = finalize(produced, item.source, item.target_fmt)
                job.signals.item_done.emit(item.id, str(out), renamed)
        except ConversionError as e:
            job.signals.item_failed.emit(item.id, e.key)
        except OSError:
            job.signals.item_failed.emit(item.id, "err.disk")
        except Exception:
            # 알려진 실패 종류(ConversionError·OSError)로 안 걸러진 예외 —
            # 미리 분류해둔 오류가 아니라는 뜻이라 원인을 로그에 남긴다
            # (사용자에게는 여전히 일반화된 err.engine 문구만 노출).
            logger.exception("변환 중 예상하지 못한 오류: %s → %s", item.source, item.target_fmt)
            job.signals.item_failed.emit(item.id, "err.engine")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            job._one_finished()


class Job:
    """ConversionJob (ENT-001). 실패해도 나머지는 계속 진행한다 (INV-04)."""

    def __init__(self, items: list[FileItem]):
        self.signals = JobSignals()
        self.items = items
        self.cancelled = False
        self._remaining = len(items)
        # _one_finished()는 최대 4개의 워커 스레드에서 동시에 호출된다.
        # "읽고 1 빼고 쓰기"는 원자적이라는 보장이 없어(파이썬 GIL 구현
        # 세부사항에 기대는 것일 뿐 언어 스펙이 아님), 마지막 항목이 끝나도
        # job_finished가 안 울려 변환 중 화면에 영구히 멈출 이론적 위험이
        # 있다 — 락으로 감싼다.
        self._lock = threading.Lock()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max(1, min(4, (os.cpu_count() or 2) - 1)))

    def start(self):
        for item in self.items:
            self._pool.start(_Task(self, item))

    def cancel(self):
        self.cancelled = True

    def _one_finished(self):
        with self._lock:
            self._remaining -= 1
            done = self._remaining == 0
        if done:
            self.signals.job_finished.emit()
