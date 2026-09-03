# FBX 3D 모델 지원 기술 스파이크 결과

> 2026-09-03 · OQ-007 검증 · 환경: macOS(Apple Silicon, arm64), Python 3.14.5(GIL 활성화, free-threaded 빌드 아님 확인 — `sys._is_gil_enabled()` True), `ufbx` 0.0.5(PyPI)

## 결론: **기각** — FBX 지원(REQ-F-020 확장 후보)은 현재 보류

`ufbx`는 라이선스·플랫폼 조건은 이 프로젝트 원칙(DEC-050)에 완전히 부합했지만, 실제 mesh 데이터 접근 시 인터프리터 종료 시점에 8/8 재현되는 세그폴트가 있어 채택 불가.

## 배경 — 왜 ufbx를 검토했는가

기존 3D 모델 변환기(`app/converters/model3d.py`, DEC-050)는 `trimesh`(MIT, 순수 Python)를 쓰는데, `trimesh`는 FBX를 전혀 지원하지 않는다(`trimesh.exchange.load.mesh_loaders` / `_mesh_exporters`에 `fbx` 없음, `trimesh==5.0.0`에서 직접 확인).

FBX SDK(Autodesk 독점 라이선스)·Blender bpy(GPL-3.0)·Assimp(네이티브 바이너리 번들 필요)는 DEC-050이 이미 배제한 이유와 정확히 충돌해 후보에서 제외. `ufbx`(https://github.com/ufbx/ufbx)는:

- 라이선스: **MIT 또는 Public Domain(Unlicense) 이중 라이선스** — 허용적 라이선스 원칙에 부합
- PyPI에 Windows(`win_amd64`/`win_arm64`)·macOS(`x86_64`/`arm64`)·Linux(manylinux/musllinux, x86_64/aarch64) 사전 빌드 wheel 전부 존재 — `pip install`만으로 끝나는 라이브러리 원칙에 부합
- 다만 원 라이브러리 소개 자체가 "single source file FBX file **loader**" — 애초에 **읽기 전용**, 쓰기(export)는 지원 안 함. 채택되더라도 "FBX → 기존 5개 포맷" 단방향만 가능(다른 포맷 → FBX 저장은 불가능)

## 검증 절차

### 1. 실제 로드 성공 확인

ufbx 저장소 자체 테스트 픽스처를 사용(신뢰할 수 있는 실제 FBX 샘플, 참조용 OBJ 동봉):

```bash
git clone --depth 1 https://github.com/ufbx/ufbx.git ufbx-src
# 픽스처: ufbx-src/data/maya_cube_big_endian_7400_binary.fbx
# 참조:   ufbx-src/data/maya_cube_big_endian.obj (정점 8개, 면 6개)
```

```python
import ufbx
scene = ufbx.load_file("maya_cube_big_endian_7400_binary.fbx")
m = scene.meshes[0]
print(m.num_vertices, m.num_faces)  # 8 6 — 참조 OBJ와 정확히 일치
```

로드 자체와 스칼라 속성(`num_vertices` 등) 읽기는 정상 동작.

### 2. 세그폴트 재현 (8/8)

```python
import ufbx
scene = ufbx.load_file("maya_cube_big_endian_7400_binary.fbx")
m = scene.meshes[0]
verts = m.vertices          # Vec3List
idx = m.vertex_indices      # Uint32List
```

이 4줄을 `python3 -c`로 8회 반복 실행 — **8/8 모두 `exit 139`(SIGSEGV)**. 스크립트 자체는 정상 출력 후 끝나지만, 인터프리터 종료 시점에 크래시. `del m; del scene`으로 명시적으로 먼저 지워도 동일하게 재현됨(코드 순서로 회피 불가).

### 3. lldb로 근본 원인 특정

```bash
lldb -o "process launch" -o "continue" -o "bt all" -o "quit" -- python3 repro_crash.py
```

```
EXC_BAD_ACCESS (code=1, address=0x48)
frame #0: _native.cpython-314-darwin.so`Context_free + 224
frame #1: _native.cpython-314-darwin.so`Context_dealloc + 20
frame #2: Python`_Py_Dealloc + 100
frame #3: _native.cpython-314-darwin.so`Uint32List_dealloc + 60
frame #4: Python`dictkeys_decref + 356
frame #5: Python`dict_dealloc + 176
frame #6: Python`module_dealloc + 384
frame #7: Python`insertdict + 368
frame #8: Python`finalize_modules + 704
frame #9: Python`_Py_Finalize + 344
frame #10: Python`Py_RunMain + 436
frame #11: Python`pymain_main + 236
frame #12: Python`Py_BytesMain + 44
```

**해석**: `mesh.vertices`/`.vertex_indices`/`.faces` 같은 List류 속성에 접근하면 그 값을 담는 네이티브 wrapper(`Uint32List` 등)가 상위 `Context`(원본 scene 데이터를 참조 카운트로 공유하는 컨텍스트로 추정)에 대한 참조를 갖는다. 인터프리터 종료(`Py_Finalize` → `finalize_modules`) 시 CPython의 모듈 정리 순서가 이 `Context`를 List wrapper보다 **먼저 해제**해버리고, 뒤이어 List wrapper가 `dealloc`되며 이미 죽은 `Context`를 다시 `free`하려다 널/댕글링 포인터(`address=0x48`)를 역참조해 크래시 — 전형적인 **소멸 순서 의존성 use-after-free**.

## 실무적 함의

PySide6 데스크톱 앱은 장시간 실행되는 프로세스라 "인터프리터 종료 시점"이 정확히 "사용자가 앱을 닫는 순간"과 일치한다. 즉 FBX를 한 번이라도 읽어 mesh 배열 데이터(스칼라 속성만 읽는 건 안전)에 접근하면, **앱을 종료할 때 100% 재현 확률로 비정상 종료**될 것으로 판단된다 — 변환 자체는 성공해도 나중에 앱이 크래시하는 "가끔 나는 버그"가 아니라 구조적 결함.

## 재검토 조건

- `ufbx`가 이 use-after-free를 수정한 새 버전을 릴리스하면(현재 0.0.5, 매우 초기 버전) 같은 절차로 재검증
- 또는 다른 순수 Python·허용적 라이선스 FBX 파서가 나오면 같은 절차(로드 성공 → 배열 데이터 접근 후 반복 실행 → lldb 크래시 확인)로 검증

## 산출물

- 이 문서(재현 절차·명령·스택 트레이스 전문)
- 요약은 [docs/06_open_questions.md](../../docs/06_open_questions.md) OQ-007 참고
