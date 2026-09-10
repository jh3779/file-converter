"""FBX(Autodesk) 3D 모델 읽기 전용 지원 — REQ-F-020 확장(DEC-069 · OQ-007).

기성 라이브러리 `ufbx`는 mesh 배열 데이터(`.vertices`/`.vertex_indices`)
접근 후 인터프리터 종료 시점에 8/8 재현되는 세그폴트가 있어(use-after-free,
lldb로 근본 원인 확정) 채택 불가였다(spike/fbx/RESULT.md 1단계). 대신
네이티브 확장이 전혀 없는 순수 Python 파서를 직접 구현한다 —
spike/fbx/spike_parser.py 2단계 스파이크에서 실현 가능성을 검증했고, 이
모듈은 그 파싱 로직을 프로덕션 수준(압축 배열 실사용 검증·좌표축
정규화·삼각형화·씬 연결 해석)으로 확장한 것이다. spike_parser.py 자체는
스파이크 기록으로 그대로 남기고(app/는 spike/에 의존하지 않음), 이 모듈은
독립적으로 다시 구현했다.

**범위**: FBX 7.x 바이너리의 형태(geometry)만 읽는다 — 애니메이션·
스키닝·머티리얼·텍스처는 범위 밖(다른 4개 포맷 컨버터와 같은 "형태 위주"
원칙, model3d.py 참고). **쓰기(FBX로 내보내기)는 지원하지 않는다** — FBX는
`converters/__init__.py`의 TARGETS에 소스로만 노출되고 대상으로는 노출
안 됨(`ufbx` 자체도 로더 전용이었던 것과 같은 제약, RESULT.md 1단계 §배경).

**알려진 한계(정직하게 문서화, 후속 과제)**:
1. **FBX 6.x는 지원 안 함** — Geometry가 별도 `Objects/Geometry`가
   아니라 `Model` 노드 안에 직접 내장되는 다른 오브젝트 모델을 쓴다
   (RESULT.md 2단계에서 실측 확인). 이 모듈은 `Objects/Geometry`가
   없으면 "쓸 수 있는 지오메트리를 못 찾음" 오류로 명확히 실패한다
   (크래시가 아니라 정직한 실패).
2. **ASCII FBX는 지원 안 함** — 바이너리 매직 헤더가 없으면 즉시 명확히
   거부한다(바이너리만).
3. **Model 노드의 로컬 변환(Translation/Rotation/Scaling)은 적용하지
   않는다** — Translation/Rotation/Scaling이 항등(identity)인 오브젝트만
   정확하다(3D 프린팅용 단일 메시처럼 원점에 변환 없이 배치된 흔한 사용
   사례가 해당). 원점 근처에 있어도 회전·스케일이 걸려 있으면(이동만
   없고 회전·크기가 non-identity인 경우도 포함) 부정확해질 수 있다 —
   "원점 근처"라는 위치 자체가 정확성을 보장하지 않는다. 여러 오브젝트가
   있거나 오브젝트가 원점에서 크게 벗어난 씬은 위치·회전이 원본과 다를
   수 있다. 실제 Blender 다중 오브젝트 fixture(Cube+Light+Camera+Cone)로
   직접 확인—
   Geometry 자체의 형태·크기·축 방향은 정확히 재현되고, Model의
   Translation만큼 위치가 원점 쪽으로 어긋난다. 실사용 피드백을 보고
   필요해지면 Translation/Rotation/Scaling 베이킹을 후속 과제로 추가한다.
   이 한계(와 아래 4번 단위 배율)는 대상 포맷과 무관하게 항상 변환 전
   UI에 고지된다(`note.fbx_source`, `app/ui/main_window.py`의
   `_update_note()` — model3d.py의 `note.stl_no_color`와 같은 패턴).
4. **GlobalSettings의 UnitScaleFactor(단위 배율)는 적용하지 않는다** —
   축 정규화(Y-up 통일)는 실제 Z-up fixture로 직접 검증했지만, 단위
   배율의 실사용 해석은 제작 도구마다 관례가 갈려(Maya 기본 cm, Blender
   기본 m, 3ds Max 사용자 설정에 따라 다름) 잘못 추정해 적용하면 오히려
   크기를 더 틀리게 만들 위험이 있다고 판단해, 원본 스토리지 값을
   배율 변경 없이 그대로 사용한다(보수적 선택).
5. **오목 다각형(non-convex polygon) 삼각형화는 부정확할 수 있음** —
   fan triangulation(첫 정점 기준 부채꼴 분할)만 구현했다. 볼록
   다각형(실사용 대다수)은 정확하고, 오목 다각형은 삼각형이 메시 바깥으로
   튀어나올 수 있다(다른 5개 포맷도 각자의 단순화 한계가 있는 것과 같은
   성격 — DEC-036의 곡선 근사, DEC-054의 곡선 bounding box 근사 등).

**검증**: `tests/fixtures/fbx/`의 실제 Maya·Blender 익스포트 픽스처로
직접 검증(ufbx 저장소 커밋 `fcc5d6ba444cfd3eb80677dba5e37e493941abe5`,
MIT/Unlicense 이중 라이선스, `tests/fixtures/fbx/README.md` 참고) —
비압축(FBX 7400/7500, 4/8바이트 오프셋 양쪽)·zlib 압축 배열(Blender
Suzanne, 실사용 압축 파일 최초 검증)·Z-up→Y-up 축 정규화(실제 Blender
Z-up 씬)·여러 오브젝트가 있는 씬에서 Connections로 실제 연결된 Geometry만
선별하는 것까지 전부 실제 파일로 확인했다.
"""
import array
import struct
import sys
import zlib
from pathlib import Path

