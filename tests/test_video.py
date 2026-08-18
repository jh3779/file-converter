"""영상→MP4 변환 테스트 (DEC-024) — ffmpeg 없으면 스킵.

핵심 검증: H.264/HEVC 영상은 무손실 스트림 카피, 그 외 코덱은 명시적으로
거부(ffmpeg가 exit 0으로 "성공"해도 MP4 표준에 안 맞는 조합을 만들 수
있어 exit code만으로 판단하면 안 된다는 걸 재현 확인 후 반영), AAC가
아닌 오디오는 ffmpeg 내장 AAC로만 재인코딩.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app import converters
from app.converters import video
from app.converters.base import ConversionError

def _detect_test_fixture_support() -> bool:
    """ffmpeg/ffprobe 존재만으로는 부족하다 — 테스트 픽스처(가짜 영상) 생성에
    libx264가 필요한데, 배포용으로 번들하는 LGPL 빌드에는 라이선스상 없다
    (DEC-024). CI의 ubuntu 러너에 어떤 ffmpeg가 미리 깔려 있는지 보장이 없어,
    실제로 인코더가 있는지 확인하고 없으면 조용히 스킵한다(하드 실패 방지) —
    이건 우리 변환 코드가 요구하는 게 아니라 테스트 픽스처 준비용 제약이다."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return False
    try:
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                               capture_output=True, timeout=10, text=True)
    except Exception:
        return False
    return "libx264" in proc.stdout


_HAS_FFMPEG = _detect_test_fixture_support()


def _detect_h264_mf_support() -> bool:
    """DEC-060: 앱이 실제로 쓸 ffmpeg(video.find_ffmpeg() — 번들 엔진 우선,
    없으면 시스템)에 h264_mf(Windows Media Foundation)가 있는지 — 테스트
    픽스처용 시스템 ffmpeg(_HAS_FFMPEG)와는 별개 질문이다. Windows에서만
    존재하고, 그 중에서도 Media Foundation 컴포넌트가 있는 빌드·환경에서만
    보인다."""
    ffmpeg = video.find_ffmpeg()
    if ffmpeg is None:
        return False
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-encoders"],
                               capture_output=True, timeout=10, text=True)
    except Exception:
        return False
    return "h264_mf" in proc.stdout


_HAS_H264_MF = _detect_h264_mf_support()


def _make_clip(path: Path, video_codec: str, audio_codec: str | None = None, duration: int = 1):
    cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi",
           "-i", f"testsrc=duration={duration}:size=160x120:rate=10"]
    if audio_codec:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}"]
    cmd += ["-c:v", video_codec]
    if audio_codec:
        cmd += ["-c:a", audio_codec]
    else:
        cmd += ["-an"]
    cmd.append(str(path))
    subprocess.run(cmd, capture_output=True, check=True, timeout=30)


