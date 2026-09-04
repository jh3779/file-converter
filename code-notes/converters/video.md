# video.py — 영상→MP4 변환 (FFmpeg 서브프로세스)

원본: `app/converters/video.py` (161줄)

이 프로젝트에서 유일하게 **외부 실행 파일(FFmpeg)을 서브프로세스로 호출**
하는 컨버터다(다른 파일들은 대부분 pip 라이브러리를 함수로 직접 호출).
"스트림 카피"(무손실, 즉시 완료)를 최우선으로 시도하고, 안 되면 Windows
전용 재인코딩으로 폴백하는 2단계 전략이 핵심이다.

---

## L1-29: 모듈 docstring — 설계 이유 전체

- **핵심 전략(L3-14)**: 영상 스트림이 H.264/HEVC면 **재인코딩 없이 그대로
  복사**(스트림 카피 — 컨테이너만 바꾸고 실제 인코딩된 데이터는 안 건드림,
  그래서 무손실이고 거의 즉시 끝남). 그 외 코덱은 Windows Media Foundation
  인코더(`h264_mf`)로 재인코딩을 시도한다(DEC-060). 이건 원래(DEC-024)
  "Mac 개발 환경에서 검증할 방법이 없다"며 미뤄뒀던 것을, CI의 Windows
  러너에서 실제 인코딩과 VMAF(화질 측정 지표) 비교까지 해서 검증한 뒤
  채택했다.
- **왜 h264_mf인가**: GPU 없는 헤드리스 서버(CI 러너)에서도 소프트웨어
  MFT(Media Foundation Transform)로 정상 동작함을 확인했다. h264_mf가
  없거나(비Windows) 재인코딩 자체가 실패하면, 기존과 동일하게 명확한
  오류(`err.video_codec_unsupported`)로 거부한다 — "검증 안 된 복잡한
  선택지보다 검증된 범위를 먼저"라는 원칙(DEC-010과 동일)은 유지하되,
  이제 h264_mf가 그 "검증된 범위"에 새로 들어왔다.
- **오디오**: AAC면 그대로 복사, 아니면 FFmpeg 내장 AAC 인코더(외부
  라이브러리 불필요, LGPL 코어에 포함)로만 재인코딩한다.
- **알려진 한계(L16-23)**:
  1. macOS는 FFmpeg를 아예 번들하지 않는다(DEC-029 — 검증된 사전 빌드
     LGPL macOS 바이너리가 없었음) — 이 기능 전체가 사실상 Windows·
     Linux 전용(기존 스트림 카피도 마찬가지였으니 새로운 비대칭은 아님).
  2. h264_mf의 화질은 libx264(GPL이라 애초에 미사용)보다는 낮을 것으로
     "추정"되지만 직접 비교는 안 했다 — 다만 DEC-024가 기각했던
     libopenh264보다는 VMAF로 뚜렷이 낫다는 건 확인했다.
  3. 목표 비트레이트는 원본 스트림의 값을 그대로 재사용하고, 없으면
     해상도 기반 근사치를 쓴다(자세한 건 L84-105).
- **왜 ffprobe로 코덱을 확인하는가(L25-29)**: `ffmpeg`가 exit code 0
  ("성공")을 반환해도, MP4 표준에 맞지 않는 조합(예: MPEG-2나 AC3를
  그대로 담은 "MP4"라는 파일)을 만들어낼 수 있다는 걸 직접 재현해서
  확인했다 — 즉 **exit code만으로는 "제대로 된 MP4가 나왔는지" 검증할
  수 없다**. 그래서 `ffmpeg -i`의 텍스트 로그를 파싱하는 옛날 방식
  대신, `ffprobe -show_streams -print_format json`으로 구조화된 JSON을
  받아 코덱 이름을 명시적으로 확인한다.

## L31-46: import와 상수

```python
import json, os, shutil, subprocess, sys
from pathlib import Path
from ..bundle import engine_dir
from .base import ConversionError

_SAFE_VIDEO_CODECS = {"h264", "hevc"}
_SAFE_AUDIO_CODECS = {"aac"}
_TIMEOUT = 300
_FALLBACK_VIDEO_ENCODER = "h264_mf"
_REENCODE_TIMEOUT = 1800
_DEFAULT_BITS_PER_PIXEL = 0.1
```

