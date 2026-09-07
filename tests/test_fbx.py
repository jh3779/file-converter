"""FBX(Autodesk) 3D 모델 읽기 전용 지원 테스트 — REQ-F-020 확장(DEC-069 · OQ-007).

실제 Maya/Blender FBX 익스포트 픽스처(`tests/fixtures/fbx/`, 출처·라이선스는
같은 폴더의 README.md 참고)로 다음을 검증한다:
- 비압축 FBX 7400/7500 큐브 파싱(정점·삼각형화 후 면 개수)
- zlib 압축 배열 실사용(Blender Suzanne, 참조 OBJ와 좌표 대조)
- Z-up→Y-up 축 정규화가 실제로 축을 바꾸는지
- Connections 기반 필터링(Light/Camera 제외, Cube+Cone만 포함)
- FBX 6.x(지원 범위 밖)가 크래시가 아니라 명확한 err.corrupted로 실패하는지
- `converters.convert()` 전체 파이프라인을 통한 왕복 검증(다른 3D 포맷
  테스트, `tests/test_model3d.py`와 같은 패턴)
- `supported`/`targets_for`가 읽기 전용 계약(FBX는 소스로만, 대상으로는
  노출 안 됨)을 지키는지

실제 파일로 재현하기 어려운 손상 파일 엣지 케이스(Objects/Connections
노드 누락, 빈 프로퍼티 배열, 범위를 벗어난 폴리곤 인덱스)는 `fbx.py`의
내부 헬퍼(`_FbxNode`·`_extract_from_nodes`)로 노드 트리를 직접 구성해
검증한다 — 이런 조건의 손상 파일을 바이너리로 새로 인코딩하는 것보다
훨씬 안정적이고 읽기 쉽다(`fbx.py`의 `_extract_from_nodes` docstring 참고).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import converters
from app.converters import fbx
from app.converters.base import ConversionError

try:
    import trimesh
    _HAS_TRIMESH = True
except ImportError:
    _HAS_TRIMESH = False

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "fbx"

CUBE_7400 = FIXTURES / "maya_cube_7400_binary.fbx"
CUBE_7500 = FIXTURES / "maya_cube_7500_binary.fbx"
CUBE_6100 = FIXTURES / "maya_cube_6100_binary.fbx"
SUZANNE = FIXTURES / "blender_282_suzanne_7400_binary.fbx"
SUZANNE_OBJ = FIXTURES / "blender_282_suzanne.obj"
ZUP = FIXTURES / "blender_340_z_up_7400_binary.fbx"


def _read_obj_vertices(path: Path):
    verts = []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append(tuple(float(x) for x in parts[1:4]))
    return verts


def _geom(node_id, flat_vertices, poly_indices):
    """테스트용 최소 Geometry 노드 트리(`_extract_from_nodes`가 보는
    모양만 흉내낸다 — Vertices/PolygonVertexIndex 프로퍼티는 실제 파서가
    이미 배열을 다 풀어놓은 뒤의 형태(파이썬 list)와 동일)."""
    g = fbx._FbxNode("Geometry", [node_id, "Geometry", "Mesh"])
    vertices_node = fbx._FbxNode("Vertices", [list(flat_vertices)])
    poly_node = fbx._FbxNode("PolygonVertexIndex", [list(poly_indices)])
    g.children = [vertices_node, poly_node]
    return g


def _model(node_id):
    return fbx._FbxNode("Model", [node_id, "Model::Test", "Mesh"])


def _objects(children):
    node = fbx._FbxNode("Objects", [])
    node.children = list(children)
    return node


def _connections(pairs):
    node = fbx._FbxNode("Connections", [])
    node.children = [fbx._FbxNode("C", ["OO", src, dst]) for src, dst in pairs]
    return node


def _global_settings(**axis_overrides):
    """`_axis_matrix`가 읽는 GlobalSettings/Properties70 노드 트리를 만든다
    (fbx.py L183-193 참고) — CoordAxis/UpAxis/FrontAxis(+부호)를
    axis_overrides로 덮어써 정상/축퇴 조합을 모두 테스트할 수 있게 한다."""
    p70 = fbx._FbxNode("Properties70", [])
    p70.children = [fbx._FbxNode("P", [name, value]) for name, value in axis_overrides.items()]
    gs = fbx._FbxNode("GlobalSettings", [])
    gs.children = [p70]
    return gs


# 삼각형 하나(정점 3개) — 로우레벨 노드 트리 테스트용 최소 지오메트리.
# PolygonVertexIndex의 마지막 인덱스는 비트 NOT으로 인코딩(FBX 관례,
# fbx.py L233 부근 `_triangulate_fan` 관련 로직과 동일 규칙).
_TRI_VERTS = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
_TRI_POLY = (0, 1, ~2)


@unittest.skipUnless(FIXTURES.exists(), "tests/fixtures/fbx 픽스처 없음")
class TestFbxParsing(unittest.TestCase):
    """실제 Maya/Blender FBX 익스포트 픽스처 기반 검증."""

    def test_cube_7400_binary_parses_correctly(self):
        vertices, faces = fbx.parse_geometry(CUBE_7400)
        self.assertEqual(len(vertices), 8)
        # 4각형 폴리곤 6개가 fan triangulation으로 삼각형 12개가 됨
        self.assertEqual(len(faces), 12)

    def test_cube_7500_binary_parses_correctly(self):
        """7500은 4바이트 대신 8바이트 오프셋 필드를 쓰는 버전 — 같은
        큐브를 파싱한 결과가 7400과 정확히 같아야 한다."""
        vertices, faces = fbx.parse_geometry(CUBE_7500)
        self.assertEqual(len(vertices), 8)
        self.assertEqual(len(faces), 12)

    def test_cube_7400_and_7500_produce_identical_vertex_set(self):
        v1, _ = fbx.parse_geometry(CUBE_7400)
        v2, _ = fbx.parse_geometry(CUBE_7500)
        self.assertEqual(sorted(v1), sorted(v2))

    def test_cube_6100_binary_rejected_as_corrupted_not_crash(self):
        """FBX 6.x는 Geometry가 `Objects` 아래 별도 오브젝트로 없는(Model에
        직접 내장되는) 다른 오브젝트 모델을 써서 지원 범위 밖이다 —
        인터프리터가 죽는 대신 명확한 ConversionError(err.corrupted)로
        실패해야 한다."""
        with self.assertRaises(ConversionError) as ctx:
            fbx.parse_geometry(CUBE_6100)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_suzanne_compressed_matches_reference_obj(self):
        """zlib 압축 배열 실사용 검증(Blender 내보내기는 흔히 압축을
        씀) — 참조 OBJ와 정점 개수·좌표를 대조한다.

        이 fixture는 GlobalSettings의 축 설정이 이미 표준(Maya 기본,
        `_axis_matrix`가 항등행렬을 반환)이라 우리 파서 출력은 원본 FBX
        저장값 그대로 Y-up이다. 반면 참조 OBJ(`blender_282_suzanne.obj`)는
        Blender 내부의 원시 Z-up 좌표를 축 변환 없이 그대로 담고 있다
        (직접 대조로 확인) — 그래서 대응 관계가 항등이 아니라
        `(x, y, z)_ours == (x, -z, y)_ref`다. 이 관계가 507개 정점 전부에서
        성립함을 사전에 전수 확인했다(공차 안에서 507/507 일치)."""
        vertices, faces = fbx.parse_geometry(SUZANNE)
        ref = _read_obj_vertices(SUZANNE_OBJ)
        self.assertEqual(len(vertices), 507)
        self.assertEqual(len(vertices), len(ref))
        # 폴리곤 500개(대부분 4각형) → fan triangulation 후 삼각형이 더 많다
        self.assertGreater(len(faces), 500)
        for (x, y, z), (rx, ry, rz) in zip(vertices, ref):
            self.assertAlmostEqual(x, rx, places=4)
            self.assertAlmostEqual(y, -rz, places=4)
            self.assertAlmostEqual(z, ry, places=4)

    def test_z_up_axis_actually_normalized_to_y_up(self):
        """Z-up→Y-up 축 정규화가 이름만 그런 게 아니라 실제로 축을
        바꾸는지 직접 검증한다 — 원본 FBX 저장값에서 Z축이었던 성분이
        변환 결과에서는 Y축 위치에 나타나야 한다."""
        data = ZUP.read_bytes()
        nodes, _version = fbx._parse(data)
        matrix, _det = fbx._axis_matrix(nodes)
        identity = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        # 항등행렬이면 애초에 "실제로 축을 바꿨는지"를 검증할 수 없다 —
        # 이 fixture가 실제로 Z-up(항등이 아님)이라는 전제부터 확인한다.
        self.assertNotEqual(matrix, identity)

        objs = next(n for n in nodes if n.name == "Objects")
        geom = objs.find_all("Geometry")[0]
        raw = geom.find("Vertices").properties[0]
        raw_x, raw_y, raw_z = raw[0], raw[1], raw[2]
        _conv_x, conv_y, _conv_z = fbx._apply_axis(matrix, raw_x, raw_y, raw_z)
        # 원본의 Z 성분(raw_z)이 변환 후 Y 위치(conv_y)에 나타난다(부호는
        # UpAxisSign에 따라 달라질 수 있어 절대값으로 비교).
        self.assertAlmostEqual(abs(conv_y), abs(raw_z), places=6)
        # 그리고 raw_z 자체는 0이 아니어야 이 검증이 의미가 있다(우연한
        # 일치 방지).
        self.assertNotAlmostEqual(raw_z, 0.0)

    def test_z_up_scene_connections_filtering_combines_only_connected_geometry(self):
        """씬에 Cube+Light+Camera+Cone이 있는데 Light/Camera는 Geometry
        자체가 없어 자동으로 제외되고, Cube(정점 8)+Cone(정점 9) 두
        Geometry만 Connections로 실제 Model에 연결된 것으로 확인돼
        합쳐진 17개 정점이 나와야 한다."""
        vertices, faces = fbx.parse_geometry(ZUP)
        self.assertEqual(len(vertices), 17)
        self.assertGreater(len(faces), 0)

        data = ZUP.read_bytes()
        nodes, _version = fbx._parse(data)
        objs = next(n for n in nodes if n.name == "Objects")
        # FBX는 오브젝트 이름을 "Name\x00\x01ClassName" 한 문자열 프로퍼티에
        # 같이 담는다(실측 확인) — "\x00\x01" 앞부분만 이름으로 비교한다.
        geom_names = {g.properties[1].split("\x00\x01")[0] for g in objs.find_all("Geometry") if len(g.properties) > 1}
        model_names = {m.properties[1].split("\x00\x01")[0] for m in objs.find_all("Model") if len(m.properties) > 1}
        # 씬 자체에는 Light/Camera Model이 있지만 Geometry는 없다는 전제 확인
        self.assertIn("Light", model_names)
        self.assertIn("Camera", model_names)
        self.assertEqual(geom_names, {"Cube", "Cone"})
        self.assertNotIn("Light", geom_names)
        self.assertNotIn("Camera", geom_names)


@unittest.skipUnless(_HAS_TRIMESH, "trimesh 없음 — pip install trimesh")
class TestFbxConvertPipeline(unittest.TestCase):
    """`converters.convert()` 전체 파이프라인 왕복 검증(tests/test_model3d.py와
    같은 패턴) — FBX를 실제로 대상 포맷들로 변환해 trimesh로 재로드했을 때
    정점·면 개수가 일치하는지 확인한다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cube_round_trip_to_all_targets(self):
        vertices, faces = fbx.parse_geometry(CUBE_7400)
        for target_ext in ("obj", "stl", "ply", "glb", "gltf"):
            with self.subTest(target=target_ext):
                out_dir = self.tmp / target_ext
                out_dir.mkdir()
                out = converters.convert(CUBE_7400, target_ext, out_dir)
                self.assertTrue(out.exists())
                result = trimesh.load(out, force="mesh")
                self.assertEqual(len(result.vertices), len(vertices))
                self.assertEqual(len(result.faces), len(faces))

    def test_suzanne_round_trip_to_glb(self):
        """glb(바이너리, 인덱스 버퍼 그대로 보존)로 왕복하면 정점·면
        개수가 정확히 일치해야 한다. obj/stl/ply처럼 텍스트나 비인덱스
        (triangle-soup) 포맷은 trimesh가 재로드 시 기본으로 수행하는
        정점 병합(근접 좌표 중복 제거, `force="mesh"`의 기본 `process=True`)
        때문에 507개 중 2개가 505개로 줄어드는 현상을 직접 확인했다(2개
        정점 쌍이 소수점 6자리로 반올림하면 우연히 같아짐) — 우리 FBX
        파서가 정점을 잘못 만든 게 아니라 trimesh의 재로드 처리 특성이라,
        인덱스를 그대로 보존하는 바이너리 포맷(glb)으로 정확한 왕복을
        검증한다. 위상(면 개수)은 모든 대상 포맷에서 동일하게 보존됨은
        `test_cube_round_trip_to_all_targets`에서 이미 확인."""
        vertices, faces = fbx.parse_geometry(SUZANNE)
        out = converters.convert(SUZANNE, "glb", self.tmp)
        result = trimesh.load(out, force="mesh")
        self.assertEqual(len(result.vertices), len(vertices))
        self.assertEqual(len(result.faces), len(faces))

    def test_suzanne_round_trip_to_obj_preserves_face_topology(self):
        """텍스트 포맷(obj)으로 왕복해도 면(삼각형) 개수, 즉 형태의
        위상 구조는 그대로 보존돼야 한다(정점 개수는 위 테스트의 설명대로
        근접 좌표 병합으로 살짝 줄 수 있음)."""
        _vertices, faces = fbx.parse_geometry(SUZANNE)
        out = converters.convert(SUZANNE, "obj", self.tmp)
        result = trimesh.load(out, force="mesh")
        self.assertEqual(len(result.faces), len(faces))

    def test_z_up_scene_round_trip_to_stl(self):
        vertices, faces = fbx.parse_geometry(ZUP)
        out = converters.convert(ZUP, "stl", self.tmp)
        result = trimesh.load(out, force="mesh")
        self.assertEqual(len(result.vertices), len(vertices))
        self.assertEqual(len(result.faces), len(faces))

    def test_cube_6100_conversion_fails_cleanly(self):
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(CUBE_6100, "obj", self.tmp)
        self.assertEqual(ctx.exception.key, "err.corrupted")


