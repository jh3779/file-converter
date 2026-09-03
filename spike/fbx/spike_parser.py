"""FBX 바이너리 포맷 최소 읽기 전용 파서 — 스파이크 전용, 프로덕션 코드 아님.

목적: 순수 Python(struct·zlib 표준 라이브러리만)으로 FBX 바이너리 파일을
읽어 "Objects/Geometry" 노드 안의 정점(Vertices)·면(PolygonVertexIndex)만
뽑아낼 수 있는지 실현 가능성을 검증한다 — ufbx(네이티브 확장, 세그폴트
버그로 채택 보류, OQ-007)를 대체할 자체 구현이 현실적인지 판단하기 위함.

범위: 형태(geometry)만. 애니메이션·스키닝·머티리얼·텍스처·노드 계층
변환(transform) 전부 범위 밖 — "정점·면 개수가 맞는 mesh를 뽑아낼 수
있는가"만 확인한다.

FBX 바이너리 포맷 구조(공개적으로 알려진 리버스 엔지니어링 스펙 기반,
Autodesk 공식 문서 아님 — 실제 파일로 직접 검증):
  - 헤더: 21바이트 매직 "Kaydara FBX Binary  \\x00" + 2바이트(\\x1a\\x00) + 버전(uint32 LE)
  - 노드 레코드(재귀): EndOffset·NumProperties·PropertyListLen(버전>=7500이면
    8바이트, 아니면 4바이트) + NameLen(1바이트)+Name + Properties + (있으면)
    자식 노드들 + 13/25바이트 널 레코드로 자식 목록 종료
  - 프로�터티 타입 코드(1바이트): Y/C/I/F/D/L=스칼라, f/d/l/i/b=배열(zlib
    압축 가능), S=문자열, R=raw
"""
import struct
import sys
import zlib
from pathlib import Path

_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"

_SCALAR_SIZES = {"Y": 2, "C": 1, "I": 4, "F": 4, "D": 8, "L": 8}
_ARRAY_ELEM_SIZES = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}
_ARRAY_ELEM_FMT = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}


class FbxParseError(Exception):
    pass


def _read_properties(buf: bytes, pos: int, num_properties: int) -> tuple[list, int]:
    """PropertyList를 파싱한다 — (property 값 리스트, 다 읽은 뒤의 pos)."""
    props = []
    for _ in range(num_properties):
        type_code = chr(buf[pos])
        pos += 1
        if type_code in _SCALAR_SIZES:
            size = _SCALAR_SIZES[type_code]
            fmt = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}[type_code]
            (val,) = struct.unpack_from(fmt, buf, pos)
            props.append(val)
            pos += size
        elif type_code in _ARRAY_ELEM_SIZES:
            array_length, encoding, compressed_length = struct.unpack_from("<III", buf, pos)
            pos += 12
            elem_size = _ARRAY_ELEM_SIZES[type_code]
            elem_fmt = _ARRAY_ELEM_FMT[type_code]
            if encoding == 0:
                raw = buf[pos : pos + array_length * elem_size]
                pos += array_length * elem_size
            elif encoding == 1:
                compressed = buf[pos : pos + compressed_length]
                pos += compressed_length
                raw = zlib.decompress(compressed)
                if len(raw) != array_length * elem_size:
                    raise FbxParseError(
                        f"압축 해제 크기 불일치: {len(raw)} != {array_length * elem_size}"
                    )
            else:
                raise FbxParseError(f"알 수 없는 배열 인코딩: {encoding}")
            values = list(struct.unpack(f"<{array_length}{elem_fmt}", raw))
            props.append(values)
        elif type_code == "S" or type_code == "R":
            (length,) = struct.unpack_from("<I", buf, pos)
            pos += 4
            data = buf[pos : pos + length]
            pos += length
            props.append(data if type_code == "R" else data.decode("utf-8", errors="replace"))
        else:
            raise FbxParseError(f"알 수 없는 프로퍼티 타입 코드: {type_code!r} (pos={pos})")
    return props, pos


class FbxNode:
    def __init__(self, name: str, properties: list):
        self.name = name
        self.properties = properties
        self.children: list["FbxNode"] = []

    def find(self, name: str) -> "FbxNode | None":
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name: str) -> list["FbxNode"]:
        return [c for c in self.children if c.name == name]

    def __repr__(self):
        return f"FbxNode({self.name!r}, {len(self.properties)} props, {len(self.children)} children)"


