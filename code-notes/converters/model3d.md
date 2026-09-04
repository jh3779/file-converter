# model3d.py — 3D 모델(OBJ/STL/PLY/GLB/GLTF) 상호 변환

원본: `app/converters/model3d.py` (51줄)

가장 짧은 컨버터 파일이지만(실제 함수는 18줄), docstring에 실제로 발견된
버그 하나와 그 수정 근거가 그대로 남아 있어 "왜 이 코드가 이 모양인지"를
가장 압축적으로 보여준다.

---

## L1-26: 모듈 docstring

세 부분으로 나뉜다:

1. **왜 trimesh인가(L1-7)**: `trimesh`는 `numpy` 하나만 필수 의존성으로
   갖는 순수 Python 라이브러리다. 경쟁 후보였을 Assimp·Blender는 네이티브
   바이너리(컴파일된 C++ 라이브러리나 전체 애플리케이션)를 따로 번들해야
   해서, 이 프로젝트의 다른 `pip` 기반 변환기(Pillow 등)와 이질적이다 —
   `trimesh`는 `pip install`만으로 끝나 기존 패턴과 일치한다. 스파이크
   단계에서 5개 포맷의 전 조합(5×4=20쌍)을 직접 왕복 변환해 정점·면
   개수·부피(volume)가 보존됨을 확인했다.
2. **알려진 한계 — STL 색상 유실(L9-13)**: STL 포맷 자체가 색상/재질
   필드를 갖고 있지 않다(포맷 스펙의 한계이지 이 코드의 버그가 아님).
   OBJ/PLY/GLB에 있던 정점 색상이 STL로 내보내면 사라진다 — 실제로
   빨간 정육면체를 STL로 내보내면 회색이 되는 걸 직접 재현해서 확인했다.
   형태(geometry, 정점·면)는 모든 조합에서 보존되지만 색상은 대상이
   STL일 때만 사라진다 — 이 사실을 UI가 변환 전에 미리 알려준다
   (`note.stl_no_color`).
3. **실제 버그와 수정(L15-25)**: 아래 L46에서 자세히.

## L27-31: import와 상수

```python
from pathlib import Path
from .base import ConversionError

_TARGET_EXTS = ("obj", "stl", "ply", "glb", "gltf")
```

`_TARGET_EXTS`는 이 파일 안에서는 실제로 안 쓰인다(참고용으로 남겨둔
것으로 보임) — 실제 포맷 목록은 `__init__.py`의 `_MODEL3D_EXTS`가
정본이다. 이 파일의 진짜 로직은 `convert_3d` 함수 하나뿐이다.

## L34-51: `convert_3d` — 유일한 함수

```python
def convert_3d(src: Path, tmpdir: Path, target_ext: str) -> Path:
    import trimesh

    try:
        mesh = trimesh.load(src, force="mesh")
    except Exception as e:
        raise ConversionError("err.corrupted", str(e))

    if mesh.vertices is None or len(mesh.vertices) == 0:
        raise ConversionError("err.corrupted", "empty mesh")

    out = tmpdir / (src.stem + "." + target_ext)
    export_kwargs = {"embed_buffers": True} if target_ext == "gltf" else {}
    try:
        mesh.export(out, **export_kwargs)
    except Exception as e:
        raise ConversionError("err.engine", str(e))
    return out
```

- **L38**: `trimesh.load(src, force="mesh")` — 파일을 읽어 메시(정점+면)
  객체로 로드한다. `force="mesh"`가 중요한 옵션: trimesh는 파일 내용에
  따라 `Trimesh`(단일 메시), `Scene`(여러 메시로 구성된 장면), 심지어
  `PointCloud`(점군)처럼 다른 타입을 반환할 수 있는데, `force="mesh"`는
  "무조건 단일 메시로 합쳐서 달라"고 강제한다 — 이후 코드(L42의
  `mesh.vertices`)가 항상 같은 인터페이스(Trimesh 객체)를 기대하므로,
  이 강제가 없으면 입력에 따라 타입이 달라져 코드가 깨질 수 있다.
- **L39-40**: 로드 자체가 실패하면(포맷을 못 읽음, 손상된 파일 등)
  `err.corrupted`로 통일한다. `except Exception`으로 넓게 잡는 이유는
  trimesh가 내부적으로 포맷별 파서(OBJ 파서, STL 파서 등)를 쓰는데
  각각 어떤 예외를 던질지 다 예측하기 어렵기 때문 — "trimesh가 뭘
  던지든 우리 쪽에서는 다 '손상된 파일'로 통일해서 처리한다"는
  방어적 설계.
