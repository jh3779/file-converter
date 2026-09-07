"""AppData(사용자별 로컬 데이터) 경로 해석 — history.py·logging_setup.py 공용.

`QStandardPaths.AppDataLocation`이 회사 로밍 프로필·OneDrive 알려진 폴더
이동 등으로 네트워크 경로에 리다이렉트돼 있으면, 그 네트워크가 응답하지
않을 때 `Path.mkdir()` 자체가 OS 타임아웃까지(수십 초~수 분) 아무 예외도
없이 그냥 멈출 수 있다(실사용 보고로 확인 — 진단 로그·최근 기록 초기화가
둘 다 메인 스레드에서, 앱 창이 뜨기도 전에 이 경로를 만들다가 걸려서,
프로세스는 살아있는데(작업 관리자엔 보임) CPU·디스크 사용률은 0%인 채로
창이 영원히 안 뜨는 것처럼 보였다 — `except OSError`(logging_setup.py)로는
못 잡는다, 애초에 예외가 안 나고 그냥 안 끝나는 것이므로).

별도 스레드에서 시도하고 정해진 시간 안에 못 끝내면 포기한다 — 그 스레드는
데몬이라 나중에 실제로 그 네트워크 호출이 (뒤늦게) 끝나더라도 프로세스
종료를 막지 않는다. 두 번째 소비자(logging_setup.py)가 생겨 공유 모듈로
승격했다(base.py의 read_text_auto_encoding과 같은 이 프로젝트의 관례).
"""
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_DEFAULT_TIMEOUT = 2.0


def resolve(timeout: float = _DEFAULT_TIMEOUT) -> Path | None:
    """AppData 디렉터리를 만들고 반환한다. 정해진 시간 안에 못 끝내면(예:
    네트워크로 리다이렉트된 경로가 응답 없음) None을 반환한다 — 호출자가
    그 자리에서 알맞게 성능 저하(fallback) 처리를 해야 한다."""
    result: dict[str, Path] = {}

    def _resolve():
        try:
            base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
            base.mkdir(parents=True, exist_ok=True)
            result["path"] = base
        except OSError:
            pass

    t = threading.Thread(target=_resolve, daemon=True)
    t.start()
    t.join(timeout)
    return result.get("path")
