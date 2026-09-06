"""확장자 없는/알 수 없는 영상의 콘텐츠 기반 감지 회귀 테스트."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import converters
from app.converters import video
from app.models import FileItem
from app.output import finalize


_H264_STREAM = {
    "index": 0,
    "codec_type": "video",
    "codec_name": "h264",
    "disposition": {"attached_pic": 0},
}


class TestContentBasedVideoDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dotted_numeric_suffix_is_detected_by_content(self):
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")
        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", return_value=True):
            self.assertTrue(converters.is_content_detected_video(src))
            self.assertEqual(converters.targets_for_source(src), ["mp4"])
            item = FileItem(id=1, source=src, source_fmt="06")
            self.assertEqual(converters.targets_for(item.source_fmt), ["mp4"])
        self.assertEqual(item.source_fmt, converters.content_video_key())

    def test_extensionless_file_is_detected_by_content(self):
        src = self.tmp / "recording"
        src.write_bytes(b"fake")
        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", return_value=True):
            item = FileItem(id=1, source=src, source_fmt="")
        self.assertEqual(item.source_fmt, converters.content_video_key())

    def test_real_dot_video_extension_does_not_bypass_content_validation(self):
        src = self.tmp / "clip.video"
        src.write_bytes(b"not-video")
        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", return_value=False):
            item = FileItem(id=1, source=src, source_fmt="video")
            self.assertFalse(converters.supported_source(src))
        self.assertEqual(item.source_fmt, "video")
        self.assertFalse(converters.supported("video"))
        self.assertEqual(converters.targets_for("video"), [])

    def test_attached_picture_only_is_not_convertible_video(self):
        cover = dict(_H264_STREAM)
        cover["disposition"] = {"attached_pic": 1}
        self.assertFalse(video.streams_convertible_to_mp4([cover], ffmpeg="ffmpeg"))

    def test_unsupported_codec_not_exposed_without_fallback_encoder(self):
        vp9 = dict(_H264_STREAM)
        vp9["codec_name"] = "vp9"
        with patch("app.converters.video._fallback_video_encoder_available", return_value=False):
            self.assertFalse(video.streams_convertible_to_mp4([vp9], ffmpeg="ffmpeg"))

    def test_safe_codec_is_exposed_without_reencode_fallback(self):
        with patch("app.converters.video._fallback_video_encoder_available", return_value=False):
            self.assertTrue(video.streams_convertible_to_mp4([_H264_STREAM], ffmpeg="ffmpeg"))

    def test_finalize_preserves_full_original_name_for_detected_video(self):
        source = self.tmp / "26.09.06"
        source.write_bytes(b"source")
        temp_dir = self.tmp / "temp"
        temp_dir.mkdir()
        produced = temp_dir / "26.09.mp4"
        produced.write_bytes(b"mp4")

        out, renamed = finalize(produced, source, "mp4", stem=source.name)

        self.assertEqual(out.name, "26.09.06.mp4")
        self.assertTrue(out.exists())
        self.assertFalse(renamed)

    def test_convert_routes_valid_unknown_extension_to_video_converter(self):
        src = self.tmp / "26.09.06"
        src.write_bytes(b"fake")
        produced = self.tmp / "26.09.mp4"
        with patch.object(converters, "_VIDEO_AVAILABLE", True), \
             patch("app.converters.video.can_convert_to_mp4", return_value=True), \
             patch("app.converters.video.video_to_mp4", return_value=produced) as convert_mock:
            out = converters.convert(src, "mp4", self.tmp)
        self.assertEqual(out, produced)
        convert_mock.assert_called_once_with(src, self.tmp)


if __name__ == "__main__":
    unittest.main()
