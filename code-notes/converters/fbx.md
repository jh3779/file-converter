# fbx.py — FBX(Autodesk) 읽기 전용 파서

원본: `app/converters/fbx.py` (675줄)

이 프로젝트에서 유일하게 "서드파티 3D 라이브러리에 안 기대고 바이너리
포맷을 직접 파싱하는" 파일이다. `model3d.py`가 trimesh 하나로 5개
포맷을 다 처리하는 것과 대조적으로, FBX는 trimesh가 아예 지원하지
않는 포맷이라 `struct`·`zlib` 표준 라이브러리만으로 바이너리 트리
파서를 새로 만들었다. 왜 그래야 했는지(ufbx 세그폴트)와 무엇을
검증했는지가 이 파일의 핵심 서사다. 코드 리뷰를 여섯 차례 거치며
`LayerElementHole`(숨긴 면) 처리, 애플리케이션 기준 자원 한도,
Geometry 구조 잔여 검증(2차), 배열 property 자료구조를
`struct.unpack()+list()`에서 `array.array`로 교체한 메모리 최적화(3차),
그 전환이 남긴 배열 길이 미검증 회귀 수정과 정점·면 전개 단계의
별도 상한(4차), 그 면 상한 검사 자체가 triangulation 물질화 이후에야
실행되던 우회 경로 차단과 노드 `end_offset`의 부모/파일 경계 사전
검증(5차), 그리고 그 정점·면 상한 자체가 실제 순간 메모리를 안전하게
막지 못했던 문제를 정점·면 출력 자료구조를 파이썬 튜플 리스트에서
평탄(flat) `array.array`로 바꿔 해소한 것(6차)이 차례로 추가됐다 —
아래 각 절에서 다룬다.

---

## L1-61: 모듈 docstring

네 부분으로 나뉜다:

1. **왜 자체 파서인가(L3-11)**: 기성 라이브러리 `ufbx`(C 네이티브 확장,
   MIT/Unlicense)를 먼저 시도했는데, mesh 배열 데이터(`.vertices`
   등)에 접근한 뒤 인터프리터가 종료되는 시점에 8/8 재현되는
   세그폴트가 있었다(`spike/fbx/RESULT.md` 1단계 — `lldb`로 근본
   원인을 use-after-free로 특정). 그래서 네이티브 확장이 전혀 없는
   순수 Python 파서를 직접 구현했다 — 구조적으로 이 클래스의 버그
   (dealloc 순서 의존성) 자체가 발생할 수 없다.
2. **범위(L13-17)**: 형태(geometry)만 읽는다(다른 5개 포맷 컨버터와
   같은 "형태 위주" 원칙). **쓰기(FBX로 내보내기)는 아예 없다** —
   `__init__.py`의 `TARGETS`에 FBX는 소스로만 등록되고 대상으로는
   노출되지 않는다.
3. **알려진 한계 5가지(L19-52)**: 아래 각 절에서 대응하는 코드와 함께
   설명. `LayerElementHole` 지원·자원 한도·구조 검증은 "알려진 한계"가
   아니라 실제로 해소한 방어이므로 이 목록에는 없다.
4. **검증(L54-60)**: `tests/fixtures/fbx/`의 실제 Maya·Blender
   익스포트로 비압축(7400/7500)·zlib 압축·좌표축 정규화·Connections
   필터링을 전부 실제 파일로 확인했다(fixture 자체의 출처·라이선스는
   `tests/fixtures/fbx/README.md`). **주의**: `LayerElementHole`
   처리는 ufbx가 자체 테스트용으로 제공하는
   `data/maya_polygon_hole_7700_binary.fbx` fixture로 검증하는 게
   이상적이지만, 이 저장소 작업 환경에서 외부 네트워크 접근이 막혀
   아직 받아오지 못했다 — 대신 `tests/test_fbx.py::TestFbxLayerElementHole`가
   다른 재현 어려운 손상 케이스(`TestFbxRobustness`)와 같은 방식으로
   `_FbxNode` 트리를 직접 구성해 검증한다. 실제 바이너리 fixture 추가는
   후속 과제로 남아 있다.

## L70-170: import·상수(배열 자료구조·자원 상한)·저수준 예외 타입

```python
_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_SCALAR_FMT = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
_ARRAY_ELEM_FMT = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}
_ARRAY_TYPECODE = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}
_MAX_FILE_SIZE = 512 * 1024 * 1024
_MAX_ARRAY_ELEMENTS = 100_000_000
_MAX_ARRAY_BYTES = 256 * 1024 * 1024
_MAX_TOTAL_ARRAY_BYTES = 512 * 1024 * 1024
_MAX_NODE_COUNT = 2_000_000
_MAX_NODE_DEPTH = 128
_MAX_VERTEX_COUNT = 10_000_000
_MAX_FACE_COUNT = 10_000_000
_OUTPUT_VERTEX_TYPECODE = "d"
_OUTPUT_FACE_TYPECODE = "q"
_LOW_LEVEL_ERRORS = (struct.error, zlib.error, UnicodeDecodeError, IndexError, ValueError, TypeError)
```

FBX 바이너리 포맷의 프로퍼티 타입 코드(1바이트 문자)를 파이썬
`struct` 포맷 문자열로 매핑하는 테이블 — 스칼라(`Y/C/I/F/D/L`)와
배열(`f/d/l/i/b`)이 서로 다른 테이블에 있다는 게 핵심 구조.

**배열 property의 자료구조 — `array.array` fast path(L76-117, 3차 리뷰
지적 반영)**: 배열 property를 예전처럼 `struct.unpack()` 뒤
`list(...)`로 이중 물질화하면(원소 하나당 별도 파이썬 객체 + 그
객체들을 담는 리스트 포인터 배열이 한 번 더 생김) 256MiB 배열(float
6700만 개) 기준 실제 순간 메모리가 raw bytes(256MB) + 튜플(~2.1GB) +
list 포인터 배열(~536MB)로 겹쳐 ~2.7GB까지 치솟는다 — `_MAX_ARRAY_BYTES`
라는 이름이 약속하는 상한과 실제 순간 메모리가 10배 이상 벌어졌다.
`array` 모듈은 원소를 개별 파이썬 객체로 만들지 않고 C 배열처럼
압축 저장해 이 간극을 없앤다. 다만 `array` typecode는 struct의
`<`/`>` 같은 명시적 크기 지정이 없고 C 컴파일러의 네이티브 타입
크기를 그대로 쓴다 — 특히 FBX의 `'l'`(64비트 정수)은 `array`
typecode `'l'`(C `long`, Windows 64비트에서는 4바이트일 수 있음)이
아니라 `'q'`(C `long long`, 사실상 항상 8바이트)로 매핑해야 한다
(`_ARRAY_TYPECODE`). `_array_fast_path_typecodes()`(L97-114)는 이
플랫폼에서 (1) 리틀엔디안이고(`array`는 항상 네이티브 바이트 순서를
쓰는데 FBX는 리틀엔디안으로 고정) (2) typecode의 실제 itemsize가
가정한 바이트 수와 일치하는 typecode만 걸러 `_ARRAY_FAST_PATH_TYPECODE`
로 캐싱해두고, 둘 중 하나라도 안 맞는 타입은 빼서 호출자가 느리지만
항상 정확한 `struct.unpack()` 경로로 조용히 폴백하게 한다.