from .base import ConversionError

_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_SCALAR_FMT = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
_SCALAR_SIZE = {"Y": 2, "C": 1, "I": 4, "F": 4, "D": 8, "L": 8}
_ARRAY_ELEM_FMT = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}
_ARRAY_ELEM_SIZE = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}

# 배열 property를 `struct.unpack()` 뒤 `list(...)`로 이중 물질화하면(원소
# 하나당 별도 파이썬 객체 + 그 객체들을 담는 리스트 포인터 배열이 한 번 더
# 생김) 256MiB 배열(float 6700만 개) 기준 실제 순간 메모리가 raw
# bytes(256MB) + 튜플(원소당 32바이트 상당, ~2.1GB) + list 포인터 배열
# (~536MB)로 겹쳐 ~2.7GB까지 치솟는다 — `_MAX_ARRAY_BYTES`라는 이름이
# 약속하는 상한과 실제 순간 메모리가 10배 이상 벌어진다(3라운드 review
# 지적). `array` 모듈은 원소를 개별 파이썬 객체로 만들지 않고 C 배열처럼
# 압축 저장해(예: float 배열이면 원소당 정확히 4바이트, 객체 헤더 오버헤드
# 없음) 이 간극을 없앤다.
#
# 다만 `array` 모듈의 typecode는 struct의 `<`/`>` 같은 명시적 크기 지정이
# 없고 C 컴파일러의 네이티브 타입 크기를 그대로 쓴다 — 특히 FBX의
# 'l'(64비트 정수)은 array 모듈 typecode 'l'(C `long`)에 매핑하면 안 된다.
# `long`은 LP64(대부분의 64비트 macOS/Linux)에서는 8바이트지만 LLP64
# (Windows 64비트)에서는 4바이트라 플랫폼에 따라 데이터가 반으로 잘려
# 조용히 틀린 값을 읽게 된다. 대신 'q'(C `long long`)를 쓴다 — C 표준상
# long long은 최소 64비트가 보장되고, 사실상 모든 실사용 컴파일러가
# 정확히 8바이트로 구현한다.
_ARRAY_TYPECODE = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}


def _array_fast_path_typecodes() -> dict:
    """이 플랫폼에서 실제로 안전하게 쓸 수 있는 `array` typecode만 골라
    반환한다 — (1) `array` 모듈은 항상 네이티브 바이트 순서를 쓰는데 FBX
    바이너리 포맷 자체는 리틀엔디안으로 고정이라, 빅엔디안 플랫폼에서는
    바이트가 뒤집혀 읽힌다. (2) typecode의 실제 itemsize가 위에서 가정한
    바이트 크기와 다른(이론상으로만 존재하는) 플랫폼도 있을 수 있다. 두
    조건 중 하나라도 안 맞으면 그 타입은 빼서, 호출자가 느리지만 항상
    정확한 `struct.unpack()` 경로로 조용히 폴백하게 한다."""
    if sys.byteorder != "little":
        return {}
    safe = {}
    for type_code, typecode in _ARRAY_TYPECODE.items():
        try:
            if array.array(typecode).itemsize == _ARRAY_ELEM_SIZE[type_code]:
                safe[type_code] = typecode
        except ValueError:
            pass
    return safe


