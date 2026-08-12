"""3D 모델 포맷 변환 테스트 (OBJ/STL/PLY/GLB/GLTF 상호 변환, trimesh).

핵심 검증: 형태(정점·면 개수, 부피)가 모든 포맷 조합에서 보존되는지,
STL로 갈 때 색상이 유실되는지(포맷 자체의 한계 — 재현 확인용).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    import trimesh
    _HAS_TRIMESH = True
except ImportError:
    _HAS_TRIMESH = False

from app import converters
from app.converters.base import ConversionError


@unittest.skipUnless(_HAS_TRIMESH, "trimesh 없음 — pip install trimesh")
class TestModel3DConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_box(self, path: Path):
        mesh = trimesh.creation.box(extents=[2, 3, 4])
        mesh.export(path)
        return mesh

    def test_obj_to_stl_preserves_geometry(self):
        src = self.tmp / "box.obj"
        original = self._make_box(src)
        out = converters.convert(src, "stl", self.tmp)
        self.assertTrue(out.exists())
        result = trimesh.load(out, force="mesh")
        self.assertEqual(len(result.vertices), len(original.vertices))
        self.assertEqual(len(result.faces), len(original.faces))
        self.assertAlmostEqual(result.volume, original.volume, places=2)

    def test_all_format_pairs_preserve_volume(self):
        exts = ("obj", "stl", "ply", "glb", "gltf")
        original = self._make_box(self.tmp / "box.obj")
        for src_ext in exts:
            src = self.tmp / f"box_src.{src_ext}"
            original.export(src)
            for dst_ext in exts:
                if src_ext == dst_ext:
                    continue
                with self.subTest(src=src_ext, dst=dst_ext):
                    out_dir = self.tmp / f"{src_ext}_to_{dst_ext}"
                    out_dir.mkdir()
                    out = converters.convert(src, dst_ext, out_dir)
                    result = trimesh.load(out, force="mesh")
                    self.assertAlmostEqual(result.volume, original.volume, places=1)
                    self.assertEqual(len(result.faces), len(original.faces))

    def test_stl_target_loses_vertex_color(self):
        """STL 포맷 자체가 색상을 담지 못한다 — 다른 포맷(PLY)에 있던
        빨간색이 STL로 변환하면 사라지는지 직접 확인(note.stl_no_color의
        근거)."""
        import numpy as np

        mesh = trimesh.creation.box(extents=[1, 1, 1])
        mesh.visual.vertex_colors = np.tile([255, 0, 0, 255], (len(mesh.vertices), 1))
        src = self.tmp / "red.ply"
        mesh.export(src)

        out = converters.convert(src, "stl", self.tmp)
        result = trimesh.load(out, force="mesh")
        color = result.visual.vertex_colors[0]
        self.assertFalse(list(color[:3]) == [255, 0, 0], "STL에 색상이 남아있으면 안 됨(포맷 자체가 미지원)")

    def test_ply_target_keeps_vertex_color(self):
        import numpy as np

        mesh = trimesh.creation.box(extents=[1, 1, 1])
        mesh.visual.vertex_colors = np.tile([255, 0, 0, 255], (len(mesh.vertices), 1))
        src = self.tmp / "red.obj"
        mesh.export(src)

        out = converters.convert(src, "ply", self.tmp)
        result = trimesh.load(out, force="mesh")
        color = result.visual.vertex_colors[0]
        self.assertEqual(list(color), [255, 0, 0, 255])

    def test_corrupted_model_rejected(self):
        src = self.tmp / "broken.obj"
        src.write_bytes(b"not a real 3d model")
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(src, "stl", self.tmp)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_self_conversion_not_exposed(self):
        self.assertNotIn("obj", converters.targets_for("obj"))
        self.assertIn("stl", converters.targets_for("obj"))

    def test_gltf_output_survives_finalize_and_tmpdir_deletion(self):
        """자동 PR 리뷰 지적(재현 확인 후 수정): .gltf(텍스트 JSON) 내보내기는
        기본값으로 정점/인덱스 버퍼를 별도 .bin 파일로 만든다 — 이 앱의
        실제 파이프라인(app/output.py의 finalize()가 convert()가 돌려준
        파일 하나만 옮기고, app/workers.py가 남은 임시 폴더를 통째로 지움,
        REQ-F-008/app/output.py)을 그대로 흉내내면(단일 파일만 다른 폴더로
        옮기고 원래 tmpdir을 삭제) .bin이 사라져 깨진 파일이 됐었다.
        embed_buffers=True로 고쳐 단일 파일이 되는지 확인한다."""
        for src_ext in ("obj", "stl", "ply", "glb"):
            with self.subTest(src=src_ext):
                convert_tmp = Path(tempfile.mkdtemp())
                src = convert_tmp / f"box.{src_ext}"
                original = self._make_box(src)
                out = converters.convert(src, "gltf", convert_tmp)

                # finalize()처럼 결과 파일 "하나만" 별도 위치로 옮긴다.
                final_dir = Path(tempfile.mkdtemp())
                final_path = final_dir / out.name
                out.rename(final_path)
                # workers.py처럼 원래 임시 폴더를 통째로 지운다(.bin이
                # 남아있었다면 여기서 함께 사라짐).
                shutil.rmtree(convert_tmp, ignore_errors=True)

                result = trimesh.load(final_path, force="mesh")
                self.assertEqual(len(result.faces), len(original.faces))
                self.assertAlmostEqual(result.volume, original.volume, places=1)
                shutil.rmtree(final_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
