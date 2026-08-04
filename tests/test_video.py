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

    def test_unsupported_video_codec_rejected(self):
        """DEC-024: H.264/HEVC 외 코덱은 v1 범위 밖 — 명시적으로 거부해야 한다.
        (ffmpeg 자체는 exit 0으로 "성공"할 수 있어 exit code만으로 판단하면 안 됨)"""
        src = self.tmp / "clip.mkv"  # 컨테이너는 지원 목록에 있어야 video_to_mp4 로직까지 도달함
        _make_clip(src, "mpeg2video", audio_codec=None)
        with self.assertRaises(ConversionError) as ctx:
            converters.convert(src, "mp4", self.tmp)
        self.assertEqual(ctx.exception.key, "err.video_codec_unsupported")

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
