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

**프로세스당 스레드는 최대 1개만 스폰**(아래 `_thread`) — AppData 경로의
네트워크 리다이렉트 여부는 프로세스가 살아있는 동안 바뀌지 않으므로,
`History()`가 생성될 때마다(테스트 스위트처럼 `MainWindow`를 반복해서
만드는 경우 포함) 매번 새로 스레드를 스폰할 이유가 없다. 실제로 CI(Linux)에서
`unittest discover`가 `MainWindow`를 대량으로 생성하는 테스트들을 거치며
이 함수가 반복 호출되자, 누적된 스레드 생성이 결국 `pthread_create`/CPython
내부 스레드 상태 락 경합으로 스레드 생성 자체가 멈추는 지점까지 가서 전체
테스트 프로세스가 무기한 정지하는 게 실제로 재현됐다(faulthandler로 확보한
스택 트레이스가 `threading.Thread.start()` → `_bootstrap_inner` →
`_set_tstate_lock`에서 멈춰 있음을 보여줬다, FBX 작업과는 무관 — 이
모듈 자체의 "매번 새 스레드" 설계가 원인).

**중요 — 타임아웃과 "확정된 실패"는 다르다**: 첫 버전의 캐싱은 타임아웃
시점의 `None`을 그 자리에서 영구 캐시해버리는 실수를 했다(review 지적) —
`logging_setup.setup()`이 먼저 호출해 타임아웃되면, 그 직후 `History()`가
호출할 때는 백그라운드 스레드가 실제로 막 성공했더라도 이미 캐시된
`None`을 돌려받아 해당 세션 내내 기록이 `:memory:`로 고정돼 사라지는
결과 손실이 생길 수 있었다. 지금은 스레드가 아직 끝나지 않았으면(타임아웃)
캐시를 확정하지 않고 그 스레드 참조만 들고 있다가, 다음 호출에서 **새
스레드를 또 만들지 않고 같은 스레드를 다시 `join()`**한다 — 스레드가
실제로 끝났을 때(성공이든, `OSError`로 인한 확정된 실패든)만 결과를
영구 캐시한다.
"""
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_DEFAULT_TIMEOUT = 2.0

_UNRESOLVED = object()
_cache = _UNRESOLVED  # 확정된 결과(Path 또는 None) 또는 아직 _UNRESOLVED
_thread: threading.Thread | None = None
_thread_result: dict[str, Path] = {}  # 현재 _thread와 짝을 이루는 결과 그릇
_cache_lock = threading.Lock()


def resolve(timeout: float = _DEFAULT_TIMEOUT) -> Path | None:
    """AppData 디렉터리를 만들고 반환한다. 정해진 시간 안에 못 끝내면(예:
    네트워크로 리다이렉트된 경로가 응답 없음) None을 반환한다 — 호출자가
    그 자리에서 알맞게 성능 저하(fallback) 처리를 해야 한다.

    확정된 결과(성공한 Path, 또는 스레드가 실제로 끝났는데 실패한 경우의
    None)는 프로세스 생애 동안 캐시된다. 아직 스레드가 안 끝나서 이번
    호출이 타임아웃된 경우는 캐시를 확정하지 않는다 — 다음 호출에서 새
    스레드를 스폰하지 않고 같은 스레드를 이어서 기다린다(그 사이 스레드가
    끝났으면 바로 확정, 아직이면 다시 대기)."""
    global _cache, _thread, _thread_result
    with _cache_lock:
        if _cache is not _UNRESOLVED:
            return _cache

        if _thread is None:
            # 이 스레드 전용 결과 그릇을 클로저로 캡처한다(모듈 전역
            # 이름으로 참조하지 않음) — `_reset_cache_for_tests()`가 나중에
            # `_thread_result`를 새 dict로 갈아치워도, 이 스레드가 뒤늦게
            # 끝나면서 쓰는 곳은 항상 자기 생성 시점에 캡처한 이 dict
            # 그대로다. 모듈 전역 이름으로 썼다면, 테스트에서 타임아웃으로
            # 살아남은 좀비 스레드가 한참 뒤(몇 테스트 지나서) 깨어나
            # 그 시점에 바인딩된 `_thread_result`(다른 테스트가 쓰고 있는
            # 그릇)에 잘못 써버릴 수 있었다(review 지적).
            result: dict[str, Path] = {}
            _thread_result = result

            def _resolve():
                try:
                    base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
                    base.mkdir(parents=True, exist_ok=True)
                    result["path"] = base
                except OSError:
                    pass

            _thread = threading.Thread(target=_resolve, daemon=True)
            _thread.start()

        _thread.join(timeout)
        if _thread.is_alive():
            # 아직 안 끝남 — 이번 호출엔 성능 저하(None)로 응답하되, 결과를
            # 확정 짓지 않는다. 같은 스레드가 백그라운드에서 계속 돌고
            # 있으니 다음 호출이 다시 join해서 그 사이 끝났는지 확인한다.
            return None
        _cache = _thread_result.get("path")
        return _cache


def _reset_cache_for_tests() -> None:
    """테스트 전용 — 캐시·스레드 참조를 초기화해 다음 `resolve()` 호출이
    실제로 다시 스레드를 스폰하도록 되돌린다. 프로덕션 코드에서는 호출하지
    않는다. 직전 테스트가 남긴 스레드가 아직 살아있어도(예: 타임아웃
    재현용으로 일부러 오래 재우는 mock), 그 스레드는 자기 생성 시점에
    캡처한 결과 그릇에만 쓰므로 여기서 만드는 새 `_thread_result`를
    건드리지 못한다."""
    global _cache, _thread, _thread_result
    with _cache_lock:
        _cache = _UNRESOLVED
        _thread = None
        _thread_result = {}