_ARRAY_FAST_PATH_TYPECODE = _array_fast_path_typecodes()

# 파일 하나가 프로세스를 종료시키지 않도록 두는, 입력이 아니라 이
# 애플리케이션이 정한 고정 상한 — 이전에는 압축 해제 상한이 입력 파일 자체가
# 선언한 array_length*elem_size였다(uint32라 최대 약 32GiB까지 허용). 그
# 값을 그대로 신뢰하면 "선언 크기만큼만 푼다"는 방어가 무력화된다(review
# 지적). 아래 상한은 이 프로젝트의 실사용 범위(3D 프린팅용 단일 메시 등,
# 모듈 docstring 참고)에 여유 있게 맞춘 값이다.
_MAX_FILE_SIZE = 512 * 1024 * 1024  # 입력 파일 자체 크기 상한
_MAX_ARRAY_ELEMENTS = 100_000_000  # 배열 property 하나의 최대 원소 개수
_MAX_ARRAY_BYTES = 256 * 1024 * 1024  # 배열 property 하나의 최대 바이트(해제 후 기준)
_MAX_TOTAL_ARRAY_BYTES = 512 * 1024 * 1024  # 파일 전체에서 누적되는 배열 바이트 상한
_MAX_NODE_COUNT = 2_000_000  # 파일 전체 노드 개수 상한
_MAX_NODE_DEPTH = 128  # 노드 트리 재귀 깊이 상한(스택 오버플로 방어 겸용)

# 파싱 중 던져질 수 있는, "손상되거나 지원 범위 밖"으로 뭉뚱그려도 되는
# 저수준 예외 — 전부 err.corrupted로 통일한다(model3d.py의 기존 관례와
# 동일: trimesh.load() 실패도 broad except로 err.corrupted). TypeError도
# 포함 — Vertices/PolygonVertexIndex가 배열 타입 코드가 아닌 스칼라로
# 저장된(비정상적으로 손상된) 파일에서 `len(flat)` 등이 TypeError를
# 던질 수 있어, 이런 경우에도 크래시 대신 err.corrupted로 정직하게 실패한다.
_LOW_LEVEL_ERRORS = (struct.error, zlib.error, UnicodeDecodeError, IndexError, ValueError, TypeError)


class _ParseBudget:
    """파싱 전체에서 공유하는 누적 자원 카운터 — 노드 개수·배열 바이트
    누적치를 여기 모아 개별 property/노드 하나만 봐서는 못 잡는 "작은
    제한 안의 값이 아주 많이 반복되는" 형태의 자원 고갈도 막는다."""

    __slots__ = ("node_count", "total_array_bytes")

    def __init__(self):
        self.node_count = 0
        self.total_array_bytes = 0


class _FbxNode:
    __slots__ = ("name", "properties", "children")

    def __init__(self, name, properties):
        self.name = name
        self.properties = properties
        self.children = []

    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name):
        return [c for c in self.children if c.name == name]