- 이 파일이 `subprocess`를 쓰는 유일한 컨버터다(다른 파일은 라이브러리
  함수 호출로 끝남) — FFmpeg는 파이썬 바인딩이 아니라 독립 실행 파일이라
  프로세스로 띄워야 한다.
- `..bundle`의 `engine_dir()`: 이 앱이 배포될 때 실행 파일 옆에 번들되는
  `engine/` 폴더 경로를 계산하는 함수(다른 컨버터, 예: `office.py`의
  `find_soffice()`도 같은 함수를 쓴다) — "배포판이면 번들 엔진을,
  개발 환경이면 시스템 설치본을" 찾는 공통 패턴의 일부.
- `_TIMEOUT = 300`(5분): 스트림 카피 위주라 넉넉히 잡아도 실제로는
  금방 끝난다는 주석. `_REENCODE_TIMEOUT = 1800`(30분): 재인코딩은
  훨씬 오래 걸릴 수 있어 별도로 더 긴 제한을 둔다.
- `_DEFAULT_BITS_PER_PIXEL = 0.1`: "경험적으로 적당한 화질"이라고
  주석에 명시된 근사치 상수 — 정확한 산출 근거보다는 실용적 기본값.

## L49-64: FFmpeg/FFprobe 실행 파일 탐색

```python
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
```

3단계 우선순위 탐색 — 이 프로젝트의 모든 외부 엔진 탐색 함수(`office.py`의
`find_soffice()` 등)가 공유하는 패턴:
1. **L58-60**: 환경변수(`FILECONV_FFMPEG`/`FILECONV_FFPROBE`)로 명시적
   경로가 지정돼 있고 실제로 존재하면 최우선으로 그걸 쓴다 — 개발·CI
   환경에서 특정 빌드를 강제로 지정할 때 쓰인다(테스트 코드에서 이
   환경변수를 세팅하는 걸 볼 수 있다).
2. **L61-63**: 배포판이면 `engine_dir()/ffmpeg/` 아래 번들된 실행
   파일을 찾는다. `sys.platform == "win32"`일 때만 `.exe` 확장자를
   붙인다 — Windows는 실행 파일에 확장자가 필요하고, macOS/Linux는
   없어도 된다.
3. **L64**: 위 둘 다 없으면 `shutil.which(name)`으로 시스템 PATH에
   설치된 걸 찾는다(개발자가 Homebrew 등으로 설치한 경우).
4. 셋 다 없으면 `None` — 호출자(`video_to_mp4`)가 이걸 보고
   `err.video_missing`을 던진다.

## L67-81: `_probe_streams` — ffprobe로 스트림 정보 얻기

```python
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
```

- `subprocess.run([...], capture_output=True, timeout=30)`: `ffprobe`를
  30초 제한으로 실행하고, stdout/stderr를 모두 캡처한다(화면에 안 뿜고
  파이썬에서 읽기 위해).
- **명령줄 인자**: `-v quiet`(불필요한 로그 억제), `-print_format json`
  (사람이 읽는 텍스트가 아니라 파싱하기 쉬운 JSON으로), `-show_streams`
  (컨테이너 안의 각 스트림 — 영상/오디오/자막 각각 — 정보를 요청).
- **타임아웃/실패/파싱 실패 3단계 처리**: 30초 안에 안 끝나면
  `err.engine`, 프로세스가 비정상 종료(`returncode != 0`, 예: 파일이
  아예 영상이 아님)면 `err.corrupted`(stderr 앞 200자만 detail로),
  JSON 파싱 자체가 깨지면(예상 못한 출력 형식) 역시 `err.corrupted`.
- `data.get("streams", [])`: JSON에 `"streams"` 키가 없어도(빈
  파일 등) 예외 없이 빈 리스트를 반환 — 그러면 호출자가 "영상 스트림
  없음"으로 자연스럽게 처리한다.

## L84-105: `_target_video_bitrate` — 재인코딩 목표 비트레이트 계산

```python
def _target_video_bitrate(video_stream: dict) -> int:
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
```

이 함수가 필요한 이유(docstring L84-91): `h264_mf`(Windows Media
Foundation 인코더)는 CRF(화질 기준 레이트 컨트롤, libx264 등에 흔한
방식) 같은 옵션이 없다 — Media Foundation API 자체의 제약으로 **비트레이트
직접 지정만** 지원한다. 그래서 "적당한 화질"을 얻으려면 목표 비트레이트
숫자를 계산해서 넘겨줘야 한다.