**이 fast path가 4차 리뷰에서 낸 회귀와 그 수정(L132-147)**은
`_read_properties` 절에서 다룬다.

**`_MAX_*` 상한(L119-147)**: 압축 해제 상한이 예전에는 입력 파일
자체가 선언한 `array_length*elem_size`였다(그 값 자체가 uint32라
최대 약 32GiB까지 허용 — "선언 크기만큼만 푼다"는 방어가 사실상
무력화된 상태였다). 이제는 애플리케이션이 정한 고정 값과 먼저
비교한다: 파일 크기(`_MAX_FILE_SIZE`), 배열 property 하나의 원소
개수·바이트(`_MAX_ARRAY_ELEMENTS`/`_MAX_ARRAY_BYTES`), 파일 전체에서
누적되는 배열 바이트(`_MAX_TOTAL_ARRAY_BYTES`, 작은 배열이 아주
많이 반복되는 형태의 자원 고갈 방어), 노드 개수·재귀 깊이
(`_MAX_NODE_COUNT`/`_MAX_NODE_DEPTH`, 각각 "넓은" 트리와 "깊은" 트리
형태의 자원 고갈 방어). 값 자체는 이 프로젝트의 실사용 범위(3D
프린팅용 단일 메시 등, 모듈 docstring 참고)에 여유 있게 맞췄다.

이 상한들은 입력 단계(`array.array`로 압축 저장된 원시 배열)만
지킨다 — `_extract_from_nodes`가 이 원시 배열에서 정점·면을 새로
조립하는 출력 단계에도 별도 상한이 필요하다(4차 리뷰 지적).
`_MAX_VERTEX_COUNT`/`_MAX_FACE_COUNT`는 이를 막는 별도 상한인데,
**상한 값(정점·면 각 1000만 개) 자체는 4차 이후 그대로이지만, 그
상한이 실제로 억제하는 순간 메모리 크기는 6차에서 크게 바뀌었다**:

- **4~5차 시점(개선 전)**: 정점·면을 (x, y, z)/(i, j, k) 파이썬 튜플의
  리스트로 전개해 쌓았다. 실측(CPython, 64비트, `sys.getsizeof` 기준)
  (float,float,float) 튜플 하나가 튜플 자체(72바이트)+float 객체
  3개(72바이트)+리스트 슬롯 포인터(8바이트)=약 152바이트, 면 튜플도
  약 164바이트 — 상한(각 1000만 개)까지 채우면 튜플 리스트만으로도
  각각 최대 약 1.4~1.5GiB. 여기에 더해 `load_trimesh`가 이 튜플
  리스트를 `np.array()`로 NumPy 배열로 복제하는 동안 원본 튜플
  리스트와 사본 NumPy 배열이 동시에 살아있는 순간이 생겨, 상한까지
  채운 파일 하나로 순간 메모리가 약 3GiB까지 치솟을 수 있었다(6차
  review 지적 Finding 1 — 상한 값은 있었지만 "정점·면 개수"라는
  상한과 "실제 순간 메모리" 사이의 배율이 너무 커서, 정상적인 대형
  photogrammetry 모델도 상한에 도달하기 훨씬 전에 프로세스가 OOM으로
  죽을 위험이 있었다. 필수 보완 판정).
- **6차 수정 후**: 정점·면을 파이썬 객체 리스트가 아니라
  `array.array('d')`(정점, x0,y0,z0,x1,... 평탄 배열)/`array.array('q')`
  (면, i0,j0,k0,i1,... 평탄 배열)에 직접 기록한다(`_OUTPUT_VERTEX_TYPECODE`/
  `_OUTPUT_FACE_TYPECODE`) — 원소 하나당 정확히 8바이트(파이썬 객체
  헤더 없음)만 쓴다. `load_trimesh`도 이 평탄 배열을 `np.array()`로
  버퍼 복사 1회에 NumPy 배열로 옮긴다(아래 `load_trimesh` 절 참고) —
  튜플 리스트 단계 자체가 없어졌다. 같은 상한(정점·면 각 1000만 개)
  기준 순간 메모리는 이제 정점·면 평탄 배열 각각 최대 약 240MiB
  (1000만 × 3 × 8바이트) 수준, `np.array()` 복사가 잠깐 더하는 사본까지
  합쳐도 최대 약 960MiB 수준으로 억제된다 — 6차 이전 추정치(~3GiB)
  대비 3배 이상 감소, 상한 값 자체를 낮추지 않고도 review 지적을
  해소한다.

3D 프린팅용 메시(보통 수십만~수백만 삼각형, 극단적 사례도
수백만~천만 단위)에는 상한 값 자체가 여전히 여유 있다. 적용 지점은
`_extract_from_nodes` 절에서 다룬다.

**`_OUTPUT_VERTEX_TYPECODE`/`_OUTPUT_FACE_TYPECODE`**: 입력 파싱
경로의 `_ARRAY_TYPECODE`와 같은 이유로 `'l'`이 아니라 `'d'`/`'q'`를
쓴다 — `'d'`(C `double`)는 IEEE 754 8바이트가 사실상 보편적이고,
`'q'`(C `long long`)는 `array` 모듈 문서상 최소 8바이트가 보장된다
(반대로 `'l'`은 Windows 64비트에서 4바이트일 수 있어 위험). 둘 다
NumPy dtype(`np.float64`/`np.int64`)과 짝지어 8바이트로 맞춰뒀다 —
`load_trimesh`의 `np.array()`가 원소별 파이썬 객체 변환 없이 버퍼를
통째로 복사할 수 있게 하기 위해서다.

`_LOW_LEVEL_ERRORS`는 이 파일 전체의 예외 처리 철학을 담은
튜플이다 — "파싱 중 뭐가 잘못됐든 사용자에게는 `err.corrupted`
하나로 통일해서 보여준다"(model3d.py가 `trimesh.load()` 실패를
전부 `except Exception`으로 뭉뚱그리는 것과 같은 원칙, 다만 여기서는
`Exception` 전체가 아니라 "이 정도는 손상된 파일이라 봐도 되는"
구체적인 타입 목록으로 좁혔다 — `ConversionError` 자체나 진짜
프로그래밍 버그(예상 못한 `AttributeError` 등)는 그대로 전파되게
하려는 의도). `TypeError`가 포함된 이유는 코드 리뷰 중 추가된
방어 — `Vertices`가 스칼라 타입 코드로 잘못 저장된 손상 파일에서
`len(flat)`이 던질 수 있는 예외까지 커버한다. `err.too_large`(새
i18n 키, `app/i18n.py`)는 이 튜플에 없다 — 정점·면 상한 초과는
"손상"이 아니라 "너무 큼"이라 `ConversionError`를 직접 던지고
`_LOW_LEVEL_ERRORS`로 감싸 재포장하지 않는다.

## L158-167: `_ParseBudget` — 파싱 전체에서 공유하는 자원 카운터(2차 리뷰 반영)