- **L42-43**: 로드 자체는 성공했지만 정점이 아예 없는(빈 메시) 경우도
  손상으로 간주한다 — `mesh.vertices is None`은 애초에 정점 배열
  자체가 없는 경우, `len(mesh.vertices) == 0`은 배열은 있지만 빈
  경우(둘 다 방어). 빈 메시를 그대로 내보내면 "성공했지만 아무것도
  없는 파일"이 나오므로, 이걸 미리 걸러 명확한 오류로 바꾼다.
- **L45**: 출력 파일명 규칙은 다른 모든 컨버터와 동일
  (`src.stem + "." + target_ext`).
- **L46: 이 파일의 핵심 — glTF 전용 옵션 분기**:
  ```python
  export_kwargs = {"embed_buffers": True} if target_ext == "gltf" else {}
  ```
  docstring(L15-25)이 설명하는 실제 발견된 버그의 수정이다:
  - `.gltf`(텍스트 기반 JSON 포맷)는 스펙상 다중 파일 구조를 쓸 수
    있다 — trimesh가 기본 옵션으로 내보내면, 정점·인덱스 같은 큰
    바이너리 데이터를 `.gltf` 옆에 별도 `.bin` 파일로 분리해서 만든다.
  - 그런데 이 앱의 출력 파이프라인(`app/output.py`의 `finalize()`,
    `app/workers.py`)은 **`convert()`가 반환한 파일 경로 하나만**
    원본 폴더로 옮기고, 나머지 임시 폴더(그 안의 `.bin` 포함)는
    통째로 삭제한다 — "입력 1개 → 출력 1개"라는 이 앱의 데이터 모델
    전제 때문이다.
  - 결과적으로, 기본 옵션으로 `.gltf`를 내보내면 `.bin`이 딸려있는데
    그 `.bin`이 삭제돼 버려서 `.gltf`가 열리지 않는(버퍼를 찾지 못하는)
    깨진 파일이 남는 실제 버그가 있었다 — "자동 PR 리뷰가 지적한
    실제 버그"라고 명시돼 있다(사람이 코드 리뷰 중 이 구조적 불일치를
    지적해서 발견됐다는 뜻).
  - 해결: `embed_buffers=True` 옵션을 주면, trimesh가 바이너리
    버퍼를 별도 `.bin` 파일로 안 쪼개고 **base64로 인코딩해 `.gltf`
    JSON 안에 데이터 URI로 직접 박아 넣는다** — 그러면 파일이
    하나로 완결되어(single file) 이 앱의 "출력 1개" 전제와 맞는다.
    재로드해서 형태가 동일함을 직접 재현 확인했다고 명시.
  - `target_ext == "gltf"`일 때만 이 옵션을 주는 이유: `embed_buffers`는
    glTF 익스포터에만 있는 옵션이라, OBJ/STL/PLY/`.glb`(바이너리
    glTF — 이건 원래 스펙상 이미 단일 파일이라 이 문제 자체가 없음)
    익스포터에 이 키워드 인자를 넘기면 `TypeError`가 난다(직접 확인).
    그래서 조건부로만 `export_kwargs`에 넣는다.
- **L47-50**: `mesh.export(out, **export_kwargs)`가 실패하면(디스크
  문제, 익스포터 자체 오류 등) `err.engine`으로 통일한다 — L38-40의
  "입력을 못 읽음"과 대비되는 "출력을 못 씀" 실패 지점.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시
- `force="mesh"` 옵션이 없으면 어떤 상황에서 이후 코드가 깨질 수 있는가?
- `embed_buffers=True`를 모든 포맷에 무조건 넘기면 왜 문제가 생기는가?
- 이 앱의 "출력 1개" 데이터 모델 전제가 `.gltf` 변환에 어떤 제약을
  만들었는가? 만약 `.gltf`+`.bin`을 둘 다 결과로 낼 수 있게 하려면
  이 파일 밖의 어느 부분(다른 파일)까지 바꿔야 하는가?
- STL로의 변환에서 색상이 사라지는 게 이 코드의 버그인가, 아닌가?
  왜 그렇게 판단할 수 있는가?