def _read_properties(buf: bytes, pos: int, num_properties: int, budget: "_ParseBudget | None" = None) -> tuple[list, int]:
    if budget is None:
        budget = _ParseBudget()
    props = []
    for _ in range(num_properties):
        type_code = chr(buf[pos])
        pos += 1
        if type_code in _SCALAR_FMT:
            (val,) = struct.unpack_from(_SCALAR_FMT[type_code], buf, pos)
            props.append(val)
            pos += _SCALAR_SIZE[type_code]
        elif type_code in _ARRAY_ELEM_FMT:
            array_length, encoding, compressed_length = struct.unpack_from("<III", buf, pos)
            pos += 12
            elem_size = _ARRAY_ELEM_SIZE[type_code]
            elem_fmt = _ARRAY_ELEM_FMT[type_code]
            # 입력이 선언한 array_length(uint32, 최대 약 32GiB 상당)를 그대로
            # 압축 해제 상한으로 쓰면 방어가 완성되지 않는다(review 지적) —
            # 압축 해제를 시도하기 전에, 이 애플리케이션이 정한 고정 상한과
            # 먼저 비교해 명확히 거부한다.
            declared_bytes = array_length * elem_size
            if array_length > _MAX_ARRAY_ELEMENTS or declared_bytes > _MAX_ARRAY_BYTES:
                raise ConversionError("err.corrupted", "fbx: 배열 property 선언 크기가 허용 한도를 초과함")
            budget.total_array_bytes += declared_bytes
            if budget.total_array_bytes > _MAX_TOTAL_ARRAY_BYTES:
                raise ConversionError("err.corrupted", "fbx: 파일 전체 배열 누적 크기가 허용 한도를 초과함")
            if encoding == 0:
                raw = buf[pos : pos + array_length * elem_size]
                pos += array_length * elem_size
            elif encoding == 1:
                # 압축 해제 전에 기대 크기를 정해두고 그 상한까지만 풀어
                # 압축 폭탄류(비정상적으로 큰 array_length·조작된 압축
                # 블록이 무제한 메모리 할당을 유발) 방어한다 — zlib.decompress()를
                # 그대로 쓰면 크기 검증이 전체를 다 푼 "뒤"에야 일어나 그 사이
                # 거대한 메모리 할당이 먼저 벌어진다(review 지적 반영).
                expected = array_length * elem_size
                decompressor = zlib.decompressobj()
                raw = decompressor.decompress(buf[pos : pos + compressed_length], expected + 1)
                pos += compressed_length
                # 상한(expected+1)까지 풀었는데도 스트림이 안 끝났다는 건
                # 실제 압축 해제 결과가 선언된 크기보다 크다는 뜻 —
                # unconsumed_tail/eof로 이를 확인한다(전체를 다 풀지 않고도
                # 판별 가능).
                if len(raw) != expected or not decompressor.eof:
                    raise ConversionError("err.corrupted", "fbx: 압축 해제 크기 불일치")
            else:
                raise ConversionError("err.corrupted", f"fbx: 알 수 없는 배열 인코딩 {encoding}")
            fast_typecode = _ARRAY_FAST_PATH_TYPECODE.get(type_code)
            if fast_typecode is not None:
                # array.array(typecode, raw)는 raw의 바이트를 그대로 C
                # 배열처럼 재해석만 할 뿐 원소별 파이썬 객체를 새로 만들지
                # 않는다 — 아래 struct.unpack()+list() 경로보다 메모리를
                # 훨씬 적게 쓴다. 인덱싱(`flat[i]`)·len()·iteration은 일반
                # list와 동일하게 동작해 하위 코드(_extract_from_nodes 등)를
                # 바꿀 필요가 없다.
                props.append(array.array(fast_typecode, raw))
            else:
                props.append(list(struct.unpack(f"<{array_length}{elem_fmt}", raw)))
        elif type_code in ("S", "R"):
            (length,) = struct.unpack_from("<I", buf, pos)
            pos += 4
            data = buf[pos : pos + length]
            pos += length
            props.append(data if type_code == "R" else data.decode("utf-8", errors="replace"))
        else:
            raise ConversionError("err.corrupted", f"fbx: 알 수 없는 프로퍼티 타입 {type_code!r}")
    return props, pos