```python
class _ParseBudget:
    __slots__ = ("node_count", "total_array_bytes")
```

`node_count`(지금까지 읽은 노드 개수)와 `total_array_bytes`(지금까지
누적된 배열 property 바이트)만 담는 아주 얇은 카운터. `_parse`가
파일 하나당 인스턴스 하나를 만들어 `_read_node`→`_read_properties`
재귀 호출 전체에 같은 인스턴스를 전달한다(`_parse` 절 참고) — 개별
노드/배열 하나만 봐서는 못 잡는 "작은 값이 아주 많이 반복되는" 형태의
자원 고갈까지 이 공유 카운터로 잡는다. 모든 호출부에서
`budget: _ParseBudget | None = None` 기본값을 두고 `None`이면 함수
안에서 새로 만드는 이유는, `tests/test_fbx.py`의 기존 테스트들이
`fbx._read_properties(buf, 0, 1)`/`fbx._parse(data)`처럼 budget 없이
직접 호출하는 패턴을 그대로 유지하기 위해서다(하위 호환).

## L170-185: `_FbxNode` — 파싱된 노드 트리의 최소 표현

```python
class _FbxNode:
    __slots__ = ("name", "properties", "children")
```

FBX 바이너리는 재귀적인 노드 트리 구조다(이름 + 프로퍼티 리스트 +
자식 노드 리스트, XML의 element와 비슷하다고 생각하면 된다).
`__slots__`를 쓴 건 큰 씬(수천 개 노드)에서 메모리를 아끼기 위한
전형적인 최적화. `find`/`find_all`은 자식 중 특정 이름을 가진
노드를 찾는 유틸 — DOM의 `querySelector`와 비슷한 역할을 아주
단순하게 구현한 것.

## L188-271: `_read_properties` — 프로퍼티 하나씩 파싱

타입 코드 1바이트를 읽고 세 갈래로 분기한다:
- **스칼라(`_SCALAR_FMT`에 있음)**: 고정 크기라 `struct.unpack_from`
  한 번으로 끝.
- **배열(`_ARRAY_ELEM_FMT`에 있음, L199-262)**: `array_length`·
  `encoding`·`compressed_length` 3개의 uint32 헤더가 먼저 온다.
  **압축 해제/슬라이싱을 시도하기 전에(L204-213, 2차 리뷰 반영)**
  `array_length`·`declared_bytes(=array_length*elem_size)`를
  `_MAX_ARRAY_ELEMENTS`/`_MAX_ARRAY_BYTES`와 먼저 비교해 명확히
  거부하고, `budget.total_array_bytes`에 누적해 파일 전체 상한
  (`_MAX_TOTAL_ARRAY_BYTES`)도 검사한다. 이 검사를 통과해야 비로소
  `encoding == 0`이면 비압축 raw bytes를 그대로 읽고, `encoding == 1`
  이면 `zlib.decompress()`로 압축을 푼다(L217-234) — 압축 해제 결과가
  선언된 `array_length * elem_size`와 다르면(길이 불일치든
  `decompressor.eof`가 안 끝났든) 손상으로 간주해 즉시 실패한다.
  이 압축 경로가 바로 알려진 한계 목록에서 "실사용 검증"이 필요했던
  부분 — Blender의 Suzanne fixture로 실제 압축 배열을 직접
  디코딩해 참조 OBJ와 좌표까지 대조했다(README 참고).

  **`raw` 길이 검증이 인코딩과 무관하게 공통으로 있다(L235-251, 4차
  리뷰 지적 Finding 1)**: `raw`를 만든 직후(encoding 0/1 어느
  쪽이든) `len(raw) != declared_bytes`면 즉시 `err.corrupted`. 왜
  필요한가 — 비압축 분기(`encoding == 0`)의 `buf[pos:pos+n]` 슬라이싱은
  파이썬 관용 동작상 `buf`가 그 길이를 다 못 채워도 예외 없이 더
  짧은 `bytes`를 조용히 반환한다. 3라운드에서 추가한 fast path
  (`array.array(typecode, raw)`, L252-262)는 `len(raw)`가 `elem_size`의
  배수이기만 하면 선언된 원소 개수보다 적어도 그냥 성공해버려서 —
  파일이 중간에 잘렸는데도 조용히 더 짧은 배열로 파싱되는 방어
  공백이 새로 생겼었다(기존 `struct.unpack(f"<{array_length}{elem_fmt}",
  raw)` 폴백 경로는 포맷 문자열이 정확한 원소 개수를 요구해 이미
  `struct.error`로 암묵적으로 막고 있었으나, fast path는 그 보호가
  없었다). 이 검증을 두 경로 공통으로 앞에 둬 대칭을 맞췄다 —
  `tests/test_fbx.py::TestFbxUncompressedArrayTruncation`이 이 회귀를
  직접 재현해 고정한다(수정 전 코드로는 조용히 통과했음을 별도
  스크립트로 확인).
- **fast path 자체(L252-262, 3차 리뷰 지적 Finding 1)**: `array.array(typecode,
  raw)`는 raw의 바이트를 그대로 C 배열처럼 재해석만 할 뿐 원소별
  파이썬 객체를 새로 만들지 않는다 — 위 상수 절에서 다룬 이중
  물질화 문제를 없앤다. 이 플랫폼에서 안전하지 않은 typecode
  (`_ARRAY_FAST_PATH_TYPECODE`에 없는 것, 상수 절 참고)는
  `struct.unpack()+list()` 폴백으로 조용히 넘어간다.
- **문자열/raw(`S`/`R`)**: 4바이트 길이 접두 + 그만큼의 바이트.
  `S`는 UTF-8 문자열로 디코딩, `R`은 원본 바이트 그대로(raw 프로퍼티,
  이 모듈에서는 실제로 쓰이지 않지만 파싱은 정상적으로 통과해야
  뒤따르는 노드 파싱이 안 깨진다).

알 수 없는 타입 코드(L269-270)는 명확한 `ConversionError`.

## L274-328: `_read_node` — 노드 하나(헤더+프로퍼티+자식) 재귀 파싱

**노드 개수·재귀 깊이 상한(L293-297, 2차 리뷰 반영)**: 헤더를 읽기도
전에 가장 먼저 `budget.node_count`를 올리고 `_MAX_NODE_COUNT`와,
`depth`를 `_MAX_NODE_DEPTH`와 비교한다 — 노드 개수는 (자식이 아주
많은) 넓은 트리, 깊이는 (중첩이 아주 깊은) 좁은 트리 형태의 자원
고갈을 각각 막는다. 자식을 재귀 호출할 때(L322) `depth + 1`을 넘겨
깊이가 누적되게 한다.

가장 까다로운 부분은 **버전에 따라 헤더 필드 크기가 다르다**는 점
(L298-303) — FBX 7500부터 `EndOffset`/`NumProperties`/
`PropertyListLen`이 uint32(4바이트씩, 총 12바이트)에서 uint64(8바이트씩,
총 24바이트)로 바뀐다. `use_64bit` 플래그 하나로 `struct` 포맷
문자열만 바꿔 전체 파싱 로직을 그대로 재사용한다.