class TestVideoTargetsPlatformGating(unittest.TestCase):
    """DEC-029: FFmpeg를 번들하지 않는 배포판(예: macOS v1)에서는 영상
    확장자가 TARGETS에서 아예 빠져야 한다 — "재설치하세요"라는 엉뚱한
    오류 대신 애초에 지원 안 하는 형식으로 자연스럽게 처리하기 위함."""

    def _reload_with_find_ffmpeg(self, return_value):
        import importlib
        from unittest.mock import patch
        with patch("app.converters.video.find_ffmpeg", return_value=return_value):
            import app.converters as converters_mod
            importlib.reload(converters_mod)
            return converters_mod

    def tearDown(self):
        import importlib
        import app.converters as converters_mod
        importlib.reload(converters_mod)  # 실제 환경 기준으로 되돌림

    def test_video_hidden_when_ffmpeg_unavailable(self):
        mod = self._reload_with_find_ffmpeg(None)
        self.assertFalse(mod.supported("avi"))
        self.assertEqual(mod.targets_for("mov"), [])

    def test_video_exposed_when_ffmpeg_available(self):
        mod = self._reload_with_find_ffmpeg("/usr/bin/ffmpeg")
        self.assertTrue(mod.supported("avi"))
        self.assertEqual(mod.targets_for("mov"), ["mp4"])


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg/ffprobe 없음 — 로컬/Windows CI에서만 실행")
class TestVideoToMp4(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _probe(self, path: Path) -> list[dict]:
        import json
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, timeout=10)
        return json.loads(proc.stdout)["streams"]

    def test_h264_aac_full_copy_lossless(self):
        """가장 흔한 케이스(H.264+AAC) — 영상·오디오 둘 다 그대로 복사, 무손실."""
        src = self.tmp / "clip.mov"
        _make_clip(src, "libx264", "aac")
        out = converters.convert(src, "mp4", self.tmp)
        self.assertTrue(out.exists())

        # 영상 스트림 MD5가 원본과 완전히 같아야 함(재인코딩 안 됐다는 증거)
        def video_md5(path):
            md5_file = self.tmp / f"{path.stem}.md5"
            subprocess.run(["ffmpeg", "-y", "-i", str(path), "-f", "md5", "-c:v", "copy", "-an",
                             str(md5_file)], capture_output=True, timeout=10)
            return md5_file.read_text()

        self.assertEqual(video_md5(src), video_md5(out))
        streams = self._probe(out)
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"] == "video"), "h264")
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"] == "audio"), "aac")

    def test_h264_ac3_audio_reencoded_video_kept(self):
        """영상은 카피, 오디오만(AC3→AAC) 재인코딩되는지."""
        src = self.tmp / "clip.mkv"
        _make_clip(src, "libx264", "ac3")
        out = converters.convert(src, "mp4", self.tmp)
        streams = self._probe(out)
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"] == "video"), "h264")
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"] == "audio"), "aac")

    def test_silent_video_no_audio_stream(self):
        src = self.tmp / "clip.mov"
        _make_clip(src, "libx264", audio_codec=None)
        out = converters.convert(src, "mp4", self.tmp)
        streams = self._probe(out)
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["codec_type"], "video")

    @unittest.skipIf(_HAS_H264_MF, "h264_mf 있음 — 재인코딩 성공 경로는 아래 별도 테스트로 검증")
    def test_unsupported_video_codec_rejected_without_fallback_encoder(self):
        """DEC-024: h264_mf(DEC-060 재인코딩 폴백)가 없는 환경(비Windows 등)
        에서는 H.264/HEVC 외 코덱을 명시적으로 거부해야 한다(ffmpeg 자체는
        exit 0으로 "성공"할 수 있어 exit code만으로 판단하면 안 됨)."""
        src = self.tmp / "clip.mkv"  # 컨테이너는 지원 목록에 있어야 video_to_mp4 로직까지 도달함
        _make_clip(src, "mpeg2video", audio_codec=None)
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(src, "mp4", self.tmp)
        self.assertEqual(ctx.exception.key, "err.video_codec_unsupported")

    @unittest.skipUnless(_HAS_H264_MF, "h264_mf 없음 — Windows(+Media Foundation)에서만 실행")
    def test_unsupported_video_codec_reencoded_via_fallback(self):
        """DEC-060: h264_mf가 있는 환경(Windows)에서는 H.264/HEVC 외 코덱도
        거부하지 않고 h264_mf로 재인코딩해 성공해야 한다."""
        src = self.tmp / "clip.mkv"
        _make_clip(src, "mpeg2video", audio_codec=None)
        out = converters.convert(src, "mp4", self.tmp)
        self.assertTrue(out.exists())
        streams = self._probe(out)
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"] == "video"), "h264")

    def test_cover_art_before_video_stream_not_selected(self):
        """커버 아트(첨부 이미지)가 실제 영상보다 앞선 스트림이어도 영상은
        여전히 h264로 선택돼야 함(코드 리뷰 지적: "0:v:0" 지정자는 첨부
        이미지도 세므로 절대 인덱스로 매핑해야 함)."""
        clip = self.tmp / "clip.mov"
        cover = self.tmp / "cover.jpg"
        src = self.tmp / "with_cover.mkv"
        _make_clip(clip, "libx264", "aac")
        subprocess.run(["ffmpeg", "-hide_banner", "-y", "-f", "lavfi",
                         "-i", "color=c=red:s=32x32", "-frames:v", "1", str(cover)],
                        capture_output=True, check=True, timeout=15)
        subprocess.run(["ffmpeg", "-hide_banner", "-y",
                         "-i", str(cover), "-i", str(clip),
                         "-map", "0:v", "-map", "1:v", "-map", "1:a",
                         "-c:v:0", "mjpeg", "-disposition:v:0", "attached_pic",
                         "-c:v:1", "copy", "-c:a", "copy", str(src)],
                        capture_output=True, check=True, timeout=15)
        out = converters.convert(src, "mp4", self.tmp)
        streams = self._probe(out)
        video = next(s for s in streams if s["codec_type"] == "video")
        self.assertEqual(video["codec_name"], "h264")

    def test_multiple_audio_tracks_preserved(self):
        """다국어/해설 등 다중 오디오 트랙이 있어도 전부 보존돼야 함
        (코드 리뷰 지적: 기존엔 첫 트랙만 남기고 조용히 삭제했음). 트랙별로
        AAC 여부를 독립 판단해 필요한 것만 재인코딩되는지도 함께 확인."""
        clip = self.tmp / "clip.mov"
        second = self.tmp / "second.mov"
        src = self.tmp / "multi_audio.mkv"
        _make_clip(clip, "libx264", "aac")
        _make_clip(second, "libx264", "ac3")
        subprocess.run(["ffmpeg", "-hide_banner", "-y",
                         "-i", str(clip), "-i", str(second),
                         "-map", "0:v", "-map", "0:a", "-map", "1:a",
                         "-c:v", "copy", "-c:a", "copy", str(src)],
                        capture_output=True, check=True, timeout=15)
        out = converters.convert(src, "mp4", self.tmp)
        streams = self._probe(out)
        audios = [s for s in streams if s["codec_type"] == "audio"]
        self.assertEqual(len(audios), 2)
        self.assertTrue(all(s["codec_name"] == "aac" for s in audios))

    def test_subtitle_track_dropped_not_fatal(self):
        """자막 트랙이 있어도(v1은 자막 미지원) 변환 자체는 성공해야 함."""
        src = self.tmp / "clip.mkv"
        _make_clip(src, "libx264", "aac")
        with_sub = self.tmp / "with_sub.mkv"
        srt = self.tmp / "sub.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\ntest\n", encoding="utf-8")
        subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-i", str(srt),
                         "-map", "0:v", "-map", "0:a", "-map", "1:s",
                         "-c:v", "copy", "-c:a", "copy", "-c:s", "srt", str(with_sub)],
                        capture_output=True, check=True, timeout=15)
        out = converters.convert(with_sub, "mp4", self.tmp)
        streams = self._probe(out)
        self.assertEqual(len(streams), 2)  # 자막 제외, 영상+오디오만


if __name__ == "__main__":
    unittest.main()