def _read_node(buf: bytes, pos: int, use_64bit: bool, budget: "_ParseBudget | None" = None, depth: int = 0):
    if budget is None:
        budget = _ParseBudget()
    # 노드 개수·재귀 깊이 둘 다 입력이 아니라 이 애플리케이션이 정한 고정
    # 상한과 비교한다 — 개수는 (자식이 아주 많은) 넓은 트리, 깊이는 (중첩이
    # 아주 깊은) 좁은 트리 형태의 자원 고갈을 각각 막는다(review 지적).
    budget.node_count += 1
    if budget.node_count > _MAX_NODE_COUNT:
        raise ConversionError("err.corrupted", "fbx: 노드 개수가 허용 한도를 초과함")
    if depth > _MAX_NODE_DEPTH:
        raise ConversionError("err.corrupted", "fbx: 노드 중첩 깊이가 허용 한도를 초과함")
    if use_64bit:
        end_offset, num_properties, _ = struct.unpack_from("<QQQ", buf, pos)
        pos += 24
    else:
        end_offset, num_properties, _ = struct.unpack_from("<III", buf, pos)
        pos += 12
    if end_offset == 0:
        return None, pos + 1  # 널 레코드(자식 목록 종료) — name_len(=0) 1바이트만 남음
    name_len = buf[pos]
    pos += 1
    name = buf[pos : pos + name_len].decode("utf-8", errors="replace")
    pos += name_len
    props, pos = _read_properties(buf, pos, num_properties, budget)
    node = _FbxNode(name, props)
    if pos < end_offset:
        while pos < end_offset:
            child, pos = _read_node(buf, pos, use_64bit, budget, depth + 1)
            if child is None:
                break
            node.children.append(child)
    if pos != end_offset:
        raise ConversionError("err.corrupted", f"fbx: 노드 {name!r} 파싱 후 위치 불일치")
    return node, pos


def _parse(data: bytes) -> tuple[list["_FbxNode"], int]:
    if data[:23] != _MAGIC:
        raise ConversionError("err.corrupted", "fbx: 바이너리 FBX 매직 헤더 불일치(ASCII FBX 미지원)")
    (version,) = struct.unpack_from("<I", data, 23)
    use_64bit = version >= 7500
    pos = 27
    nodes = []
    n = len(data)
    budget = _ParseBudget()
    while pos < n:
        node, pos = _read_node(data, pos, use_64bit, budget)
        if node is None:
            break
        nodes.append(node)
    return nodes, version


def _axis_matrix(nodes: list["_FbxNode"]) -> tuple[list[list[float]], float]:
    """GlobalSettings의 CoordAxis/UpAxis/FrontAxis(+부호)로 Y-up 오른손
    좌표계 정규화 행렬을 만든다. 표준(Maya 기본) 축이면 항등행렬이 되고,
    Z-up 씬(Blender "Z Up" 내보내기 옵션 등)이면 실제로 축을 바꾼다 —
    tests/fixtures/fbx/blender_340_z_up_7400_binary.fbx로 직접 검증."""
    coord_axis, coord_sign = 0, 1
    up_axis, up_sign = 1, 1
    front_axis, front_sign = 2, 1
    gs = next((n for n in nodes if n.name == "GlobalSettings"), None)
    if gs is not None:
        p70 = gs.find("Properties70")
        if p70 is not None:
            values = {c.properties[0]: c.properties[-1] for c in p70.children if c.properties}
            coord_axis = int(values.get("CoordAxis", coord_axis))
            coord_sign = int(values.get("CoordAxisSign", coord_sign))
            up_axis = int(values.get("UpAxis", up_axis))
            up_sign = int(values.get("UpAxisSign", up_sign))
            front_axis = int(values.get("FrontAxis", front_axis))
            front_sign = int(values.get("FrontAxisSign", front_sign))
    # 값 자체가 스펙 위반이면(Axis가 0/1/2 순열이 아니거나 Sign이 ±1이
    # 아님) 여기서 명확히 실패시킨다. 이렇게 하면 두 가지를 동시에 막는다:
    # (1) Sign이 ±1이 아닌 값(예: 2)이면 det≈0 축퇴 방어를 피해가면서
    # (det≈2 등) 축 하나가 조용히 배로 왜곡된 좌표가 나오는 것을 막고,
    # (2) Axis가 0/1/2가 아닌 값(예: 3)이면 아래 matrix[.][axis] 인덱싱에서
    # IndexError가 나는데, 그 호출자(_extract_from_nodes)의 try/except가
    # 이 함수 호출 지점을 감싸지 않아 IndexError가 최상위까지 그대로
    # 전파돼 err.corrupted가 아니라 원인 불명의 err.engine으로 보고되는
    # 문제를 막는다(값 검증이 인덱싱보다 먼저 일어나므로 IndexError 자체가
    # 발생하지 않게 됨 — review 지적 반영).
    axes = (coord_axis, up_axis, front_axis)
    signs = (coord_sign, up_sign, front_sign)
    if set(axes) != {0, 1, 2} or any(s not in (1, -1) for s in signs):
        raise ConversionError("err.corrupted", "fbx: GlobalSettings의 좌표축 설정이 유효하지 않음")
    matrix = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    matrix[0][coord_axis] = float(coord_sign)
    matrix[1][up_axis] = float(up_sign)
    matrix[2][front_axis] = float(front_sign)
    m = matrix
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    return matrix, det