**널 레코드 처리(L304-305)**: `end_offset == 0`이면 이 위치는 자식
목록의 끝을 알리는 13/25바이트짜리 특수 레코드다 — 이름도 프로퍼티도
없이 헤더 뒤에 `name_len(=0)` 1바이트만 더 있다.

**`end_offset`의 부모/파일 경계 사전 검증(L280·284-289·306-313, 5차
리뷰 지적)**: 예전에는 헤더에서 읽은 `end_offset`을 곧바로 신뢰해 그
위치까지 재귀 파싱을 계속한 뒤, 끝나고 나서야(L326-327)
`pos != end_offset`인지 사후 검사했다 — `end_offset` 자체가 버퍼
길이나 부모 노드의 `end_offset`을 넘는 값이어도 그 사실 자체를
미리 걸러내지 않았다(결국은 `struct.unpack_from`/인덱싱에서
`struct.error`/`IndexError`가 나서 `_LOW_LEVEL_ERRORS`로 잡혀
`err.corrupted`가 되긴 했지만, 명시적인 방어가 아니라 우연한
결과였다). 이제는 `parent_end`라는 새 인자(부모 노드의 `end_offset`,
최상위 호출은 파일 전체 길이)를 받아, 헤더에서 `end_offset`을 읽은
직후 `pos <= end_offset <= parent_end`를 확인하고 위반하면 즉시
`err.corrupted`로 실패시킨다. 재귀 호출(L322)이 자식에게 물려주는
`parent_end`는 현재 노드 자신의 `end_offset`이다 — 이렇게 하면 각
노드가 "내 부모가 허용한 범위 안에서만" 존재할 수 있다는 불변식이
트리 전체에 재귀적으로 유지된다. `parent_end`가 안 주어지면(예: 이
함수를 단독 호출하는 기존 테스트들, L288-289) `len(buf)`로 안전하게
기본값 처리해 하위 호환을 유지한다.

