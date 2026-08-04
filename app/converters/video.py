"""영상 변환 — 영상→MP4 (FFmpeg LGPL 빌드 번들, DEC-024).

v1 범위: 영상 스트림은 H.264/HEVC일 때만 그대로 복사(스트림 카피 —
재인코딩 없음, 무손실, 사실상 즉시 완료)한다. 그 외 코덱은 지원하지
않는다. 오디오는 AAC면 그대로 복사, 아니면 ffmpeg 내장(외부 라이브러리
불필요, LGPL 코어 포함) AAC 인코더로만 재인코딩한다.

왜 이렇게 좁혔는가: 실사용 영상 대부분(휴대폰 영상·화면 녹화·최근
콘텐츠)은 이미 H.264 또는 HEVC라 이 경로만으로 충분히 넓게 커버된다.
영상 코덱 자체를 재인코딩해야 하는 경우까지 지원하려면 인코더를 골라야
하는데, 조사해본 선택지들이 전부 트레이드오프가 있었다: OpenH264(BSD)는
실사용 화질이 x264보다 뚜렷하게 나쁨(Cisco 자체 이슈 트래커에서 확인),
libx264는 화질은 좋지만 GPL이라 이 프로젝트가 지금까지 지켜온 라이선스
기준과 다시 검토가 필요, Windows Media Foundation 인코더(h264_mf)는
Mac 개발 환경에서 검증할 방법이 없음. 검증 안 된 복잡한 선택지보다
검증된 좁은 범위(스트림 카피)를 먼저 내놓는다(PDF/HWP→DOCX의 DEC-010과
같은 원칙).

ffmpeg -i(구 텍스트 파싱)가 아니라 ffprobe -show_streams -print_format
json으로 코덱을 판별한다 — ffmpeg가 exit 0으로 "성공"해도 MP4 표준에
안 맞는 조합(예: MPEG-2나 AC3를 그대로 담은 MP4)을 만들 수 있음을 실제로
재현 확인했다 — exit code로 판단하면 안 되고 코덱 이름을 명시적으로
확인해야 한다.
"""
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
_TIMEOUT = 300  # 스트림 카피 위주라 넉넉히 잡아도 실제로는 금방 끝남


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


def video_to_mp4(src: Path, tmpdir: Path) -> Path:
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg is None or ffprobe is None:
        raise ConversionError("err.video_missing")

    streams = _probe_streams(ffprobe, src)
    # 앨범아트 등 "첨부 이미지"로 표시된 스트림은 진짜 영상이 아니므로 제외
    video_streams = [s for s in streams
                      if s.get("codec_type") == "video"
                      and not s.get("disposition", {}).get("attached_pic")]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise ConversionError("err.corrupted", "영상 스트림 없음")

    video_stream = video_streams[0]
    video_codec = video_stream.get("codec_name")
    if video_codec not in _SAFE_VIDEO_CODECS:
        raise ConversionError("err.video_codec_unsupported", video_codec or "unknown")

    # "0:v:0" 스트림 지정자는 첨부 이미지(커버 아트)도 영상 스트림으로 세어
    # 포함시킬 수 있어(대문자 V만 첨부 이미지를 제외), 첨부 이미지가 실제
    # 영상보다 앞선 파일에서는 위에서 검증한 스트림과 다른 것이 매핑될 수
    # 있다 — ffprobe로 확인한 절대 스트림 인덱스를 그대로 사용해 검증
    # 대상과 실제 매핑 대상을 일치시킨다.
    cmd = [ffmpeg, "-y", "-i", str(src),
           "-map", f"0:{video_stream['index']}", "-c:v", "copy", "-sn"]
    # 오디오 트랙 전부 보존(다국어/해설 트랙 등) — 트랙별로 AAC 여부를
    # 독립적으로 판단해 필요한 것만 재인코딩한다.
    for i, a in enumerate(audio_streams):
        codec = "copy" if a.get("codec_name") in _SAFE_AUDIO_CODECS else "aac"
        cmd += ["-map", f"0:{a['index']}", f"-c:a:{i}", codec]

    out = tmpdir / (src.stem + ".mp4")
    cmd.append(str(out))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ConversionError("err.engine", "timeout")
    if proc.returncode != 0 or not out.exists():
        raise ConversionError("err.corrupted", proc.stderr.decode(errors="replace")[:200])
    return out