- **L92-97**: 가장 좋은 값은 원본 스트림이 이미 갖고 있는 `bit_rate`다
  — 재인코딩 전후로 파일 크기·화질 기대치가 비슷하게 유지되도록 원본
  값을 그대로 재사용한다. `int(bit_rate)` 변환이 실패할 수도 있어서
  (`TypeError`/`ValueError`) try/except로 감싸고, 실패하면 그냥
  넘어가(`pass`) 아래 근사치 계산으로 폴백한다.
- **L98-105 (근사치 계산, bit_rate가 없는 드문 컨테이너용)**:
  - 해상도가 없으면 1280×720(HD 기본값)으로 가정.
  - `avg_frame_rate`는 ffprobe가 `"25/1"`처럼 분수 문자열로 준다 —
    `.split("/")`로 분자/분모를 나눠 `float(num)/float(den)`으로
    실제 fps를 계산한다. 값이 없으면(`or "25/1"`) 기본 25fps로 가정.
    분모가 0이거나 값 자체가 숫자로 파싱 안 되면(`ValueError`,
    `ZeroDivisionError`) 25.0으로 폴백.
  - `width * height * fps * _DEFAULT_BITS_PER_PIXEL`: "픽셀당 비트"
    방식의 표준적인 비트레이트 근사 공식(가로×세로×초당 프레임 수×
    픽셀당 비트 계수). `max(..., 500_000)`으로 최소 500kbps는 보장
    (너무 낮은 비트레이트로 인코딩되는 걸 방지).

## L108-161: `video_to_mp4` — 메인 변환 함수

```python
def video_to_mp4(src: Path, tmpdir: Path) -> Path:
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg is None or ffprobe is None:
        raise ConversionError("err.video_missing")

    streams = _probe_streams(ffprobe, src)
    video_streams = [s for s in streams
                      if s.get("codec_type") == "video"
                      and not s.get("disposition", {}).get("attached_pic")]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise ConversionError("err.corrupted", "영상 스트림 없음")

    video_stream = video_streams[0]
    video_codec = video_stream.get("codec_name")
    is_safe_codec = video_codec in _SAFE_VIDEO_CODECS
    if is_safe_codec:
        video_codec_args = ["-c:v", "copy"]
    else:
        video_codec_args = ["-c:v", _FALLBACK_VIDEO_ENCODER,
                             "-b:v", str(_target_video_bitrate(video_stream))]

    cmd = [ffmpeg, "-y", "-i", str(src),
           "-map", f"0:{video_stream['index']}", *video_codec_args, "-sn"]
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
```

- **L109-112**: 엔진 자체가 없으면(개발 환경에 FFmpeg 미설치, 또는
  macOS 배포판처럼 애초에 번들 안 됨) `err.video_missing`으로 즉시
  실패. `app/converters/__init__.py`가 이 함수 자체를 `TARGETS`에서
  빼버리는 경우(모듈 로드 시점에 `find_ffmpeg() is None`이면)도
  있으니, 이 체크는 "TARGETS에는 있었는데 실행 시점에 엔진이
  사라진"(예: 백신이 격리시킴, DEC-033 참고) 드문 경우를 위한
  방어선이다.
- **L114-121: 스트림 분류**:
  - `video_streams`: `codec_type == "video"`이면서 `attached_pic`
    (앨범아트처럼 "첨부 이미지"로 표시된 스트림)이 **아닌** 것만.
    많은 오디오 파일(MP3, MOV 등)이 커버 아트를 "영상 스트림"처럼
    담고 있는데, 이건 진짜 영상이 아니므로 걸러낸다.
  - `audio_streams`: 오디오 타입 전부.
  - 진짜 영상 스트림이 하나도 없으면 `err.corrupted`.
- **L123-135: 코덱 판단과 인자 구성**:
  - 첫 번째(주된) 영상 스트림의 코덱 이름을 확인해
    `_SAFE_VIDEO_CODECS`(`{"h264", "hevc"}`)에 있는지 본다.
  - 안전한 코덱이면 `-c:v copy`(재인코딩 없이 그대로 복사).
  - 아니면 `-c:v h264_mf -b:v <계산된 비트레이트>`로 재인코딩 시도.
