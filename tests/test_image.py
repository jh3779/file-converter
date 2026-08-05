"""이미지 포맷 변환 테스트 (JPG/PNG/BMP/GIF/WEBP/TIFF 상호 변환, Pillow).

핵심 검증: EXIF 회전 반영, 알파 채널→무알파 포맷 변환 시 흰 배경 합성,
애니메이션 이미지는 항상 첫 프레임만 사용(고지 필요).
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import converters
from app.converters.base import ConversionError
from app.converters.image import is_animated


class TestImageConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_jpg_to_png_roundtrip(self):
        src = self.tmp / "photo.jpg"
        Image.new("RGB", (20, 10), (0, 128, 255)).save(src)
        out = converters.convert(src, "png", self.tmp)
        self.assertTrue(out.exists())
        with Image.open(out) as im:
            self.assertEqual(im.format, "PNG")
            self.assertEqual(im.size, (20, 10))

    def test_transparent_png_to_jpg_composites_white_background(self):
        src = self.tmp / "logo.png"
        im = Image.new("RGBA", (4, 4), (255, 0, 0, 0))  # 완전 투명
        im.save(src)
        out = converters.convert(src, "jpg", self.tmp)
        with Image.open(out) as result:
            self.assertEqual(result.mode, "RGB")
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))

    def test_exif_rotation_applied(self):
        # EXIF Orientation=6은 시계 방향 90도 회전을 의미 — 가로 10x20 원본이
        # 회전 반영 후 세로 20x10으로 나와야 한다(옆으로 눕는 사진 방지).
        src = self.tmp / "rotated.jpg"
        im = Image.new("RGB", (20, 10), (10, 20, 30))
        exif = im.getexif()
        exif[0x0112] = 6
        im.save(src, exif=exif)
        out = converters.convert(src, "png", self.tmp)
        with Image.open(out) as result:
            self.assertEqual(result.size, (10, 20))

    def test_animated_gif_detected(self):
        src = self.tmp / "anim.gif"
        frames = [Image.new("RGB", (4, 4), (i * 50, 0, 0)) for i in range(3)]
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=50, loop=0)
        self.assertTrue(is_animated(src))

    def test_static_image_not_animated(self):
        src = self.tmp / "static.png"
        Image.new("RGB", (4, 4)).save(src)
        self.assertFalse(is_animated(src))

    def test_animated_gif_to_png_uses_first_frame_only(self):
        src = self.tmp / "anim.gif"
        frames = [Image.new("RGB", (4, 4), (i * 80, 0, 0)) for i in range(3)]
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=50, loop=0)
        out = converters.convert(src, "png", self.tmp)
        with Image.open(out) as result:
            self.assertEqual(result.convert("RGB").getpixel((0, 0)), (0, 0, 0))  # 첫 프레임 색

    def test_corrupted_image_rejected(self):
        src = self.tmp / "broken.png"
        src.write_bytes(b"not a real image")
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(src, "jpg", self.tmp)
        self.assertEqual(ctx.exception.key, "err.corrupted")

    def test_jpg_and_jpeg_excluded_from_each_others_targets(self):
        self.assertNotIn("jpg", converters.targets_for("jpeg"))
        self.assertNotIn("jpeg", converters.targets_for("jpg"))
        self.assertIn("png", converters.targets_for("jpg"))


if __name__ == "__main__":
    unittest.main()