**자식 파싱의 미묘한 분기(L320-325)**:
```python
if pos < end_offset:
    while pos < end_offset:
        child, pos = _read_node(buf, pos, use_64bit, budget, depth + 1, end_offset)
        if child is None:
            break
        node.children.append(child)
if pos != end_offset:
    raise ConversionError(...)
```
FBX 바이너리는 **자식이 없는 리프 노드는 널 레코드 자체를 아예
생략한다**(공식 문서가 없는, 리버스 엔지니어링으로 알려진 포맷
특유의 관례). 그래서 프로퍼티까지 다 읽은 시점에 `pos`가 이미
`end_offset`과 같으면(자식 없음) `while` 루프에 아예 안 들어가고,
그렇지 않으면(자식이 있음, 마지막엔 널 레코드로 끝남) 루프를 돈다.
마지막 `if pos != end_offset`은 이 두 경우 모두를 소화한 뒤 그래도
위치가 안 맞으면 파싱 자체가 잘못됐다는 뜻이라 명확히 실패시키는
전체 파일의 정합성 체크다 — 위 `parent_end` 사전 검증과는 별개의
안전망으로 남겨둔다(사전 검증은 "이 노드가 허용된 범위 밖으로
뻗어나가려 하는가"를, 이 사후 검사는 "실제로 다 읽고 나니 선언한
위치와 정확히 맞아떨어지는가"를 확인한다).

## L331-345: `_parse` — 파일 전체 진입점

매직 헤더 23바이트(`_MAGIC`) 확인 → 4바이트 버전 → `use_64bit` 결정
→ `pos=27`부터 최상위 노드를 반복해서 읽는다. `_ParseBudget()`을
여기서 파일 하나당 하나만 만들어(L339) 모든 최상위 노드의 `_read_node`
호출에 그대로 넘긴다 — 이 인스턴스가 파일 전체의 노드 개수·배열
바이트 누적치를 들고 있다. 각 최상위 호출에 `parent_end=n`(파일 전체
길이)을 명시적으로 넘겨(L341, 5차 리뷰 지적) 최상위 노드의
`end_offset`도 파일 길이를 넘지 못하게 한다. 최상위에서도 널 레코드를
만나면(`node is None`) 바로 멈추는데, 이건 실제 FBX 파일에는 최상위
널 레코드 뒤에 썸네일·푸터 같은 노드 트리가 아닌 잡다한 바이너리가
더 있기 때문 — 이 파일은 그 뒤를 아예 안 본다(형태 데이터는 이미 다
읽었으므로 필요 없음).

## L348-391: `_axis_matrix` — 좌표축 정규화 행렬 계산

알려진 한계 목록에는 없지만(오히려 "해결한" 부분) 이 파일에서 가장
수학적인 함수다. FBX의 `GlobalSettings/Properties70`에서
`CoordAxis`/`UpAxis`/`FrontAxis`(각 0/1/2 = X/Y/Z 중 어느 축인지)와
그 부호(`*Sign`)를 읽어 3×3 행렬을 만든다:

```python
matrix[0][coord_axis] = float(coord_sign)
matrix[1][up_axis] = float(up_sign)
matrix[2][front_axis] = float(front_sign)
```

행렬의 각 행이 "결과 좌표계의 X/Y/Z축이 원본의 어느 축에서 오는가"를
나타낸다 — 표준 Maya 축(`CoordAxis=0,UpAxis=1,FrontAxis=2`, 전부 부호
+1)이면 이 행렬은 항등행렬이 된다. Blender가 "Z Up" 옵션으로 내보낸
파일은 `UpAxis=2`가 되고, 그러면 `matrix[1][2] = 1`이 돼 원본의 Z
성분이 결과의 Y 위치로 옮겨간다 — `tests/test_fbx.py`의
`test_z_up_axis_actually_normalized_to_y_up`이 이 사실 자체를 원본
저장값과 직접 대조해서 검증한다(단순히 "정점 개수가 맞다"가 아니라
"Z였던 값이 진짜로 Y 위치에 나타난다"까지 확인).

행렬식(`det`, L365-369)이 음수면 이 변환이 반사(거울상, 오른손↔왼손
좌표계 전환)를 포함한다는 뜻 — 이런 경우 삼각형의 정점 순서(winding)를
그대로 두면 노멀이 뒤집힌 것처럼 보이므로, `_extract_from_nodes`에서
`flip_winding` 플래그로 삼각형의 두 번째·세 번째 정점을 맞바꾼다
(`_extract_from_nodes` 절 참고).

## L394-400: `_apply_axis` — 행렬-벡터 곱

`_axis_matrix`가 만든 3×3 행렬을 정점 하나(x, y, z)에 적용하는 순수
함수. 딱 행렬-벡터 곱 공식 그대로라 특별한 트릭은 없다.

## L403-423: `_connected_geometry_ids` — Connections 기반 필터링

FBX 씬은 `Objects` 아래 여러 `Geometry`가 있을 수 있는데, 그중
일부는 실제로 화면에 보이는 Model에 연결 안 된 "고아" 데이터일 수
있다(숨겨진 프록시, 백업용 등). `Connections` 노드는 `C` 자식들로
`("OO", 소스ID, 대상ID)` 형태의 오브젝트-오브젝트 연결을 나열하는데,
이 함수는 그중 대상이 실제 `Model`인 연결만 골라 그 소스(Geometry)
ID 집합을 만든다.

**안전한 기본값이 두 겹으로 있다는 점이 중요하다**:
1. `Connections` 노드 자체가 없으면(L392-393) 바로 모든 Geometry
   포함.
2. `Connections`는 있지만 실제로 Model에 연결된 게 하나도 안 잡히면
   (L402, `connected & all_geometry_ids if connected else
   all_geometry_ids`) 그래도 모든 Geometry를 포함 — "잘못 걸러내서
   조용히 데이터가 사라지는 것"보다 "약간 더 포함시키는 것"이 훨씬
   안전하다는 이 프로젝트 전반의 원칙(TARGETS의 "가능한 것만
   노출"과는 반대 방향이지만 같은 "조용한 유실 방지" 철학).

## L426-430: `_triangulate_fan` — 다각형 삼각형화

```python
def _triangulate_fan(polygon: list[int]):
    for i in range(1, len(polygon) - 1):
        yield (polygon[0], polygon[i], polygon[i + 1])
```

FBX의 `PolygonVertexIndex`는 4각형 이상의 폴리곤을 그대로 담을 수
있는데, 이후 파이프라인(trimesh export)은 삼각형만 다룬다. 첫
정점을 고정하고 나머지를 순서대로 이어 부채꼴로 쪼개는 가장 단순한
방법(fan triangulation) — 볼록 다각형은 항상 정확하지만 오목
다각형은 삼각형이 메시 경계 밖으로 튀어나올 수 있다(모듈 docstring
알려진 한계 5번). 실제 fixture의 정육면체(4각형)·Suzanne(대부분
4각형)은 전부 볼록이라 이 한계에 걸리지 않는다. 이 함수 자체는
호출자(`_extract_from_nodes`)가 폴리곤 정점이 3개 이상임을 이미
검증해준다고 가정한다(정점 0~2개인 입력은 빈 제너레이터를 내놓을 뿐
에러를 내지 않는다 — 그 검증은 호출자 책임).

## L433-462: `_HOLE_MAPPING_DIRECT`·`_polygon_holes` — 숨긴 면 처리(2차 리뷰 반영)

FBX의 `LayerElementHole`은 `Geometry`마다 폴리곤별로 "이 면은 숨김"
여부를 담을 수 있는 레이어다(Maya의 홀(hole) 폴리곤 기능). 예전
버전은 이 레이어를 아예 읽지 않아 `Vertices`/`PolygonVertexIndex`만
보고 모든 폴리곤을 그대로 삼각형화했다 — 즉 유효한 FBX 기능으로
숨겨둔 면이 조용히 복원돼 버렸다(닫힌 부분이 막힌 메시로 나옴).

```python
_HOLE_MAPPING_DIRECT = ("ByPolygon", "Direct")
```

실제로 관찰되는 조합(Maya export 기준)은 폴리곤 하나당 bool 하나
(`MappingInformationType=ByPolygon`)를 그 값 그대로 참조
(`ReferenceInformationType=Direct`)하는 것뿐이다. `_polygon_holes`는:
1. `LayerElementHole` 자식이 아예 없으면 `None`을 반환한다 — 호출자가
   이를 "모든 면이 보임"으로 해석해 필터링을 건너뛴다(안전한 기본값,
   `_connected_geometry_ids`와 같은 철학).
2. 있는데 `(Mapping, Reference)`가 `_HOLE_MAPPING_DIRECT`가 아니면
   **조용히 무시하지 않고 명시적으로 거부**한다 — 이 모듈이 해석
   방법을 모르는 조합(예: `ByVertice`, `IndexToDirect`)을 만나서
   숨긴 면이 있는지 없는지 확신할 수 없는 상태로 넘어가면 안 되기
   때문(review 지적 — 정직한 실패 원칙).
3. `Holes` 배열이 없거나 길이가 실제 폴리곤 개수와 다르면 손상된
   파일로 보고 거부한다.

## L480-625: `_extract_from_nodes` — 이 파일의 핵심 로직

`parse_geometry`(파일 IO)와 분리된 이유부터 짚을 만하다 — **테스트
용이성 때문에 리팩터링된 함수**다. 노드 트리 레벨의 엣지 케이스
(Objects 없음·Connections 없음·빈 프로퍼티 배열·범위 벗어난 인덱스·
숨긴 면)를 검증하려면 실제로 그런 조건을 만족하는 손상된/특수한
바이너리 FBX 파일을 새로 인코딩해야 하는데, 그 대신 `_FbxNode`를
파이썬 코드로 직접 조립해서 이 함수 하나만 단위 테스트할 수 있게
분리했다(`tests/test_fbx.py::TestFbxRobustness`,
`TestFbxLayerElementHole` 참고).

**반환값은 (x, y, z)/(i, j, k) 튜플의 리스트가 아니라 평탄(flat)
`array.array`다(6차 리뷰 반영, 위 `_MAX_VERTEX_COUNT` 절 참고)** —
정점 N개면 길이 3N짜리 `array.array('d')`(x0,y0,z0,x1,y1,z1,...), 면
M개면 길이 3M짜리 `array.array('q')`(i0,j0,k0,i1,...)다. 아래 동작
순서 설명의 "누적 리스트에 추가" 부분들은 전부 이 평탄 배열에
`.append()` 세 번씩 하는 것으로 바뀌었다 — 어떤 단계에서 튜플이
잠깐이라도 만들어지면(예: `_apply_axis`/`_triangulate_fan`이 돌려주는
`(x, y, z)`/`(a, b, c)`), 그 튜플은 즉시 풀어서(unpack) 평탄 배열에
흘려넣고 바로 버린다 — 튜플 자체를 리스트에 쌓아두지 않는다.

동작 순서:
1. `Objects` 노드가 없으면 즉시 실패(L494-496) — FBX 6.x가 여기
   걸린다(알려진 한계 1번).
2. 좌표축 행렬·Connections 필터를 미리 한 번만 계산(L498-509).
3. `Objects` 아래 모든 `Geometry`를 순회하며(L514), Connections
   필터를 통과 못 하면 건너뛴다(L515-516) — 단, `geom.properties`가
   비어있으면(ID 자체가 없는 비정상 케이스) 단락 평가로 무조건
   포함시킨다(안전한 기본값).
4. `Vertices`/`PolygonVertexIndex` 둘 다 있는 Geometry만 처리
   (L517-520, 둘 중 하나라도 없으면 조용히 skip).
5. **Vertices 3배수 검증(L521-527, 2차 리뷰 반영)**: `len(flat) % 3`이
   0이 아니면 (x, y, z) 세 값씩 안 묶이는 손상된 배열이라 즉시 실패한다
   — 예전엔 `range(0, len(flat) - 2, 3)`로 남는 좌표 1~2개를 그냥
   버려 손상을 조용히 가려버렸다.
6. **정점 상한 검사 후 축 변환 적용(L528-543, 4차 리뷰 지적 Finding
   2)**: `base + local_vertex_count > _MAX_VERTEX_COUNT`면 이 Geometry의
   정점을 평탄 배열에 전개하기 **전에** `err.too_large`로 실패한다 —
   전개가 끝난 뒤에야 확인하면 이미 상한을 훨씬 넘는 만큼 다 써넣은
   뒤라 상한을 둔 의미가 없어진다. 통과하면 정점 좌표를 3개씩 끊어
   축 변환 적용 후(`_apply_axis`가 돌려주는 `(ax, ay, az)` 튜플을
   즉시 풀어 평탄 배열에 원소 3개로 흘려넣음, 6차 리뷰 반영)
   `all_vertices`에 추가한다 — `base = len(all_vertices) // 3`(L528,
   평탄 배열이라 정점 개수는 길이의 1/3)는 여러 Geometry를 하나의
   정점/면 목록으로 합칠 때 인덱스가 겹치지 않게 하는 오프셋.
7. **숨긴 면 조회(L544-546)**: `PolygonVertexIndex`의 음수(폴리곤
   종결자) 개수로 이 Geometry의 폴리곤 총 개수를 미리 세고,
   `_polygon_holes`로 폴리곤별 숨김 플래그(`holes`, 없으면 `None`)를
   가져온다.
8. `PolygonVertexIndex`를 순회하며(L549-610) 음수(비트 NOT으로
   인코딩된 폴리곤 마지막 정점, `~idx`)를 만나면 그 폴리곤이 끝난
   것으로 본다:
   - **로컬 범위 검증(L552-560)**: `base`를 더하기 전에 이 Geometry
     안에서의 로컬 인덱스부터 범위를 검증한다 — base를 더한 뒤(전역
     인덱스)에만 검증하면, 앞쪽 Geometry의 범위 초과 로컬 인덱스가
     뒤쪽 Geometry들이 늘려준 전체 정점 수 안에 우연히 들어와 검증을
     통과해버릴 수 있다(서로 무관한 Geometry의 정점을 잇는 삼각형이
     조용히 생성되는 위험 — review 지적).
   - **폴리곤 인덱스 누적 단계의 조기 면 상한 검사(L561-576, 5차 리뷰
     지적 — 아래 별도 절에서 상세히 다룸)**: `polygon.append(real_idx)`
     직후, 종결자(`is_last`)를 기다리지 않고 매 인덱스 추가마다
     `len(polygon) - 2 > _MAX_FACE_COUNT - current_face_count`를
     확인해 초과하면 즉시 `err.too_large`로 실패한다(`current_face_count
     = len(all_faces) // 3` — 평탄 배열이라 면 개수는 길이의 1/3).
   - **폴리곤 정점 수 검증(L577-583, 2차 리뷰 반영)**: 종결된 폴리곤의
     정점이 3개 미만이면 삼각형을 만들 수 없는 손상된 데이터인데,
     예전에는 `_triangulate_fan`이 삼각형 0개를 내놓는 것으로 조용히
     흡수해버렸다 — 여기서 명확히 실패시킨다.
   - **숨긴 면이 아니면 물질화 전 면 상한 재검사 후 삼각형화(L584-602,
     4차 리뷰 지적 Finding 2 + 5차 리뷰 지적 — 아래 별도 절 참고)**:
     `holes`가 `None`이거나 이 폴리곤의 플래그가 거짓이면(보임)
     `_triangulate_fan(polygon)`을 실제로 돌리기 **전에** 먼저
     `expected_tri_count = len(polygon) - 2`만 계산해 상한 초과 여부를
     확인한다. 통과하면 그제서야 `for a, b, c in _triangulate_fan(polygon)`로
     삼각형을 하나씩 만들며(필요하면 winding 뒤집기) 그 자리에서 바로
     `all_faces`에 원소 3개씩 흘려넣는다(6차 리뷰 반영 — 예전처럼
     `list(_triangulate_fan(...))`로 전체를 리스트에 먼저 모아두지
     않음). 숨긴 면이어도 **정점 자체는 이미 6번에서 추가돼 남아있다**
     — 숨김은 "이 면을 그리지 않는다"는 뜻이지 "이 정점이 없다"는
     뜻이 아니기 때문(다른 폴리곤이 같은 정점을 쓸 수도 있음).
9. **폴리곤 종결자 누락 검증(L605-610, 2차 리뷰 반영)**: 루프가 끝난
   뒤에도 `polygon` 버퍼가 비어있지 않으면, `PolygonVertexIndex` 끝에
   음수 종결자가 없어 마지막 폴리곤이 잘린 것이다 — 예전에는 이
   잔여 정점들이 조용히 버려졌다.
10. **경계 검증(L614-624, 코드 리뷰 중 추가)**: 최종적으로 정점·면이
    하나도 없으면 실패(FBX 6.x·빈 파일·모든 폴리곤이 숨김인 경우
    등), 그리고 신규로 추가된 방어 — 폴리곤 인덱스가 실제 정점 개수
    범위를 벗어나면(손상된 파일) 여기서 명확히 실패시킨다(6차: 평탄
    `all_faces` 배열을 직접 순회하며 `any(i < 0 or i >= vertex_count
    for i in all_faces)`로 확인 — 예전엔 `(i, j, k)` 튜플을 순회하며
    안의 원소를 검사했다). 이 검증이 없으면 `load_trimesh`가
    `process=False`로 trimesh에 넘기기 때문에(아래 절 참고) trimesh
    자체 검증도 기대할 수 없어, 깨진 인덱스가 그대로 export 단계까지
    흘러가 알 수 없는 방식으로 망가진 출력 파일이 나올 위험이 있었다.

**면 상한 검사가 triangulation 물질화 "뒤"에야 실행되던 우회 경로와
그 수정(5차 리뷰 지적)**: 4차에서 추가한 면 상한 검사는
`tris = list(_triangulate_fan(polygon))`로 폴리곤 전체를 이미 삼각형
튜플 리스트로 물질화한 뒤에야 `len(all_faces) + len(tris) >
_MAX_FACE_COUNT`를 확인했다. `polygon`은 종결자(음수 인덱스)가
나오기 전까지 `PolygonVertexIndex`의 인덱스를 계속 누적한 것인데, 이
누적 자체에는 개수 제한이 없었다 — `PolygonVertexIndex` 배열
property 자체의 상한(`_MAX_ARRAY_BYTES`, uint32 기준 약 6700만 개)
까지는 허용됐다. 즉 정점은 몇 개 안 되더라도(`_MAX_VERTEX_COUNT`
통과), `PolygonVertexIndex`가 그 몇 안 되는 정점 인덱스들을 종결자
없이 수천만 번 반복 참조하는 손상된 파일이면, 하나의 거대한
"폴리곤"이 만들어지고 `_triangulate_fan()`이 fan triangulation으로
즉시 (그 폴리곤 길이-2)개의 삼각형 튜플을 `list()`로 한 번에
물질화해버려 — 상한 검사보다 이 물질화가 먼저 일어나므로 상한이
사실상 무력화됐다(실측: 종결자 없이 정점 200만 개를 반복 참조하는
폴리곤 하나로, 수정 전 코드는 peak 메모리 약 178MB·0.45초를 쓴 뒤에야
`err.too_large`를 던졌다). 수정은 **두 지점에 방어를 겹쳐 둔다**:
1. **폴리곤 인덱스 누적 단계(L561-576)**: 종결자를 기다리지 않고,
   `polygon.append(real_idx)` 직후 매번 "이 폴리곤이 지금 당장
   끝난다면(`len(polygon) - 2`개의 삼각형) 남은 예산
   (`_MAX_FACE_COUNT - current_face_count`)을 넘는가"를 확인해 초과
   즉시 실패시킨다 — 폴리곤 리스트 자체가 무한정 자라는 것을 막는
   주된 방어선.
2. **`_triangulate_fan()` 호출 직전(L588-591)**: 실제로 호출하기 전에
   `len(polygon) - 2`(예상 삼각형 개수)만 먼저 계산해 재검사한다 —
   1번 방어와 별개의 방어선으로, `_triangulate_fan()` 자체를 호출하지
   않고 막는다(6차 이후에는 `list(_triangulate_fan(...))`이 아니라
   `for a, b, c in _triangulate_fan(polygon):`로 순회하며 즉시
   평탄 배열에 흘려넣지만, 이 방어가 막는 대상은 동일하게
   `_triangulate_fan()` 호출 자체다).

수정 후 같은 재현 시나리오(정점 200만 개 반복 참조)는
`_triangulate_fan()`이 아예 호출되지 않고 peak 메모리 약 1.75KB·
0.009초 만에 `err.too_large`를 던진다(실측 비교, git stash로 수정
전/후 코드를 오가며 직접 측정). `tests/test_fbx.py::
TestFbxFaceCountLimitBypassViaUnterminatedPolygon`이 `_MAX_FACE_COUNT`를
작게 낮춰 같은 로직을 빠르게 검증하고, `_triangulate_fan`을
`mock.patch.object`로 감싸 실제로 호출되지 않았음을 `assert_not_called()`
로 직접 확인한다.

**정점·면 상한(6·8번)은 `err.too_large`를, 나머지는 전부
`err.corrupted`를 쓴다** — 상한 초과는 "파일이 손상됨"이 아니라
"이 앱이 처리하기엔 너무 큼"이라 사용자에게 다른 메시지를 보여줘야
하기 때문(`app/i18n.py`의 `err.too_large` 키 참고, `err.corrupted`
문구 그대로 쓰면 사용자가 파일이 깨졌다고 오인할 수 있음). 이
두 예외는 `_LOW_LEVEL_ERRORS` 튜플에 없는 `ConversionError`를 직접
던지므로 L611의 `except _LOW_LEVEL_ERRORS`에 잡히지 않고 그대로
전파된다(다른 `ConversionError` raise들과 동일한 패턴).

## L628-651: `parse_geometry` — 공개 API 1 (파일 → 정점/면)

**파일 크기 선(先)검사(L639-641, 2차 리뷰 반영)**: `read_bytes()`로
파일 전체를 메모리에 올리기 전에 `src.stat().st_size`부터
`_MAX_FILE_SIZE`와 비교한다 — 읽은 "뒤"에 검사하면 거대한 파일이
거부되기도 전에 이미 다 메모리에 올라가 버려 방어 의미가 없어진다.
그 다음 파일을 바이트로 읽고(`OSError`는 `err.disk` — `stat()`도
`read_bytes()`도 둘 다 여기서 잡힌다) `_parse()`로 노드 트리를 만든
뒤(저수준 파싱 오류는 `err.corrupted`) `_extract_from_nodes`로
위임한다. `ConversionError`는 그대로 다시 던진다(L644-645) — `_parse`
내부나 파일 크기 검사에서 이미 의미 있는 메시지를 담아 던진 것을
여기서 뭉개면 안 되기 때문(다른 저수준 예외만 새로 감싼다). 반환값은
`_extract_from_nodes`와 동일하게 평탄(flat) `array.array` 쌍이다(6차
리뷰 반영).

## L654-675: `load_trimesh` — 공개 API 2 (파일 → Trimesh 객체)

`model3d.py`의 `convert_3d()`가 소스 확장자가 `.fbx`일 때 호출하는
진입점. `parse_geometry`로 얻은 평탄 `array.array` 쌍(vertices, faces)을
`np.array(..., dtype=np.float64/np.int64).reshape(-1, 3)`로 (N, 3)
NumPy 배열로 바꿔 `trimesh.Trimesh(..., process=False)`를 만든다.

**왜 `np.array()`(항상 복사)이지 `np.frombuffer()`(zero-copy)가
아닌가(6차 리뷰 반영)**: `array.array`는 버퍼 프로토콜을 지원하므로
`np.array()`가 원소별로 파이썬 객체를 만들지 않고 버퍼를 통째로
복사한다(파이썬 튜플 리스트를 거치던 6차 이전 경로보다 훨씬 적은
메모리, 위 `_MAX_VERTEX_COUNT` 절 참고) — 이 지점에서 `np.frombuffer()`를
쓰면 그 복사조차 없앨 수 있지만(진짜 zero-copy), 그렇게 만들어진
NumPy 배열이 always-writable임이 보장되지 않는다(`array.array`의
쓰기 가능 여부·NumPy/플랫폼 버전에 따라 read-only 뷰가 될 수 있음 —
문서화된 보장이 아님). trimesh가 내부적으로 배열에 쓰기를 시도할 수
있는데(`process=False`라도), 이를 실행/테스트로 확인할 수 없는 환경
(코드 리뷰만으로 검증)이었기 때문에 성능보다 안전 쪽(복사)을
택했다 — 필요하면 이후에 `np.frombuffer()` + writability 검증으로
한 단계 더 최적화할 수 있는 여지로 남겨둔다.

**`process=False`가 중요**하다 — trimesh의 기본 로드 처리(중복
정점 병합, 퇴화 삼각형 제거 등)를 여기서는 적용하지 않는다. 이
파서가 이미 유효한 메시를 만들었다고 보고, 후속 export 단계에서
trimesh가 임의로 데이터를 바꾸지 않게 하려는 의도 — 다만 이 때문에
`tests/test_fbx.py`의 왕복 테스트가 obj/stl처럼 텍스트나
비인덱스(triangle-soup) 포맷으로 나갔다가 **다시 로드**할 때는
trimesh가 그 시점의 기본 `process=True`로 근접 좌표를 병합해 정점
수가 살짝 줄 수 있다(예: Suzanne 507→505) — 이건 이 파서의 결함이
아니라 trimesh 재로드 처리의 특성이라, glb처럼 인덱스를 그대로
보존하는 바이너리 포맷으로 정확한 정점 수 일치를 확인하고 텍스트
포맷은 면(위상) 개수만 비교하도록 테스트를 나눴다.

## 테스트 파일에서의 반환 타입 변화 흡수(6차)

`tests/test_fbx.py`는 정점/면을 여전히 `(x, y, z)`/`(i, j, k)` 튜플의
리스트로 다루는 기존 어서션(`len()`, `zip()`, `sorted()`, 튜플 언패킹
등)이 많다 — `fbx.parse_geometry`/`fbx._extract_from_nodes`가 이제
평탄 배열을 반환하므로, 테스트 파일에 `_chunks3(flat)` 헬퍼(3개씩
묶어 튜플 리스트로 되돌림)와 `_parse_geometry_chunked`/
`_extract_from_nodes_chunked` 래퍼 함수를 추가해 기존 어서션을 거의
그대로 유지했다(모든 기존 호출부를 이 래퍼로 일괄 치환). 단,
새로 추가한 메모리 회귀 테스트
(`tests/test_fbx.py::TestFbxVertexFaceMaterializationMemory`)는 이
래퍼를 쓰지 않고 `fbx._extract_from_nodes`를 직접 호출한다 — 래퍼가
다시 튜플로 묶어버리면 이 테스트가 검증하려는 개선(원소별 파이썬
객체 미생성) 자체가 래퍼 안에서 사라져버리기 때문이다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시

- FBX 7500 전후로 노드 헤더 필드 크기가 왜 다르며, 이 코드는 그
  차이를 어디서 어떻게 흡수하는가?
- 자식이 없는 리프 노드에서 널 레코드가 생략된다는 사실을 모른 채
  `_read_node`를 짰다면 어떤 파일에서 어떤 식으로 파싱이 깨졌을까?
- `_connected_geometry_ids`가 "안전한 기본값"을 두 겹으로 둔 이유는
  무엇이고, 만약 반대로 "모르면 제외"를 기본값으로 했다면 어떤
  실사용 시나리오에서 문제가 생겼을까?
- `_extract_from_nodes`를 `parse_geometry`에서 분리한 이유는? 만약
  분리하지 않았다면 "Connections 노드가 없는 경우"를 검증하는
  테스트를 어떻게 작성해야 했을까?
- `load_trimesh`가 `process=False`로 Trimesh를 만드는데, 왜 텍스트
  포맷으로 왕복하면 정점 개수가 줄 수 있는가? 이게 이 파서의
  버그인지 아닌지 어떻게 판단했는가?
- `_polygon_holes`가 `LayerElementHole` 자체가 없을 때와, 있지만
  지원하지 않는 매핑 방식일 때를 서로 다르게 처리하는 이유는?
  왜 후자를 "모든 면이 보임"으로 조용히 넘기면 안 되는가?
- 압축 해제 상한을 입력이 선언한 `array_length`가 아니라
  `_MAX_ARRAY_BYTES` 같은 애플리케이션 고정값으로 바꾼 이유는?
  `_ParseBudget`의 `total_array_bytes`는 개별 배열 상한만으로는
  왜 부족한 어떤 공격/손상 시나리오를 추가로 막는가?
- `array.array` fast path(3차 리뷰 최적화)가 왜 비압축(`encoding == 0`)
  배열에서만 배열 길이 미검증 회귀를 냈는가? 압축(`encoding == 1`)
  분기는 왜 같은 문제가 원래부터 없었는가? 이 회귀를 고치는 검증을
  압축 분기에도 굳이 (중복으로) 넣은 이유는?
- 입력 배열은 `_MAX_ARRAY_BYTES`로 이미 상한이 있는데,
  `_MAX_VERTEX_COUNT`/`_MAX_FACE_COUNT`라는 별도 상한이 왜 추가로
  필요했는가? "입력 바이트가 상한 안"이라는 사실이 "출력 메모리도
  상한 안"이라는 결론으로 이어지지 않는 이유는?
- `_MAX_VERTEX_COUNT`/`_MAX_FACE_COUNT` 위반을 `err.corrupted`가
  아니라 `err.too_large`라는 새 코드로 나눈 이유는? 사용자 관점에서
  두 실패가 왜 다른 메시지를 받아야 하는가?
- 4차에서 추가한 면 상한 검사(`len(all_faces) + len(tris) >
  _MAX_FACE_COUNT`)는 왜 "검사가 있다"는 사실만으로는 충분하지
  않았는가? `list(_triangulate_fan(polygon))`가 이미 호출된 "뒤"에
  검사가 실행되면 구체적으로 어떤 입력이 그 검사를 무력화시키는가?
- 5차 수정은 폴리곤 인덱스 누적 단계(L561-576)와
  `_triangulate_fan()` 호출 직전(L588-591) 두 곳에 방어를 겹쳐
  뒀다. 앞쪽 방어 하나만으로 이미 충분해 보이는데, 뒤쪽 방어를
  "죽은 코드"로 남겨둔 이유는 무엇인가?
- `_read_node`가 `parent_end`를 받기 전에는 헤더의 `end_offset`이
  버퍼 범위를 벗어나도 결국 `_LOW_LEVEL_ERRORS`로 잡혀
  `err.corrupted`가 됐다. 그런데도 명시적인 `parent_end` 검증을 왜
  추가해야 했는가 — "결과적으로 같은 에러가 난다"는 것만으로 왜
  충분하지 않은가?
- `_read_node`의 재귀 호출이 자식에게 물려주는 `parent_end`는 왜
  파일 전체 길이(`len(buf)`)가 아니라 "현재 노드 자신의
  `end_offset`"이어야 하는가? 만약 모든 재귀 호출에 파일 전체
  길이를 그대로 물려줬다면 어떤 손상 파일 패턴을 놓쳤을까?
- 4~5차의 `_MAX_VERTEX_COUNT`/`_MAX_FACE_COUNT` 상한은 "정점·면
  개수"를 제한하는데, 6차 리뷰는 왜 그것만으로는 "실제 순간 메모리"를
  안전하게 제한하지 못한다고 지적했는가? 상한 값(1000만) 자체를
  낮추는 대신 정점·면의 내부 자료구조를 바꾸는 쪽을 택한 이유는?
- `_extract_from_nodes`가 평탄 `array.array`를 반환하도록 바뀐 뒤,
  `base = len(all_vertices) // 3`·`current_face_count = len(all_faces)
  // 3`처럼 "길이를 3으로 나눠 개수를 구하는" 패턴이 여러 곳에
  등장한다. 이 변환을 빠뜨리고 옛날처럼 `len(all_vertices)`를 정점
  개수로 그대로 썼다면 어떤 증상으로 나타났을까(예: `_MAX_VERTEX_COUNT`
  검사가 실제보다 몇 배 느슨해지거나 빡빡해지는 등)?
- `load_trimesh`는 `np.frombuffer()`(진짜 zero-copy)가 아니라
  `np.array()`(항상 복사)를 쓴다. 이 선택이 순수 성능 관점에서는
  최적이 아닐 수 있는데도 왜 이렇게 결정했는가 — 만약 이 프로젝트가
  테스트를 실제로 실행할 수 있는 환경에서 작업했다면 이 결정이
  달라졌을 수 있는가?
- 테스트 파일의 `_extract_from_nodes_chunked` 래퍼는 결과를 다시
  튜플 리스트로 묶어 기존 어서션을 그대로 재사용할 수 있게 한다.
  그런데 `TestFbxVertexFaceMaterializationMemory`는 왜 이 래퍼 대신
  `fbx._extract_from_nodes`를 직접 호출해야만 하는가?
