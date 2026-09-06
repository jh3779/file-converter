"""확장자 없는/알 수 없는 영상의 콘텐츠 기반 감지 회귀 테스트."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import converters
from app.models import FileItem


_VIDEO_STREAM = {
    "index": 0,
    "codec_type": "video",
    "codec_name": "h264",
    "disposition": {"attached_pic": 0},
}


class TestContentBasedVideoDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _detect_patches(self, streams=None):
        return (
            patch.object(converters, "_VIDEO_AVAILABLE", True),
            patch("app.converters.video.find_ffprobe", return_value="ffprobe"),
            patch("app.converters.video._probe_streams", return_value=streams or [_VIDEO_STREAM]),
        )

    def test_filename_with_dot_number_suffix_detected_as_video(self):
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")
        p1, p2, p3 = self._detect_patches()
        with p1, p2, p3:
            self.assertEqual(converters.detect_source_format(src), "video")

    def test_extensionless_file_detected_as_video(self):
        src = self.tmp / "recording"
        src.write_bytes(b"fake")
        p1, p2, p3 = self._detect_patches()
        with p1, p2, p3:
            self.assertEqual(converters.detect_source_format(src), "video")

    def test_attached_picture_only_is_not_video(self):
        src = self.tmp / "album.bin"
        src.write_bytes(b"fake")
        cover = dict(_VIDEO_STREAM)
        cover["disposition"] = {"attached_pic": 1}
        p1, p2, p3 = self._detect_patches([cover])
        with p1, p2, p3:
            self.assertEqual(converters.detect_source_format(src), "bin")

    def test_file_item_normalizes_unknown_extension_to_video(self):
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")
        p1, p2, p3 = self._detect_patches()
        with p1, p2, p3:
            item = FileItem(id=1, source=src, source_fmt="06")
        self.assertEqual(item.source_fmt, "video")
        self.assertEqual(converters.targets_for(item.source_fmt), ["mp4"])

    def test_convert_preserves_full_original_name_for_detected_video(self):
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")
        produced = self.tmp / "26.09.mp4"

        def fake_convert(_src, _tmpdir):
            produced.write_bytes(b"mp4")
            return produced

        p1, p2, p3 = self._detect_patches()
        original = converters._DISPATCH.get(("video", "mp4"))
        converters._DISPATCH[("video", "mp4")] = fake_convert
        try:
            with p1, p2, p3:
                out = converters.convert(src, "mp4", self.tmp)
        finally:
            if original is None:
                converters._DISPATCH.pop(("video", "mp4"), None)
            else:
                converters._DISPATCH[("video", "mp4")] = original

        self.assertEqual(out.name, "26.09.06.mp4")
        self.assertTrue(out.exists())
        self.assertFalse(produced.exists())


if __name__ == "__main__":
    unittest.main()
