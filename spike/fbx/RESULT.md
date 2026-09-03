# FBX 3D 모델 지원 기술 스파이크 결과

> 2026-09-03 · OQ-007 검증 · 환경: macOS(Apple Silicon, arm64), Python 3.14.5(GIL 활성화, free-threaded 빌드 아님 확인 — `sys._is_gil_enabled()` True), `ufbx` 0.0.5(PyPI)

## 결론: **기각** — FBX 지원(REQ-F-020 확장 후보)은 현재 보류

`ufbx`는 라이선스·플랫폼 조건은 이 프로젝트 원칙(DEC-050)에 완전히 부합했지만, 실제 mesh 데이터 접근 시 인터프리터 종료 시점에 8/8 재현되는 세그폴트가 있어 채택 불가.

## 배경 — 왜 ufbx를 검토했는가

기존 3D 모델 변환기(`app/converters/model3d.py`, DEC-050)는 `trimesh`(MIT, 순수 Python)를 쓰는데, `trimesh`는 FBX를 전혀 지원하지 않는다(`trimesh.exchange.load.mesh_loaders` / `_mesh_exporters`에 `fbx` 없음, `trimesh==5.0.0`에서 직접 확인).

FBX SDK(Autodesk 독점 라이선스)·Blender bpy(GPL-3.0)·Assimp(네이티브 바이너리 번들 필요)는 DEC-050이 이미 배제한 이유와 정확히 충돌해 후보에서 제외. `ufbx`(https://github.com/ufbx/ufbx)는:

- 라이선스: **MIT 또는 Public Domain(Unlicense) 이중 라이선스** — 허용적 라이선스 원칙에 부합
- `ufbx` 자체는 C 라이브러리이고 Python 바인딩은 그 위에 얹은 **네이티브 확장**이다(아래 §3의 `lldb` 스택 트레이스에서 실제로 `_native.cpython-314-darwin.so`로 확인됨) — Assimp처럼 "네이티브 바이너리를 따로 번들해야 하는" 문제와 근본적으로는 같은 종류지만, PyPI에 Windows(`win_amd64`/`win_arm64`)·macOS(`x86_64`/`arm64`)·Linux(manylinux/musllinux, x86_64/aarch64) **사전 빌드 wheel**이 전부 존재해 `pip install`만으로 끝나고 별도 네이티브 빌드·시스템 설치가 불요하다는 점에서 DEC-050 원칙("허용적 라이선스 + pip install만으로 끝남")을 만족한다
- 다만 원 라이브러리 소개 자체가 "single source file FBX file **loader**" — 애초에 **읽기 전용**, 쓰기(export)는 지원 안 함. 채택되더라도 "FBX → 기존 5개 포맷" 단방향만 가능(다른 포맷 → FBX 저장은 불가능)

## 검증 절차

### 1. 실제 로드 성공 확인

ufbx 저장소 자체 테스트 픽스처를 사용(신뢰할 수 있는 실제 FBX 샘플, 참조용 OBJ 동봉):

```bash
git clone https://github.com/ufbx/ufbx.git ufbx-src
git -C ufbx-src checkout fcc5d6ba444cfd3eb80677dba5e37e493941abe5  # 이 스파이크 검증 시점 HEAD
# 픽스처: ufbx-src/data/maya_cube_big_endian_7400_binary.fbx
#   SHA256: ae57b303974668fb814dcca3c81cdd5adad3e3c72e4a69f16aa0776018a0e578
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

**직접 관측한 것**: 이 macOS(arm64)·Python 3.14.5·`ufbx` 0.0.5 환경에서, `python3 -c` 스크립트로 mesh 배열 데이터에 접근한 뒤 인터프리터를 종료하면 8/8 세그폴트가 재현됐다. PySide6 앱·Windows·패키징된(PyInstaller) 실행 파일에서의 재현은 이번 스파이크 범위에 없다.

**여기서 도출한 추론**(검증되지 않음, 재검토 시 직접 확인 필요): `lldb` 스택 트레이스가 보여주는 근본 원인(CPython `Py_Finalize`의 모듈 정리 순서에 의존하는 use-after-free)은 애플리케이션 종류나 OS에 특정되지 않는 CPython 자체의 종료 절차이므로, PySide6 데스크톱 앱(장시간 실행 프로세스라 "인터프리터 종료 시점"이 "사용자가 앱을 닫는 순간"과 일치)에서도 유사하게 재현될 가능성이 높다고 추정한다. 다만 이는 이 스파이크가 직접 검증한 결과가 아니라 스택 트레이스 해석에 기반한 추론이며, 채택을 다시 검토할 경우 실제 PySide6 앱·지원 대상 Python 버전·Windows 환경에서 재현 여부를 별도로 확인해야 한다.

이 macOS 환경에서만도 관측된 결과(스칼라 속성만 읽으면 안전, 배열 데이터에 접근하는 순간 8/8 크래시)만으로 채택을 보류하기에는 충분하다고 판단했다.

## 재검토 조건

- `ufbx`가 이 use-after-free를 수정한 새 버전을 릴리스하면(현재 0.0.5, 매우 초기 버전) 같은 절차로 재검증
- 또는 같은 기준(허용적 라이선스 + 3플랫폼 사전 빌드 wheel + 외부 실행 파일 설치 불요, 순수 Python이든 네이티브 확장이든 무관)을 만족하는 다른 FBX 파서가 나오면 같은 절차(로드 성공 → 배열 데이터 접근 후 반복 실행 → lldb 크래시 확인)로 검증

## 산출물

- 이 문서(재현 절차·명령·스택 트레이스 전문)
- 요약은 [docs/06_open_questions.md](../../docs/06_open_questions.md) OQ-007 참고

---

## 후속 스파이크(2단계): 자체 구현 읽기 전용 파서 실현 가능성

> 2026-09-03 · `ufbx` 세그폴트로 채택이 막힌 뒤, "네이티브 확장 없이
> 순수 Python(`struct`·`zlib` 표준 라이브러리)으로 FBX 바이너리를 직접
> 읽는 최소 파서를 만들 수 있는가"를 확인한 2단계 스파이크.

### 결론: **실현 가능** — FBX 7.x(2011년 이후 대부분의 익스포터 기본값) 바이너리에서 정점·폴리곤 데이터를 정확히 추출 성공

### 범위

형태(geometry)만 — 정점 좌표(`Vertices`)와 면 구성(`PolygonVertexIndex`)만
뽑는다. 애니메이션·스키닝·머티리얼·텍스처·노드 계층(transform)은 범위
밖(다른 5개 포맷 컨버터, `model3d.py`도 같은 "형태 위주" 범위 원칙).

### 구현: `spike/fbx/spike_parser.py` (194줄, 표준 라이브러리만 — `struct`·`zlib`·`pathlib`)

FBX 바이너리 포맷(공개적으로 알려진 리버스 엔지니어링 스펙, Autodesk
공식 문서 아님 — 실제 파일로 직접 검증)의 3개 레이어를 순서대로 구현:

1. **헤더**: 21바이트 매직(`Kaydara FBX Binary  \x00`) + 2바이트 + 버전
   (uint32 LE). 버전 ≥7500이면 이후 노드 레코드가 8바이트 필드를,
   미만이면 4바이트 필드를 쓴다(코드로 분기).
2. **노드 레코드(재귀)**: `EndOffset`·`NumProperties`·`PropertyListLen`
   + `NameLen`(1바이트)+`Name` + `Properties` + (있으면) 자식 노드들,
   13/25바이트 널 레코드로 자식 목록 종료.
3. **프로퍼티**: 1바이트 타입 코드로 분기 — 스칼라(`Y/C/I/F/D/L`)는
   고정 크기, 배열(`f/d/l/i/b`)은 `array_length`+`encoding`+
   `compressed_length` 헤더 뒤에 raw 또는 zlib 압축 데이터, 문자열/raw
   (`S/R`)는 4바이트 길이 접두.

### 검증 절차와 결과

같은 ufbx 저장소(커밋 `fcc5d6b`, RESULT.md 1단계와 동일 고정 리비전)의
테스트 픽스처 3개로 검증:

| 픽스처 | SHA256 | 버전 | 결과 |
|---|---|---|---|
| `maya_cube_7400_binary.fbx` | `4c827bcd...d32b9f23` | 7400(4바이트 오프셋) | ✅ 정점 8개·폴리곤 6개 — 정답과 정확히 일치 |
| `maya_cube_7500_binary.fbx` | `d80844d7...eb9d13c` | 7500(8바이트 오프셋) | ✅ 정점 8개·폴리곤 6개, 실제 좌표(`-0.5,-0.5,0.5`)까지 1단계에서 확인한 참조 OBJ와 일치 |
| `maya_cube_6100_binary.fbx` | `2917bf0f...b00d65df8` | 6100 | ❌ Geometry 노드 자체가 없음(아래 한계 참고) |

- `PolygonVertexIndex`의 비트 NOT 인코딩(폴리곤의 마지막 정점 인덱스를
  `~i`로 저장해 폴리곤 경계를 표시하는 FBX 특유의 관례)도 정상
  디코딩됨을 직접 확인(`[0, 1, 3, -3, ...]`에서 `-3 == ~2`, 즉 이
  폴리곤이 정점 `0,1,3,2`로 구성됨을 정확히 해석).
- 두 버전(7400/7500)이 서로 다른 오프셋 필드 크기(4바이트/8바이트)를
  쓰는데, 코드가 버전 번호만 보고 자동 분기해 둘 다 정확히 파싱함을
  확인 — 이건 실사용 FBX 파일 대부분(2011년 이후 익스포터)이 이 두
  버전대 중 하나를 쓴다는 점에서 중요한 신호.

### 알려진 한계(정직하게 문서화, 이번 스파이크 범위)

1. **FBX 6.x는 지원 안 됨**: 지오메트리가 별도 `Geometry` 오브젝트가
   아니라 `Model` 노드 안에 직접 내장되는 **다른 오브젝트 모델**을
   쓴다(FBX 7.0부터 새 오브젝트 모델로 전환된 것으로 알려짐 — 직접
   확인: `maya_cube_6100_binary.fbx`의 `Objects` 자식이
   `['Model', 'SceneInfo', 'Material', 'GlobalSettings']`로
   `Geometry`가 없음). 6.x 지원은 별도 파싱 경로가 추가로 필요.
2. **압축(zlib) 배열은 코드만 있고 실제 파일로 미검증**: 이 저장소의
   테스트 픽스처를 전수 스캔했으나 `encoding=1`(압축)로 저장된
   `Vertices` 배열을 가진 파일을 찾지 못했다 — 모두 `encoding=0`
   (비압축)이었다. `zlib.decompress()` 호출 경로 자체는 표준
   라이브러리 문서대로 구현했지만, **실제 압축된 FBX 파일로 직접
   검증하지 못했다**(이 프로젝트의 "직접 재현 확인" 원칙에 아직 못
   미치는 부분 — 재검토 시 압축 사용이 확인된 실제 파일로 추가 검증
   필요, 예: Blender가 내보낸 FBX는 흔히 압축을 씀).
3. **좌표계·단위 변환 없음**: `Vertices`를 원시 배열 그대로 반환한다
   — FBX는 씬 단위(cm/m/인치)·좌표축(Y-up/Z-up) 설정을
   `GlobalSettings` 노드에 따로 담는데, 이걸 안 읽으므로 다른
   포맷(예: OBJ는 관례적으로 임의 단위)으로 내보낼 때 크기·방향이
   원본 3D 툴에서 보던 것과 다를 수 있다.
4. **삼각형화 없음**: `PolygonVertexIndex`가 4각형 이상의 다각형을
   그대로 담을 수 있는데(이번 큐브 픽스처도 4각형 6개), 이걸
   삼각형으로 쪼개는 로직이 없다 — `trimesh`처럼 삼각형 메시만
   다루는 하위 파이프라인에 바로 못 물린다.
5. **연결(Connections) 미해석**: 씬에 `Geometry` 오브젝트가 여러 개
   있을 때 어느 것이 실제로 보이는 메시인지(예: 숨겨진 프록시
   메시 제외) `Connections` 노드로 판단해야 하는데, 이번 스파이크는
   `Objects` 아래 `Geometry`를 전부 무조건 추출한다.

### 실무적 함의 — "직접 만든다면" 질문에 대한 답

- **기술적으로는 가능**: 네이티브 확장이 전혀 없어(순수 Python)
  `ufbx`가 겪은 소멸 순서 use-after-free 같은 클래스의 버그 자체가
  구조적으로 발생할 수 없다. FBX 7.x 바이너리에서 형태 데이터를
  뽑아내는 핵심 파싱 로직은 194줄로 이미 동작한다.
- **프로덕션화까지는 추가 작업이 상당함**: 위 5가지 한계를 다
  메우려면(특히 좌표계 변환·삼각형화·Connections 해석·압축 실사용
  검증·ASCII FBX 지원 여부 결정) `model3d.py` 수준의 안정성에
  도달하기까지 최소 며칠~1주 이상의 반복 검증이 더 필요해 보인다
  — 다만 "완전히 막혀서 불가능"이 아니라 "범위를 좁혀 단계적으로
  넓혀갈 수 있는 정상적인 개발 작업"이라는 게 이번 스파이크의
  핵심 결론이다.
- **쓰기(export) 방향은 이번에 다루지 않음**: 이 스파이크는 읽기
  전용만 검증했다 — FBX를 생성하는 방향은 노드 트리를 거꾸로
  직렬화하는 완전히 별도의 작업이라 범위 밖으로 남긴다.

### 재검토·확장 시 다음 단계 제안

1. 압축된 실제 FBX 샘플(Blender 익스포트 등)로 zlib 경로 직접 검증
2. `GlobalSettings`의 단위·좌표축을 읽어 일관된 좌표계로 정규화
3. 다각형 삼각형화(fan triangulation 등 단순한 방법부터)
4. `Connections` 노드를 해석해 실제로 렌더링되는 Geometry만 선별
5. FBX 6.x 지원이 필요하면 `Model` 노드 직접 파싱 경로 추가
6. 위 항목들이 정리되면 `app/converters/model3d.py`처럼 `trimesh`
   메시 객체로 변환하는 어댑터를 붙여 기존 5개 포맷(OBJ/STL/PLY/
   GLB/GLTF)으로 내보내는 파이프라인과 통합

### 산출물

- `spike/fbx/spike_parser.py` — 이번 스파이크의 파서 구현
- 위 3개 픽스처와 SHA256(재현용)
