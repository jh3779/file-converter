"""변환 작업 실행 — STATE-001·002 · M-03.

UI 스레드는 변환하지 않는다. FileItem 1개 = QRunnable 1개.
워커 → UI는 시그널로만 통신하고, 모델 상태 전이는 UI 스레드에서 수행한다.
"""
import os
import shutil

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import converters
from .converters.base import ConversionError
from .models import FileItem
from .output import finalize, make_tmpdir


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
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max(1, min(4, (os.cpu_count() or 2) - 1)))

    def start(self):
        for item in self.items:
            self._pool.start(_Task(self, item))

    def cancel(self):
        self.cancelled = True

    def _one_finished(self):
        self._remaining -= 1
        if self._remaining == 0:
            self.signals.job_finished.emit()
