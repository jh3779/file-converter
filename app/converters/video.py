"""영상 변환 — 영상→MP4 (FFmpeg LGPL 빌드 번들, DEC-024·DEC-060·DEC-066).

영상 스트림은 H.264/HEVC일 때 그대로 복사(스트림 카피 — 재인코딩 없음,
무손실, 사실상 즉시 완료)한다. 그 외 코덱은 Windows Media Foundation
인코더(h264_mf)로 재인코딩을 시도한다(DEC-060) — Mac 개발 환경에서
검증할 방법이 없어 DEC-024에서 "복잡한 선택지" 취급하며 미뤄뒀던 것을,
CI(Windows 러너)로 실제 인코딩·VMAF 화질 비교까지 검증한 뒤 채택했다.
GPU 없는 헤드리스 서버에서도 소프트웨어 MFT로 정상 동작함을 확인(DEC-060
스파이크). h264_mf가 없거나(비Windows) 실패하면 기존과 동일하게
`err.video_codec_unsupported`로 명확히 거부한다 — "검증 안 된 복잡한
선택지보다 검증된 범위를 먼저"라는 DEC-010과 같은 원칙은 유지하되, 이제
h264_mf가 검증된 범위에 들어왔다. 오디오는 AAC면 그대로 복사, 아니면
ffmpeg 내장(외부 라이브러리 불필요, LGPL 코어 포함) AAC 인코더로만
재인코딩한다.

**알려진 한계**: (1) macOS는 FFmpeg 자체를 번들하지 않아(DEC-029, 검증된
사전 빌드 LGPL macOS 바이너리가 없음) 이 기능 전체가 Windows 전용이다 —
기존 스트림 카피 경로와 동일한 제약이라 새로운 비대칭은 아니다.
(2) h264_mf의 화질은 libx264(GPL이라 미사용)보다는 낮을 것으로 추정되나
직접 비교하지 않았다 — DEC-024가 기각한 libopenh264보다는 VMAF로 확인한
바 뚜렷이 낫다(DEC-060). (3) 목표 비트레이트는 원본 스트림의 bit_rate를
그대로 재사용한다 — 이 값이 없는 드문 컨테이너는 해상도 기반 근사치로
대체한다.

ffmpeg -i(구 텍스트 파싱)가 아니라 ffprobe -show_streams -print_format
json으로 코덱을 판별한다 — ffmpeg가 exit 0으로 "성공"해도 MP4 표준에
안 맞는 조합(예: MPEG-2나 AC3를 그대로 담은 MP4)을 만들 수 있음을 실제로
재현 확인했다 — exit code로 판단하면 안 되고 코덱 이름을 명시적으로
확인해야 한다.

DEC-066부터는 콘텐츠 기반 입력 감지(확장자 없음/알 수 없는 확장자 영상,
`converters.is_content_detected_video`)에서도 이 판별 로직을 그대로
재사용한다(`streams_convertible_to_mp4`) — 즉 H.264/HEVC이거나, 그 외
코덱이라도 현재 FFmpeg에서 h264_mf 폴백을 실제 사용할 수 있을 때만 MP4
변환 가능으로 노출해, 감지는 됐는데 실제 변환은 실패하는 false positive를
막는다.
"""

import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from ..bundle import engine_dir
from .base import ConversionError

_SAFE_VIDEO_CODECS = {"h264", "hevc"}
_SAFE_AUDIO_CODECS = {"aac"}
_TIMEOUT = 300  # 스트림 카피 위주라 넉넉히 잡아도 실제로는 금방 끝남
_FALLBACK_VIDEO_ENCODER = "h264_mf"  # Windows Media Foundation — DEC-060
_REENCODE_TIMEOUT = 1800  # 실제 재인코딩은 스트림 카피보다 오래 걸릴 수 있음
_DEFAULT_BITS_PER_PIXEL = 0.1  # 원본에 bit_rate 정보가 없을 때의 근사치(경험적 "적당한 화질" 기준)


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
            capture_output=True,
            timeout=30,
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
    return [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]


@lru_cache(maxsize=8)
def _encoder_available(ffmpeg: str, encoder: str) -> bool:
    """현재 FFmpeg 빌드가 encoder를 실제 노출하는지 확인한다.

    파일마다 `ffmpeg -encoders`를 반복하지 않도록 실행 파일 경로+인코더 이름
    기준으로 캐시한다. 실행 자체가 실패하면 사용할 수 없는 것으로 본다.
    """
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            timeout=10,
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
    """재인코딩 목표 비트레이트(bps) — 원본 스트림의 bit_rate를 그대로
    재사용해 재인코딩 전후 파일 크기·화질 기대치가 비슷하게 유지되도록
    한다. bit_rate가 없는 드문 컨테이너(일부 AVI/MKV는 스트림 레벨
    bit_rate를 안 담음)는 해상도×프레임레이트 기반 "픽셀당 비트" 근사치로
    대체한다 — h264_mf는 CRF 같은 화질 기준 레이트 컨트롤이 없어(Media
    Foundation 인코더 API 자체의 제약, 비트레이트 지정만 지원) 목표
    비트레이트가 항상 있어야 한다."""
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
            "-c:v",
            _FALLBACK_VIDEO_ENCODER,
            "-b:v",
            str(_target_video_bitrate(video_stream)),
        ]

    # ffprobe로 검증한 절대 스트림 인덱스를 그대로 매핑해 attached picture와
    # 실제 영상이 섞인 파일에서도 검증 대상과 실제 변환 대상을 일치시킨다.
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-map",
        f"0:{video_stream['index']}",
        *video_codec_args,
        "-sn",
    ]
    # 오디오 트랙 전부 보존(다국어/해설 트랙 등) — 트랙별로 AAC 여부를
    # 독립적으로 판단해 필요한 것만 재인코딩한다.
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
