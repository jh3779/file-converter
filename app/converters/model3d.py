"""3D 모델 포맷 변환 — OBJ/STL/PLY/GLB/GLTF 상호 변환 (trimesh, MIT 라이선스).

trimesh는 numpy 하나만 필수 의존성으로 갖는 순수 Python 라이브러리라
(Assimp·Blender처럼 별도 네이티브 바이너리를 번들할 필요가 없음) 이
프로젝트의 다른 pip 기반 변환기(Pillow의 image.py 등)와 같은 방식으로
쓸 수 있다. 이번 스파이크에서 5개 포맷 전 조합(20쌍)을 직접 왕복 검증해
정점·면 개수·부피(volume)가 모두 정확히 보존됨을 확인했다.

**알려진 한계(정직하게 문서화)**: STL은 포맷 자체에 색상/재질 정보가
없다 — OBJ/PLY/GLB에 있던 정점 색상(vertex color)이나 재질(material)이
STL로 변환하면 사라진다(직접 재현 확인: 빨간색으로 칠한 정육면체를
STL로 내보내면 회색으로 나옴). 형태(geometry)는 모든 조합에서 보존되지만
색상/재질은 대상이 STL이면 유실된다 — 변환 전 UI 고지(note.stl_no_color).

**자동 PR 리뷰가 지적한 실제 버그 1건(재현 확인 후 수정)**: `.gltf`(텍스트
JSON 변환)는 포맷 자체가 다중 파일이라, trimesh가 기본값으로 내보내면
정점·인덱스 버퍼를 같은 폴더에 별도 `.bin` 파일로 분리해 만든다(직접
재현 확인). 이 앱의 출력 파이프라인(`app/output.py`의 `finalize()`)은
`convert()`가 돌려준 파일 하나만 원본 폴더로 옮기고 나머지 임시 폴더는
통째로 지운다(`app/workers.py`) — 그러면 `.bin`이 사라진 채로 남은
`.gltf`는 그 버퍼를 찾지 못해 깨진 파일이 된다. `embed_buffers=True`로
내보내면 버퍼가 base64 데이터 URI로 `.gltf` 안에 그대로 박혀 단일 파일이
된다(직접 재현 확인 — 재로드 시 형태 동일). glTF 익스포터에만 있는
옵션이라(`.glb`·OBJ·STL·PLY 익스포터에 넘기면 `TypeError`) target이
"gltf"일 때만 넘긴다.
"""
from pathlib import Path

from .base import ConversionError

_TARGET_EXTS = ("obj", "stl", "ply", "glb", "gltf")


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