def _apply_axis(matrix: list[list[float]], x: float, y: float, z: float) -> tuple[float, float, float]:
    m = matrix
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z,
        m[1][0] * x + m[1][1] * y + m[1][2] * z,
        m[2][0] * x + m[2][1] * y + m[2][2] * z,
    )


def _connected_geometry_ids(nodes: list["_FbxNode"]) -> set:
    """Connections에서 실제로 Model에 연결된(OO 타입) Geometry ID만
    뽑는다 — 씬에 있지만 안 쓰이는(예: 숨겨진 프록시·백업용) Geometry
    오브젝트를 걸러낸다(RESULT.md "다음 단계 제안" 4번). Connections가
    없거나 못 찾으면 안전하게 모든 Geometry를 포함한다(보수적 기본값)."""
    objs = next((n for n in nodes if n.name == "Objects"), None)
    if objs is None:
        return set()
    all_geometry_ids = {g.properties[0] for g in objs.find_all("Geometry") if g.properties}
    conns = next((n for n in nodes if n.name == "Connections"), None)
    if conns is None:
        return all_geometry_ids
    model_ids = {m.properties[0] for m in objs.find_all("Model") if m.properties}
    connected = set()
    for c in conns.children:
        if c.name != "C" or len(c.properties) < 3 or c.properties[0] != "OO":
            continue
        src_id, dst_id = c.properties[1], c.properties[2]
        if dst_id in model_ids:
            connected.add(src_id)
    return connected & all_geometry_ids if connected else all_geometry_ids


def _triangulate_fan(polygon: list[int]):
    """단순 fan triangulation(첫 정점 기준 부채꼴 분할) — 볼록 다각형은
    정확하고 오목 다각형은 부정확할 수 있다(알려진 한계 5)."""
    for i in range(1, len(polygon) - 1):
        yield (polygon[0], polygon[i], polygon[i + 1])


# LayerElementHole이 실제로 관찰되는 조합(Maya export 기준) — 폴리곤 하나당
# bool 하나(ByPolygon)를 그 값 그대로 참조(Direct)한다. 이 조합 밖의
# MappingInformationType/ReferenceInformationType(예: ByVertice·IndexToDirect)은
# 이 모듈이 해석 방법을 모르므로 조용히 무시하지 않고 명시적으로 거부한다
# (review 지적 — 유효한 FBX 기능을 조용히 무시해 숨긴 면을 살려내면 안 됨).
_HOLE_MAPPING_DIRECT = ("ByPolygon", "Direct")


def _polygon_holes(geom: "_FbxNode", polygon_count: int):
    """Geometry의 `LayerElementHole`에서 폴리곤별 숨김 여부를 읽는다.
    LayerElementHole 자체가 없으면 모든 면이 보인다는 뜻이라 None을
    반환해 호출자가 필터링을 건너뛰게 한다."""
    hole_node = geom.find("LayerElementHole")
    if hole_node is None:
        return None
    mapping_node = hole_node.find("MappingInformationType")
    ref_node = hole_node.find("ReferenceInformationType")
    mapping = mapping_node.properties[0] if mapping_node and mapping_node.properties else None
    reference = ref_node.properties[0] if ref_node and ref_node.properties else None
    if (mapping, reference) != _HOLE_MAPPING_DIRECT:
        raise ConversionError(
            "err.corrupted", f"fbx: 지원하지 않는 LayerElementHole 매핑 방식({mapping!r}/{reference!r})"
        )
    holes_node = hole_node.find("Holes")
    if holes_node is None or not holes_node.properties:
        raise ConversionError("err.corrupted", "fbx: LayerElementHole에 Holes 배열이 없음")
    holes = holes_node.properties[0]
    if len(holes) != polygon_count:
        raise ConversionError("err.corrupted", "fbx: LayerElementHole의 Holes 배열 길이가 폴리곤 개수와 다름")
    return holes