class TestFbxRegistry(unittest.TestCase):
    """읽기 전용 계약 — FBX는 소스로만 노출되고 대상으로는 절대 노출되지
    않아야 한다(단방향)."""

    def test_fbx_supported_as_source(self):
        self.assertTrue(converters.supported("fbx"))

    def test_fbx_targets_are_exactly_five_model_formats(self):
        self.assertEqual(sorted(converters.targets_for("fbx")), ["glb", "gltf", "obj", "ply", "stl"])

    def test_fbx_not_exposed_as_target_of_other_model_formats(self):
        for src in ("obj", "stl", "ply", "glb", "gltf"):
            with self.subTest(src=src):
                self.assertNotIn("fbx", converters.targets_for(src))


class TestFbxRobustness(unittest.TestCase):
    """실제 fixture로 재현하기 어려운 손상 파일 엣지 케이스 — 파싱된 노드
    트리 레벨(`_FbxNode`)을 직접 구성해 `_extract_from_nodes`로 검증한다."""

    def test_missing_objects_node_raises_corrupted(self):
        with self.assertRaises(ConversionError) as ctx:
            fbx._extract_from_nodes([])  # Objects 노드가 아예 없는 최상위 목록
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_missing_connections_node_includes_all_geometry_safely(self):
        """Connections 노드가 아예 없으면 어느 Geometry가 실제로 쓰이는지
        판단할 근거가 없으므로, 안전하게 모든 Geometry를 포함해야 한다
        (조용한 데이터 유실 방지가 압도적으로 우선)."""
        g1 = _geom(100, _TRI_VERTS, _TRI_POLY)
        g2 = _geom(200, _TRI_VERTS, _TRI_POLY)
        nodes = [_objects([g1, g2, _model(101)])]  # Connections 노드 없음
        vertices, faces = fbx._extract_from_nodes(nodes)
        self.assertEqual(len(vertices), 6)  # 삼각형 2개 분량
        self.assertEqual(len(faces), 2)

    def test_empty_vertex_array_geometry_contributes_nothing_but_does_not_crash(self):
        """빈 Vertices 배열(array_length=0)을 가진 Geometry가 있어도
        크래시하지 않고, 그 Geometry는 그냥 기여분 0으로 건너뛰고 다른
        유효한 Geometry는 정상 반영돼야 한다."""
        g_empty = _geom(300, (), ())
        g_valid = _geom(100, _TRI_VERTS, _TRI_POLY)
        nodes = [_objects([g_empty, g_valid]), _connections([(100, 101), (300, 101)]), ]
        # Connections에 Model(101)이 실제로 없어도(연결 대상 누락) 안전한
        # 기본값(모든 Geometry 포함)으로 fallback해야 하므로 Model 없이도 확인.
        vertices, faces = fbx._extract_from_nodes(nodes)
        self.assertEqual(len(vertices), 3)
        self.assertEqual(len(faces), 1)

    def test_all_empty_geometry_raises_corrupted(self):
        g_empty = _geom(300, (), ())
        nodes = [_objects([g_empty])]
        with self.assertRaises(ConversionError) as ctx:
            fbx._extract_from_nodes(nodes)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_no_geometry_objects_at_all_raises_corrupted(self):
        """Objects 노드는 있지만 그 아래 Geometry가 하나도 없는 경우
        (FBX 6.x 등)도 명확히 실패해야 한다."""
        nodes = [_objects([_model(101)])]
        with self.assertRaises(ConversionError) as ctx:
            fbx._extract_from_nodes(nodes)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_out_of_range_polygon_index_raises_corrupted(self):
        """PolygonVertexIndex가 그 Geometry의 Vertices 범위를 벗어난
        인덱스를 담고 있는(손상된) 경우 — 검증 없이 넘기면 뒤 파이프라인
        (trimesh export)에 깨진 인덱스가 조용히 흘러갈 위험이 있어, 여기서
        명확히 실패해야 한다."""
        bad_poly = (0, 1, ~5)  # 정점은 3개(인덱스 0~2)뿐인데 5를 참조
        g_bad = _geom(400, _TRI_VERTS, bad_poly)
        nodes = [_objects([g_bad])]
        with self.assertRaises(ConversionError) as ctx:
            fbx._extract_from_nodes(nodes)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_degenerate_axis_settings_raise_corrupted_instead_of_silent_distortion(self):
        """GlobalSettings의 CoordAxis/UpAxis가 서로 겹치면(둘 다 0 = X축)
        `_axis_matrix`가 특이(det=0) 행렬을 만들어 한 축이 조용히 다른
        축과 겹쳐 찌그러진다 — 크래시나 err.corrupted 없이 찌그러진
        메시가 그대로 export되면 안 되므로, 여기서 명확히 실패해야 한다
        (review-verify-agent 지적 사항, fbx.py L258 부근 방어 코드)."""
        gs = _global_settings(CoordAxis=0, CoordAxisSign=1, UpAxis=0, UpAxisSign=1, FrontAxis=2, FrontAxisSign=1)
        g = _geom(100, _TRI_VERTS, _TRI_POLY)
        nodes = [gs, _objects([g])]
        with self.assertRaises(ConversionError) as ctx:
            fbx._extract_from_nodes(nodes)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_normal_axis_settings_do_not_raise(self):
        """대조군 — 표준(비축퇴) 축 설정이면 위 방어 코드가 오탐하지 않고
        정상적으로 변환돼야 한다."""
        gs = _global_settings(CoordAxis=0, CoordAxisSign=1, UpAxis=1, UpAxisSign=1, FrontAxis=2, FrontAxisSign=1)
        g = _geom(100, _TRI_VERTS, _TRI_POLY)
        nodes = [gs, _objects([g])]
        vertices, faces = fbx._extract_from_nodes(nodes)
        self.assertEqual(len(vertices), 3)
        self.assertEqual(len(faces), 1)

    def test_geometry_without_id_is_included_by_default(self):
        """Geometry 노드에 ID 프로퍼티 자체가 없는(비정상이지만 방어적으로
        다뤄야 하는) 경우, `if geom.properties and ...`의 단락 평가로
        무조건 포함되는지 확인(안전한 기본값)."""
        g_no_id = fbx._FbxNode("Geometry", [])  # properties가 완전히 빈 리스트
        g_no_id.children = [
            fbx._FbxNode("Vertices", [list(_TRI_VERTS)]),
            fbx._FbxNode("PolygonVertexIndex", [list(_TRI_POLY)]),
        ]
        nodes = [_objects([g_no_id])]
        vertices, faces = fbx._extract_from_nodes(nodes)
        self.assertEqual(len(vertices), 3)
        self.assertEqual(len(faces), 1)


if __name__ == "__main__":
    unittest.main()