- **L137-143: 스트림 매핑에서의 주의점(중요한 버그 방지 코드)**:
  ```python
  cmd = [ffmpeg, "-y", "-i", str(src),
         "-map", f"0:{video_stream['index']}", *video_codec_args, "-sn"]
  ```
  주석(L137-141)이 설명하는 함정: FFmpeg의 `-map 0:v:0`(소문자 v)
  같은 스트림 지정자는 "첨부 이미지"도 영상 스트림으로 세어버릴 수
  있다(대문자 `V`를 써야 첨부 이미지가 제외됨, 하지만 그것도
  완벽하지 않을 수 있음). 만약 첨부 이미지 스트림이 실제 영상
  스트림보다 파일 안에서 **먼저** 나온다면, `-map 0:v:0`은
  "첫 번째 v 스트림"인 첨부 이미지를 가리키게 돼, 위에서
  `_SAFE_VIDEO_CODECS`로 검증한 진짜 영상 스트림과 다른 게 매핑되는
  불일치가 생길 수 있다. 그래서 이 코드는 `f"0:{video_stream['index']}"`
  처럼 **ffprobe로 이미 확인한 절대 스트림 인덱스**(정수, 예: `"0:2"`)
  를 그대로 쓴다 — "검증한 대상"과 "실제로 매핑되는 대상"을 반드시
  일치시키기 위한 방어. `-sn`은 자막 스트림을 제외(subtitle none).
- **L144-148: 오디오 트랙 처리**:
  ```python
  for i, a in enumerate(audio_streams):
      codec = "copy" if a.get("codec_name") in _SAFE_AUDIO_CODECS else "aac"
      cmd += ["-map", f"0:{a['index']}", f"-c:a:{i}", codec]
  ```
  다국어/해설 트랙처럼 오디오가 여러 개일 수 있는데, **전부 보존**
  한다(주석 L144-145). 각 트랙마다 **독립적으로** AAC 여부를 판단해
  AAC면 복사, 아니면 재인코딩 — 예를 들어 한 트랙은 AAC고 다른
  트랙은 AC3라면, AAC 트랙은 그대로 복사하고 AC3 트랙만 재인코딩한다.
  `f"-c:a:{i}"`는 FFmpeg 문법으로 "i번째로 매핑된 오디오 출력 스트림의
  코덱"을 가리킨다(출력 스트림 인덱스 기준, 소스 인덱스가 아님에 주의).
- **L152**: 안전한 코덱(스트림 카피)이면 짧은 타임아웃(`_TIMEOUT`,
  5분), 재인코딩이면 긴 타임아웃(`_REENCODE_TIMEOUT`, 30분) — 작업
  성격에 맞춰 다르게 잡는다.
- **L157-160: 실패 시 두 가지로 갈라지는 오류 메시지**:
  ```python
  if proc.returncode != 0 or not out.exists():
      if is_safe_codec:
          raise ConversionError("err.corrupted", ...)
      raise ConversionError("err.video_codec_unsupported", video_codec or "unknown")
  ```
  같은 "실패"(exit code 비정상 또는 출력 파일이 실제로 안 생김)이지만
  원인 코덱이 안전했는지 아닌지에 따라 **다른 에러 키**로 나눈다:
  - 이미 "안전한 코덱"(H.264/HEVC)이었는데도 실패했다면, 이건 코덱
    문제가 아니라 파일 자체가 손상됐다는 뜻 → `err.corrupted`.
  - 안전하지 않은 코덱이라 재인코딩을 시도했는데 그게 실패했다면
    (h264_mf가 없는 비Windows, 또는 재인코딩 자체가 실패) →
    `err.video_codec_unsupported`(코덱 이름을 detail에 실어서).
  이 구분 덕분에 사용자는 "내 파일이 깨졌다"와 "이 코덱은 지원 안
  한다"를 구분해서 안내받는다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `_probe_streams`가 실패할 수 있는 세 가지 경우(타임아웃/비정상
  종료/JSON 파싱 실패)는 각각 어떤 실제 상황에서 발생하는가?
- `-map` 인자에서 절대 스트림 인덱스를 쓰는 게 왜 중요한가? 만약
  `-map 0:v:0`(코덱 판단과 무관하게)을 그냥 썼다면 어떤 상황에서
  버그가 날 수 있었는가?
- `is_safe_codec`이 True인데도 최종 변환이 실패하면 왜
  `err.video_codec_unsupported`가 아니라 `err.corrupted`를 던지는가?
- `_target_video_bitrate`가 `bit_rate` 메타데이터를 신뢰하지 못하는
  경우(파싱 실패)와 애초에 없는 경우를 어떻게 같은 폴백 경로로
  합류시키는가?