def _read_node(buf: bytes, pos: int, use_64bit: bool) -> tuple["FbxNode | None", int]:
    """하나의 노드 레코드를 읽는다. 널 레코드(자식 목록의 끝)를 만나면
    (None, 그 다음 pos)를 반환한다."""
    if use_64bit:
        end_offset, num_properties, property_list_len = struct.unpack_from("<QQQ", buf, pos)
        pos += 24
    else:
        end_offset, num_properties, property_list_len = struct.unpack_from("<III", buf, pos)
        pos += 12

    if end_offset == 0:
        # 널 레코드(13 또는 25바이트, 헤더 필드는 이미 다 읽었으므로 남은
        # 패딩만 건너뛴다 — 1바이트 name_len(=0)까지 포함해서 이미 읽은
        # 필드 다음에 1바이트가 남음)
        pos += 1  # name_len(0)
        return None, pos

    name_len = buf[pos]
    pos += 1
    name = buf[pos : pos + name_len].decode("utf-8", errors="replace")
    pos += name_len

    props, pos = _read_properties(buf, pos, num_properties)
    node = FbxNode(name, props)

    # end_offset은 "이 노드 전체(자식 포함)가 끝나는 절대 위치"다. 지금
    # pos가 이미 거기 도달했으면 자식이 없는 것(리프 노드) — 아니면
    # end_offset 전까지 자식 노드들을 재귀적으로 읽는다.
    if pos < end_offset:
        while pos < end_offset:
            child, pos = _read_node(buf, pos, use_64bit)
            if child is None:
                break
            node.children.append(child)

    if pos != end_offset:
        raise FbxParseError(
            f"노드 {name!r} 파싱 후 위치 불일치: pos={pos} end_offset={end_offset}"
        )
    return node, pos


def parse_fbx(path: Path) -> tuple[list[FbxNode], int]:
    """FBX 바이너리 파일을 파싱해 (최상위 노드 리스트, 버전)을 반환한다."""
    buf = path.read_bytes()
    if buf[:23] != _MAGIC:
        raise FbxParseError(f"FBX 바이너리 매직 헤더 불일치 (ASCII FBX이거나 손상됨): {buf[:23]!r}")
    (version,) = struct.unpack_from("<I", buf, 23)
    use_64bit = version >= 7500
    pos = 27

    nodes = []
    # 파일 최상위도 "널 레코드로 끝나는 노드 시퀀스"와 같은 구조다.
    while pos < len(buf):
        node, pos = _read_node(buf, pos, use_64bit)
        if node is None:
            break
        nodes.append(node)
    return nodes, version


def extract_geometry(nodes: list[FbxNode]) -> list[dict]:
    """최상위 노드들에서 Objects/Geometry를 찾아 정점·폴리곤 정점 인덱스를
    뽑는다. 반환: [{"name", "num_vertices", "num_polygons"}]"""
    results = []
    for top in nodes:
        if top.name != "Objects":
            continue
        for geom in top.find_all("Geometry"):
            vertices_node = geom.find("Vertices")
            poly_idx_node = geom.find("PolygonVertexIndex")
            if vertices_node is None or poly_idx_node is None:
                continue
            vertices_flat = vertices_node.properties[0]
            poly_indices = poly_idx_node.properties[0]
            num_vertices = len(vertices_flat) // 3
            # PolygonVertexIndex: 각 폴리곤의 "마지막" 정점 인덱스는
            # 비트 NOT(~i)으로 저장돼 폴리곤 경계를 표시한다(FBX 바이너리
            # 포맷의 알려진 관례) — 음수 개수 = 폴리곤 개수.
            num_polygons = sum(1 for i in poly_indices if i < 0)
            results.append({
                "name": geom.properties[1] if len(geom.properties) > 1 else "",
                "num_vertices": num_vertices,
                "num_polygons": num_polygons,
            })
    return results


if __name__ == "__main__":
    path = Path(sys.argv[1])
    nodes, version = parse_fbx(path)
    print(f"FBX 버전: {version}")
    print(f"최상위 노드: {[n.name for n in nodes]}")
    geoms = extract_geometry(nodes)
    for g in geoms:
        print(f"Geometry {g['name']!r}: 정점 {g['num_vertices']}개, 폴리곤 {g['num_polygons']}개")
