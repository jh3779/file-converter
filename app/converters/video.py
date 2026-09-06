"""영상 변환 — 영상→MP4 (FFmpeg LGPL 빌드 번들, DEC-024·DEC-060).

영상 스트림은 H.264/HEVC일 때 그대로 복사(스트림 카피 — 재인코딩 없음,
무손실, 사실상 즉시 완료)한다. 그 외 코덱은 Windows Media Foundation
인코더(h264_mf)로 재인코딩을 시도한다(DEC-060). 오디오는 AAC면 그대로
복사하고, 아니면 ffmpeg 내장 AAC 인코더로 재인코딩한다.

ffprobe JSON으로 코덱을 판별하며, 콘텐츠 기반 입력 감지에서도 실제 변환과
동일한 지원 판정을 재사용한다. 즉 H.264/HEVC이거나, 그 외 코덱이라도 현재
FFmpeg에서 h264_mf 폴백을 실제 사용할 수 있을 때만 MP4 변환 가능으로 본다.
"""
from functools import lru_cache
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..bundle import engine_dir
from .base import ConversionError

_SAFE_VIDEO_CODECS = {"h264", "hevc"}
_SAFE_AUDIO_CODECS = {"aac"}
_TIMEOUT = 300
_FALLBACK_VIDEO_ENCODER = "h264_mf"  # Windows Media Foundation — DEC-060
_REENCODE_TIMEOUT = 1800
_DEFAULT_BITS_PER_PIXEL = 0.1


def find_ffmpeg() -> str | None:
    return _find_tool("ffmpeg")


def find_ffprobe() -> str | None:
    return _find_tool("ffprobe")


def _find_tool(name: str) -> str | None:
    env = os.environ.get(f"FILECONV_{name.upper()}")
    if env and Path(env).exists():
        return env
    bundled = engine_dir() / "ffmpeg" / (f"{name}.exe" if sys.platform == "win32" else name)
    if bundled.exists():
        return str(bundled)
    return shutil.which(name)


def _probe_streams(ffprobe: str, src: Path) -> list[dict]:
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", str(src)],
            capture_output=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0:
        raise ConversionError("err.corrupted", proc.stderr.decode(errors="replace")[:200])
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ConversionError("err.corrupted", str(e))
    return data.get("streams", [])


def _real_video_streams(streams: list[dict]) -> list[dict]:
    """커버 아트(attached_pic)를 제외한 실제 영상 스트림만 반환."""
    return [
        s for s in streams
        if s.get("codec_type") == "video"
        and not s.get("disposition", {}).get("attached_pic")
    ]


@lru_cache(maxsize=8)
def _encoder_available(ffmpeg: str, encoder: str) -> bool:
    """현재 FFmpeg 빌드가 encoder를 실제 노출하는지 확인한다.

    파일마다 `ffmpeg -encoders`를 반복하지 않도록 실행 파일 경로+인코더 이름
    기준으로 캐시한다. 실행 자체가 실패하면 사용할 수 없는 것으로 본다.
    """
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    text = proc.stdout.decode(errors="replace")
    return encoder in text


def _fallback_video_encoder_available(ffmpeg: str | None = None) -> bool:
    ffmpeg = ffmpeg or find_ffmpeg()
    return bool(ffmpeg and _encoder_available(ffmpeg, _FALLBACK_VIDEO_ENCODER))


def streams_convertible_to_mp4(streams: list[dict], ffmpeg: str | None = None) -> bool:
    """ffprobe stream 목록이 현재 `video_to_mp4` 지원 범위인지 판정.

    이 함수가 콘텐츠 감지와 실제 변환의 공통 계약이다. 안전 코덱(H.264/HEVC)
    은 stream copy가 가능하므로 바로 True. 그 외 코덱은 DEC-060 폴백인
    h264_mf가 현재 FFmpeg에 실제 있을 때만 True다.
    """
    videos = _real_video_streams(streams)
    if not videos:
        return False
    codec = videos[0].get("codec_name")
    if codec in _SAFE_VIDEO_CODECS:
        return True
    return _fallback_video_encoder_available(ffmpeg)


def can_convert_to_mp4(src: Path) -> bool:
    """확장자와 무관하게 src가 현재 앱에서 MP4로 변환 가능한지 확인.

    판별 실패/손상 파일은 UI에서 변환 가능으로 노출하지 않기 위해 False로
    처리한다. 실제 변환에서 다시 검증하므로 이 함수는 지원 노출용 사전 판정이다.
    """
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg is None or ffprobe is None:
        return False
    try:
        streams = _probe_streams(ffprobe, src)
    except (ConversionError, OSError):
        return False
    return streams_convertible_to_mp4(streams, ffmpeg)


def _target_video_bitrate(video_stream: dict) -> int:
    """재인코딩 목표 비트레이트(bps)."""
    bit_rate = video_stream.get("bit_rate")
    if bit_rate:
        try:
            return int(bit_rate)
        except (TypeError, ValueError):
            pass
    width = video_stream.get("width") or 1280
    height = video_stream.get("height") or 720
    try:
        num, den = (video_stream.get("avg_frame_rate") or "25/1").split("/")
        fps = float(num) / float(den) if float(den) else 25.0
    except (ValueError, ZeroDivisionError):
        fps = 25.0
    return max(int(width * height * fps * _DEFAULT_BITS_PER_PIXEL), 500_000)


def video_to_mp4(src: Path, tmpdir: Path) -> Path:
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg is None or ffprobe is None:
        raise ConversionError("err.video_missing")

    streams = _probe_streams(ffprobe, src)
    video_streams = _real_video_streams(streams)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise ConversionError("err.corrupted", "영상 스트림 없음")

    video_stream = video_streams[0]
    video_codec = video_stream.get("codec_name")
    is_safe_codec = video_codec in _SAFE_VIDEO_CODECS
    if is_safe_codec:
        video_codec_args = ["-c:v", "copy"]
    else:
        # 콘텐츠 감지와 실제 변환의 지원 판정을 일치시킨다. h264_mf가 없는
        # 환경에서 먼저 MP4 대상으로 노출한 뒤 실패하는 false positive를 막는다.
        if not _fallback_video_encoder_available(ffmpeg):
            raise ConversionError("err.video_codec_unsupported", video_codec or "unknown")
        video_codec_args = [
            "-c:v", _FALLBACK_VIDEO_ENCODER,
            "-b:v", str(_target_video_bitrate(video_stream)),
        ]

    # ffprobe로 검증한 절대 스트림 인덱스를 그대로 매핑해 attached picture와
    # 실제 영상이 섞인 파일에서도 검증 대상과 실제 변환 대상을 일치시킨다.
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-map", f"0:{video_stream['index']}", *video_codec_args, "-sn",
    ]
    for i, a in enumerate(audio_streams):
        codec = "copy" if a.get("codec_name") in _SAFE_AUDIO_CODECS else "aac"
        cmd += ["-map", f"0:{a['index']}", f"-c:a:{i}", codec]

    out = tmpdir / (src.stem + ".mp4")
    cmd.append(str(out))
    timeout = _TIMEOUT if is_safe_codec else _REENCODE_TIMEOUT
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not out.exists():
        if is_safe_codec:
            raise ConversionError("err.corrupted", proc.stderr.decode(errors="replace")[:200])
        raise ConversionError("err.video_codec_unsupported", video_codec or "unknown")
    return out
