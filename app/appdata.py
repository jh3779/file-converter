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

**프로세스당 1회만 실제로 스레드를 스폰**(아래 `_cache`) — AppData 경로의
네트워크 리다이렉트 여부는 프로세스가 살아있는 동안 바뀌지 않으므로,
`History()`가 생성될 때마다(테스트 스위트처럼 `MainWindow`를 반복해서
만드는 경우 포함) 매번 새로 스레드를 스폰할 이유가 없다. 실제로 CI(Linux)에서
`unittest discover`가 `MainWindow`를 대량으로 생성하는 테스트들을 거치며
이 함수가 반복 호출되자, 누적된 스레드 생성이 결국 `pthread_create`/CPython
내부 스레드 상태 락 경합으로 스레드 생성 자체가 멈추는 지점까지 가서 전체
테스트 프로세스가 무기한 정지하는 게 실제로 재현됐다(faulthandler로 확보한
스택 트레이스가 `threading.Thread.start()` → `_bootstrap_inner` →
`_set_tstate_lock`에서 멈춰 있음을 보여줬다, FBX 작업과는 무관 — 이
모듈 자체의 "매번 새 스레드" 설계가 원인). 캐싱으로 프로세스 생애 동안
많아야 1개의 스레드만 만들도록 고쳤다.
"""
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_DEFAULT_TIMEOUT = 2.0

_UNRESOLVED = object()
_cache = _UNRESOLVED
_cache_lock = threading.Lock()


def resolve(timeout: float = _DEFAULT_TIMEOUT) -> Path | None:
    """AppData 디렉터리를 만들고 반환한다. 정해진 시간 안에 못 끝내면(예:
    네트워크로 리다이렉트된 경로가 응답 없음) None을 반환한다 — 호출자가
    그 자리에서 알맞게 성능 저하(fallback) 처리를 해야 한다.

    결과(성공한 Path든, 타임아웃으로 인한 None이든)는 프로세스 생애 동안
    캐시된다 — 이 값은 프로세스 안에서 바뀌지 않으므로, 두 번째 호출부터는
    스레드를 새로 스폰하지 않고 캐시를 그대로 반환한다."""
    global _cache
    with _cache_lock:
        if _cache is not _UNRESOLVED:
            return _cache

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
        _cache = result.get("path")
        return _cache


def _reset_cache_for_tests() -> None:
    """테스트 전용 — 캐시를 초기화해 다음 `resolve()` 호출이 실제로 다시
    스레드를 스폰하도록 되돌린다. 프로덕션 코드에서는 호출하지 않는다."""
    global _cache
    with _cache_lock:
        _cache = _UNRESOLVED
