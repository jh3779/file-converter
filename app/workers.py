"""변환 작업 실행 — STATE-001·002 · M-03.

UI 스레드는 변환하지 않는다. FileItem 1개 = QRunnable 1개.
워커 → UI는 시그널로만 통신하고, 모델 상태 전이는 UI 스레드에서 수행한다.
"""
import logging
import os
import shutil
import threading
from pathlib import Path

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


class FileDetectionSignals(QObject):
    ready = Signal(object)  # FileItem — 감지가 끝난 완성된 항목


class _CreateItemTask(QRunnable):
    """확장자만으로 지원 여부를 못 정하는 파일의 FileItem 생성을 백그라운드
    스레드에서 수행한다.

    FileItem.__post_init__(models.py)이 확장자 미지원 파일에 대해 콘텐츠
    기반 영상 감지(ffprobe subprocess, 최대 수십 초 타임아웃)를 동기적으로
    실행하는데, 드롭/파일 선택 이벤트 핸들러(main_window.py의 dropEvent·
    _browse → add_files)는 워커 스레드 디스패치 없이 Qt 메인 스레드에서
    바로 호출된다 — 즉 미지원 확장자 파일 하나를 드롭하기만 해도 UI가
    그 시간만큼 그대로 멈췄다(정밀 검증에서 발견). FileItem 생성 자체를
    이 QRunnable로 옮겨 무거운 판정이 메인 스레드를 막지 않게 한다."""

    def __init__(self, item_id: int, source: Path, source_fmt: str, signals: FileDetectionSignals):
        super().__init__()
        self.item_id = item_id
        self.source = source
        self.source_fmt = source_fmt
        self.signals = signals

    def run(self):
        try:
            item = FileItem(self.item_id, self.source, self.source_fmt)
        except Exception:
            # PySide6는 QRunnable 안의 미처리 예외를 애플리케이션에 전파하지
            # 않고 조용히 삼킨다 — 가드가 없으면 사용자가 드롭한 파일이
            # 목록에 아예 안 뜨고 원인도 어디에도 안 남는다(정밀 재검증
            # 지적). _Task.run()과 같은 원칙으로 로그에 남긴다.
            logger.exception("파일 항목 생성 중 예상하지 못한 오류: %s", self.source)
            return
        self.signals.ready.emit(item)


def create_file_item_async(item_id: int, source: Path, source_fmt: str, signals: FileDetectionSignals):
    """QThreadPool의 전역 인스턴스에 생성 작업을 맡긴다 — 변환용 Job이 쓰는
    스레드풀(Job.__init__, 동시 실행 수 제한)과는 별개다. 파일 추가는
    변환과 동시에 일어나지 않고(파일을 추가하는 동안엔 변환 중이 아님),
    작업 하나하나가 짧아 동시 실행 수를 따로 제한할 이유가 없다."""
    QThreadPool.globalInstance().start(_CreateItemTask(item_id, source, source_fmt, signals))


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
            content_video = (
                item.target_fmt == "mp4"
                and converters.is_content_detected_video(item.source)
            )
            produced = converters.convert(item.source, item.target_fmt, tmpdir)
            if job.cancelled:
                # 취소: 결과 폐기 + 임시파일 삭제 (STATE-002 전이)
                job.signals.item_failed.emit(item.id, "err.cancelled")
            else:
                # 확장자 없는/알 수 없는 영상은 원본 파일명 전체가 basename이다.
                # 예: 26.09.06 → 26.09.06.mp4. 일반 변환은 기존 source.stem 규칙 유지.
                stem = item.source.name if content_video else None
                out, renamed = finalize(
                    produced, item.source, item.target_fmt, stem=stem,
                )
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