def _extract_from_nodes(nodes: list["_FbxNode"]) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """이미 파싱된 최상위 노드 목록에서 Geometry를 뽑아 Y-up 정규화·
    삼각형화한 (vertices, faces)를 만든다. `parse_geometry`(파일 IO+바이너리
    파싱)에서 이 부분만 분리해뒀다 — 노드 트리 레벨의 엣지 케이스(Objects
    없음·Connections 없음·빈 프로퍼티 배열 등)를 직접 만든 `_FbxNode` 트리로
    바이너리를 새로 인코딩하지 않고도 단위 테스트할 수 있게 하기 위함
    (tests/test_fbx.py 참고)."""
    objs = next((n for n in nodes if n.name == "Objects"), None)
    if objs is None:
        raise ConversionError("err.corrupted", "fbx: Objects 노드가 없음(지원 범위 밖 FBX 버전일 수 있음)")

    matrix, det = _axis_matrix(nodes)
    if abs(det) < 1e-9:
        # GlobalSettings의 CoordAxis/UpAxis/FrontAxis가 서로 중복돼(예: 둘 다
        # 같은 축을 가리킴) 특이(singular) 행렬이 되는 손상된 파일 — 이 경우
        # 행렬식만 보면 반사(det<0)도 회전(det>0)도 아니라 한 축이 조용히
        # 다른 축과 겹쳐 찌그러진다(예: X·Y 성분이 같은 값이 됨). 크래시도
        # err.corrupted도 없이 찌그러진 메시가 그대로 export되는 것을 막기
        # 위해, 다른 손상 파일 케이스(PolygonVertexIndex 범위 초과 등)와
        # 동일하게 여기서 명확히 실패시킨다.
        raise ConversionError("err.corrupted", "fbx: GlobalSettings의 좌표축 설정이 축퇴(degenerate)됨")
    flip_winding = det < 0
    connected_ids = _connected_geometry_ids(nodes)

    all_vertices: list[tuple[float, float, float]] = []
    all_faces: list[tuple[int, int, int]] = []
    try:
        for geom in objs.find_all("Geometry"):
            if geom.properties and geom.properties[0] not in connected_ids:
                continue
            vertices_node = geom.find("Vertices")
            poly_idx_node = geom.find("PolygonVertexIndex")
            if vertices_node is None or poly_idx_node is None:
                continue
            flat = vertices_node.properties[0]
            # Vertices는 (x, y, z) 세 값씩 묶인 배열이어야 한다 — 3의 배수가
            # 아니면 손상된 파일인데, 예전에는 `range(0, len(flat) - 2, 3)`로
            # 남는 좌표 1~2개를 그냥 버려 손상을 조용히 가려버렸다(review
            # 지적). 여기서 명확히 실패시킨다.
            if len(flat) % 3 != 0:
                raise ConversionError("err.corrupted", "fbx: Vertices 배열 길이가 3의 배수가 아님")
            base = len(all_vertices)
            local_vertex_count = len(flat) // 3
            for i in range(0, len(flat), 3):
                all_vertices.append(_apply_axis(matrix, flat[i], flat[i + 1], flat[i + 2]))
            poly_indices = poly_idx_node.properties[0]
            polygon_count = sum(1 for idx in poly_indices if idx < 0)
            holes = _polygon_holes(geom, polygon_count)
            polygon: list[int] = []
            polygon_index = 0
            for idx in poly_indices:
                is_last = idx < 0
                local_idx = ~idx if is_last else idx
                # base를 더하기 전에 이 Geometry 안에서의 로컬 범위부터
                # 검증한다 — base를 더한 뒤(전역 인덱스)에만 검증하면, 앞쪽
                # Geometry의 범위 초과 로컬 인덱스가 뒤쪽 Geometry들이 늘려준
                # 전체 정점 수 안에 우연히 들어와 검증을 통과해버릴 수 있다
                # (서로 무관한 Geometry의 정점을 잇는 삼각형이 조용히 생성되는
                # 위험 — review 지적 반영). 이 함수 끝의 최종 전역 검증은
                # 다른 방식의 손상에 대한 안전망으로 남겨둔다.
                if local_idx < 0 or local_idx >= local_vertex_count:
                    raise ConversionError("err.corrupted", "fbx: PolygonVertexIndex가 정점 범위를 벗어남")
                real_idx = local_idx + base
                polygon.append(real_idx)
                if is_last:
                    # 종결된 폴리곤의 정점이 3개 미만(0~2정점)이면 삼각형을
                    # 만들 수 없는 손상된 데이터다 — 예전에는 fan
                    # triangulation이 삼각형 0개를 내놓는 것으로 조용히
                    # 흡수해버렸다(review 지적).
                    if len(polygon) < 3:
                        raise ConversionError("err.corrupted", "fbx: 폴리곤의 정점 수가 3 미만")
                    if holes is None or not holes[polygon_index]:
                        tris = list(_triangulate_fan(polygon))
                        if flip_winding:
                            tris = [(c, b, a) for (a, b, c) in tris]
                        all_faces.extend(tris)
                    polygon_index += 1
                    polygon = []
            if polygon:
                # 루프가 끝났는데 마지막 폴리곤이 종결(음수 인덱스)되지
                # 않은 채 남아있다 — PolygonVertexIndex 끝에 종결자가
                # 누락된 손상 파일이다(review 지적, 예전에는 이 잔여
                # 정점들이 조용히 버려졌다).
                raise ConversionError("err.corrupted", "fbx: PolygonVertexIndex에 폴리곤 종결자가 없음")
    except _LOW_LEVEL_ERRORS as e:
        raise ConversionError("err.corrupted", str(e))

    if not all_vertices or not all_faces:
        raise ConversionError("err.corrupted", "fbx: 변환 가능한 지오메트리를 찾지 못함(FBX 6.x는 미지원)")
    # 방어적 경계 검증 — PolygonVertexIndex가 같은 Geometry의 Vertices
    # 개수보다 큰 인덱스를 담고 있는(손상된) 파일이면, 뒤 파이프라인
    # (trimesh/numpy)에 넘기기 전에 여기서 명확히 실패시킨다. process=False로
    # trimesh에 넘기므로(load_trimesh) trimesh 쪽 자체 검증에 기대지 않는다 —
    # 검증 없이 넘기면 인덱스가 배열 범위를 벗어난 채로 조용히 내보내져
    # 깨진 출력 파일이 될 위험이 있다(이 프로젝트의 "정직한 실패" 원칙).
    vertex_count = len(all_vertices)
    if any(i < 0 or i >= vertex_count for tri in all_faces for i in tri):
        raise ConversionError("err.corrupted", "fbx: PolygonVertexIndex가 정점 범위를 벗어남")
    return all_vertices, all_faces


def parse_geometry(src: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """FBX 파일에서 Connections로 Model에 실제 연결된 Geometry를 전부 읽어
    Y-up으로 정규화·삼각형화한 (vertices, faces)를 반환한다. 여러
    Geometry가 있으면 하나의 정점/면 목록으로 합친다(trimesh.load의
    force="mesh"와 같은 관례, model3d.py 참고)."""
    try:
        # 파일 전체를 메모리로 읽기 전에 먼저 크기부터 확인한다 — read_bytes()
        # 뒤에 검사하면 거대한 파일이 거부되기 전에 이미 다 메모리에 올라가
        # 버려 방어 의미가 없어진다(review 지적).
        size = src.stat().st_size
        if size > _MAX_FILE_SIZE:
            raise ConversionError("err.corrupted", "fbx: 파일 크기가 허용 한도를 초과함")
        data = src.read_bytes()
        nodes, _version = _parse(data)
    except ConversionError:
        raise
    except OSError as e:
        raise ConversionError("err.disk", str(e))
    except _LOW_LEVEL_ERRORS as e:
        raise ConversionError("err.corrupted", str(e))

    return _extract_from_nodes(nodes)


def load_trimesh(src: Path):
    """FBX를 읽어 trimesh.Trimesh로 반환한다 — model3d.py의 convert_3d()가
    trimesh.load() 대신 이 함수를 호출한다(FBX는 trimesh가 자체 지원하지
    않는 포맷)."""
    import numpy as np
    import trimesh

    vertices, faces = parse_geometry(src)
    return trimesh.Trimesh(
        vertices=np.array(vertices, dtype=float),
        faces=np.array(faces, dtype=int),
        process=False,
    )
