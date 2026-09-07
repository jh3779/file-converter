# fbx.py — FBX(Autodesk) 읽기 전용 파서

원본: `app/converters/fbx.py` (334줄)

이 프로젝트에서 유일하게 "서드파티 3D 라이브러리에 안 기대고 바이너리
포맷을 직접 파싱하는" 파일이다. `model3d.py`가 trimesh 하나로 5개
포맷을 다 처리하는 것과 대조적으로, FBX는 trimesh가 아예 지원하지
않는 포맷이라 `struct`·`zlib` 표준 라이브러리만으로 바이너리 트리
파서를 새로 만들었다. 왜 그래야 했는지(ufbx 세그폴트)와 무엇을
검증했는지가 이 파일의 핵심 서사다.

---

## L1-57: 모듈 docstring

네 부분으로 나뉜다:

1. **왜 자체 파서인가(L3-11)**: 기성 라이브러리 `ufbx`(C 네이티브 확장,
   MIT/Unlicense)를 먼저 시도했는데, mesh 배열 데이터(`.vertices`
   등)에 접근한 뒤 인터프리터가 종료되는 시점에 8/8 재현되는
   세그폴트가 있었다(`spike/fbx/RESULT.md` 1단계 — `lldb`로 근본
   원인을 use-after-free로 특정). 그래서 네이티브 확장이 전혀 없는
   순수 Python 파서를 직접 구현했다 — 구조적으로 이 클래스의 버그
   (dealloc 순서 의존성) 자체가 발생할 수 없다.
2. **범위(L13-17)**: 형태(geometry)만 읽는다(다른 5개 포맷 컨버터와
   같은 "형태 위주" 원칙). **쓰기(FBX로 내보내기)는 아예 없다** —
   `__init__.py`의 `TARGETS`에 FBX는 소스로만 등록되고 대상으로는
   노출되지 않는다.
3. **알려진 한계 5가지(L19-48)**: 아래 각 절에서 대응하는 코드와 함께
   설명.
4. **검증(L50-56)**: `tests/fixtures/fbx/`의 실제 Maya·Blender
   익스포트로 비압축(7400/7500)·zlib 압축·좌표축 정규화·Connections
   필터링을 전부 실제 파일로 확인했다(fixture 자체의 출처·라이선스는
   `tests/fixtures/fbx/README.md`).

## L58-76: import·상수·저수준 예외 타입

```python
_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_SCALAR_FMT = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
_ARRAY_ELEM_FMT = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}
_LOW_LEVEL_ERRORS = (struct.error, zlib.error, UnicodeDecodeError, IndexError, ValueError, TypeError)
```

FBX 바이너리 포맷의 프로퍼티 타입 코드(1바이트 문자)를 파이썬
`struct` 포맷 문자열로 매핑하는 테이블 — 스칼라(`Y/C/I/F/D/L`)와
배열(`f/d/l/i/b`)이 서로 다른 테이블에 있다는 게 핵심 구조.
`_LOW_LEVEL_ERRORS`는 이 파일 전체의 예외 처리 철학을 담은
튜플이다 — "파싱 중 뭐가 잘못됐든 사용자에게는 `err.corrupted`
하나로 통일해서 보여준다"(model3d.py가 `trimesh.load()` 실패를
전부 `except Exception`으로 뭉뚱그리는 것과 같은 원칙, 다만 여기서는
`Exception` 전체가 아니라 "이 정도는 손상된 파일이라 봐도 되는"
구체적인 타입 목록으로 좁혔다 — `ConversionError` 자체나 진짜
프로그래밍 버그(예상 못한 `AttributeError` 등)는 그대로 전파되게
하려는 의도). `TypeError`가 포함된 이유는 코드 리뷰 중 추가된
방어 — `Vertices`가 스칼라 타입 코드로 잘못 저장된 손상 파일에서
`len(flat)`이 던질 수 있는 예외까지 커버한다.

## L79-94: `_FbxNode` — 파싱된 노드 트리의 최소 표현

```python
class _FbxNode:
    __slots__ = ("name", "properties", "children")
```

FBX 바이너리는 재귀적인 노드 트리 구조다(이름 + 프로퍼티 리스트 +
자식 노드 리스트, XML의 element와 비슷하다고 생각하면 된다).
`__slots__`를 쓴 건 큰 씬(수천 개 노드)에서 메모리를 아끼기 위한
전형적인 최적화. `find`/`find_all`은 자식 중 특정 이름을 가진
노드를 찾는 유틸 — DOM의 `querySelector`와 비슷한 역할을 아주
단순하게 구현한 것.

## L97-130: `_read_properties` — 프로퍼티 하나씩 파싱

타입 코드 1바이트를 읽고 세 갈래로 분기한다:
- **스칼라(`_SCALAR_FMT`에 있음)**: 고정 크기라 `struct.unpack_from`
  한 번으로 끝.
- **배열(`_ARRAY_ELEM_FMT`에 있음, L106-121)**: `array_length`·
  `encoding`·`compressed_length` 3개의 uint32 헤더가 먼저 온다.
  `encoding == 0`이면 비압축 raw bytes를 그대로 읽고, `encoding == 1`
  이면 `zlib.decompress()`로 압축을 푼다(L114-118) — 압축 해제 후
  크기가 선언된 `array_length * elem_size`와 다르면 손상으로 간주해
  즉시 실패(L117-118, 조용히 잘린 데이터를 쓰지 않기 위한 방어).
  이 압축 경로가 바로 알려진 한계 목록에서 "실사용 검증"이 필요했던
  부분 — Blender의 Suzanne fixture로 실제 압축 배열을 직접
  디코딩해 참조 OBJ와 좌표까지 대조했다(README 참고).
- **문자열/raw(`S`/`R`)**: 4바이트 길이 접두 + 그만큼의 바이트.
  `S`는 UTF-8 문자열로 디코딩, `R`은 원본 바이트 그대로(raw 프로퍼티,
  이 모듈에서는 실제로 쓰이지 않지만 파싱은 정상적으로 통과해야
  뒤따르는 노드 파싱이 안 깨진다).

알 수 없는 타입 코드(L128-129)는 명확한 `ConversionError`.

## L133-156: `_read_node` — 노드 하나(헤더+프로퍼티+자식) 재귀 파싱

가장 까다로운 부분은 **버전에 따라 헤더 필드 크기가 다르다**는 점
(L134-139) — FBX 7500부터 `EndOffset`/`NumProperties`/
`PropertyListLen`이 uint32(4바이트씩, 총 12바이트)에서 uint64(8바이트씩,
총 24바이트)로 바뀐다. `use_64bit` 플래그 하나로 `struct` 포맷
문자열만 바꿔 전체 파싱 로직을 그대로 재사용한다.

**널 레코드 처리(L140-141)**: `end_offset == 0`이면 이 위치는 자식
목록의 끝을 알리는 13/25바이트짜리 특수 레코드다 — 이름도 프로퍼티도
없이 헤더 뒤에 `name_len(=0)` 1바이트만 더 있다.

**자식 파싱의 미묘한 분기(L148-154)**:
```python
if pos < end_offset:
    while pos < end_offset:
        child, pos = _read_node(buf, pos, use_64bit)
        if child is None:
            break
        node.children.append(child)
if pos != end_offset:
    raise ConversionError(...)
```
FBX 바이너리는 **자식이 없는 리프 노드는 널 레코드 자체를 아예
생략한다**(공식 문서가 없는, 리버스 엔지니어링으로 알려진 포맷
특유의 관례). 그래서 프로퍼티까지 다 읽은 시점에 `pos`가 이미
`end_offset`과 같으면(자식 없음) `while` 루프에 아예 안 들어가고,
그렇지 않으면(자식이 있음, 마지막엔 널 레코드로 끝남) 루프를 돈다.
마지막 `if pos != end_offset`은 이 두 경우 모두를 소화한 뒤 그래도
위치가 안 맞으면 파싱 자체가 잘못됐다는 뜻이라 명확히 실패시키는
전체 파일의 정합성 체크다.

## L159-172: `_parse` — 파일 전체 진입점

매직 헤더 23바이트(`_MAGIC`) 확인 → 4바이트 버전 → `use_64bit` 결정
→ `pos=27`부터 최상위 노드를 반복해서 읽는다. 최상위에서도 널
레코드를 만나면(`node is None`) 바로 멈추는데, 이건 실제 FBX
파일에는 최상위 널 레코드 뒤에 썸네일·푸터 같은 노드 트리가 아닌
잡다한 바이너리가 더 있기 때문 — 이 파일은 그 뒤를 아예 안 본다
(형태 데이터는 이미 다 읽었으므로 필요 없음).

## L175-204: `_axis_matrix` — 좌표축 정규화 행렬 계산

알려진 한계 목록에는 없지만(오히려 "해결한" 부분) 이 파일에서 가장
수학적인 함수다. FBX의 `GlobalSettings/Properties70`에서
`CoordAxis`/`UpAxis`/`FrontAxis`(각 0/1/2 = X/Y/Z 중 어느 축인지)와
그 부호(`*Sign`)를 읽어 3×3 행렬을 만든다:

```python
matrix[0][coord_axis] = float(coord_sign)
matrix[1][up_axis] = float(up_sign)
matrix[2][front_axis] = float(front_sign)
```

행렬의 각 행이 "결과 좌표계의 X/Y/Z축이 원본의 어느 축에서 오는가"를
나타낸다 — 표준 Maya 축(`CoordAxis=0,UpAxis=1,FrontAxis=2`, 전부 부호
+1)이면 이 행렬은 항등행렬이 된다. Blender가 "Z Up" 옵션으로 내보낸
파일은 `UpAxis=2`가 되고, 그러면 `matrix[1][2] = 1`이 돼 원본의 Z
성분이 결과의 Y 위치로 옮겨간다 — `tests/test_fbx.py`의
`test_z_up_axis_actually_normalized_to_y_up`이 이 사실 자체를 원본
저장값과 직접 대조해서 검증한다(단순히 "정점 개수가 맞다"가 아니라
"Z였던 값이 진짜로 Y 위치에 나타난다"까지 확인).

행렬식(`det`, L199-203)이 음수면 이 변환이 반사(거울상, 오른손↔왼손
좌표계 전환)를 포함한다는 뜻 — 이런 경우 삼각형의 정점 순서(winding)를
그대로 두면 노멀이 뒤집힌 것처럼 보이므로, `_extract_from_nodes`에서
`flip_winding` 플래그로 삼각형의 두 번째·세 번째 정점을 맞바꾼다
(L282-283, `_extract_from_nodes` 절 참고).

## L207-213: `_apply_axis` — 행렬-벡터 곱

`_axis_matrix`가 만든 3×3 행렬을 정점 하나(x, y, z)에 적용하는 순수
함수. 딱 행렬-벡터 곱 공식 그대로라 특별한 트릭은 없다.

## L216-236: `_connected_geometry_ids` — Connections 기반 필터링

FBX 씬은 `Objects` 아래 여러 `Geometry`가 있을 수 있는데, 그중
일부는 실제로 화면에 보이는 Model에 연결 안 된 "고아" 데이터일 수
있다(숨겨진 프록시, 백업용 등). `Connections` 노드는 `C` 자식들로
`("OO", 소스ID, 대상ID)` 형태의 오브젝트-오브젝트 연결을 나열하는데,
이 함수는 그중 대상이 실제 `Model`인 연결만 골라 그 소스(Geometry)
ID 집합을 만든다.

**안전한 기본값이 두 겹으로 있다는 점이 중요하다**:
1. `Connections` 노드 자체가 없으면(L226-227) 바로 모든 Geometry
   포함.
2. `Connections`는 있지만 실제로 Model에 연결된 게 하나도 안 잡히면
   (L236, `connected & all_geometry_ids if connected else
   all_geometry_ids`) 그래도 모든 Geometry를 포함 — "잘못 걸러내서
   조용히 데이터가 사라지는 것"보다 "약간 더 포함시키는 것"이 훨씬
   안전하다는 이 프로젝트 전반의 원칙(TARGETS의 "가능한 것만
   노출"과는 반대 방향이지만 같은 "조용한 유실 방지" 철학).

## L239-243: `_triangulate_fan` — 다각형 삼각형화

```python
def _triangulate_fan(polygon: list[int]):
    for i in range(1, len(polygon) - 1):
        yield (polygon[0], polygon[i], polygon[i + 1])
```

FBX의 `PolygonVertexIndex`는 4각형 이상의 폴리곤을 그대로 담을 수
있는데, 이후 파이프라인(trimesh export)은 삼각형만 다룬다. 첫
정점을 고정하고 나머지를 순서대로 이어 부채꼴로 쪼개는 가장 단순한
방법(fan triangulation) — 볼록 다각형은 항상 정확하지만 오목
다각형은 삼각형이 메시 경계 밖으로 튀어나올 수 있다(모듈 docstring
알려진 한계 5번). 실제 fixture의 정육면체(4각형)·Suzanne(대부분
4각형)은 전부 볼록이라 이 한계에 걸리지 않는다.

## L246-300: `_extract_from_nodes` — 이 파일의 핵심 로직

`parse_geometry`(파일 IO)와 분리된 이유부터 짚을 만하다 — **테스트
용이성 때문에 리팩터링된 함수**다. 노드 트리 레벨의 엣지 케이스
(Objects 없음·Connections 없음·빈 프로퍼티 배열·범위 벗어난 인덱스)를
검증하려면 실제로 그런 조건을 만족하는 손상된 바이너리 FBX 파일을
새로 인코딩해야 하는데, 그 대신 `_FbxNode`를 파이썬 코드로 직접
조립해서 이 함수 하나만 단위 테스트할 수 있게 분리했다
(`tests/test_fbx.py::TestFbxRobustness` 참고).

동작 순서:
1. `Objects` 노드가 없으면 즉시 실패(L253-255) — FBX 6.x가 여기
   걸린다(알려진 한계 1번).
2. 좌표축 행렬·Connections 필터를 미리 한 번만 계산(L257-259).
3. `Objects` 아래 모든 `Geometry`를 순회하며(L264), Connections
   필터를 통과 못 하면 건너뛴다(L265-266) — 단, `geom.properties`가
   비어있으면(ID 자체가 없는 비정상 케이스) 단락 평가로 무조건
   포함시킨다(안전한 기본값).
4. `Vertices`/`PolygonVertexIndex` 둘 다 있는 Geometry만 처리
   (L269-270, 둘 중 하나라도 없으면 조용히 skip).
5. 정점 좌표를 3개씩 끊어 축 변환 적용 후 누적 리스트에 추가
   (L271-274) — `base`(L272)는 여러 Geometry를 하나의 정점/면
   리스트로 합칠 때 인덱스가 겹치지 않게 하는 오프셋.
6. `PolygonVertexIndex`를 순회하며 음수(비트 NOT으로 인코딩된 폴리곤
   마지막 정점, `~idx`)를 만나면 그 폴리곤이 끝난 것으로 보고
   fan triangulation → (필요하면 winding 뒤집기) → 누적(L276-285).
7. **경계 검증(L289-299, 코드 리뷰 중 추가)**: 최종적으로 정점·면이
   하나도 없으면 실패(FBX 6.x·빈 파일 등), 그리고 신규로 추가된
   방어 — 폴리곤 인덱스가 실제 정점 개수 범위를 벗어나면(손상된
   파일) 여기서 명확히 실패시킨다. 이 검증이 없으면 `load_trimesh`가
   `process=False`로 trimesh에 넘기기 때문에(아래 절 참고) trimesh
   자체 검증도 기대할 수 없어, 깨진 인덱스가 그대로 export 단계까지
   흘러가 알 수 없는 방식으로 망가진 출력 파일이 나올 위험이 있었다.

## L303-318: `parse_geometry` — 공개 API 1 (파일 → 정점/면)

파일을 바이트로 읽고(`OSError`는 `err.disk`) `_parse()`로 노드
트리를 만든 뒤(저수준 파싱 오류는 `err.corrupted`) `_extract_from_nodes`
로 위임한다. `ConversionError`는 그대로 다시 던진다(L311-312) —
`_parse` 내부에서 이미 의미 있는 메시지를 담아 던진 것을 여기서
뭉개면 안 되기 때문(다른 저수준 예외만 새로 감싼다).

## L321-333: `load_trimesh` — 공개 API 2 (파일 → Trimesh 객체)

`model3d.py`의 `convert_3d()`가 소스 확장자가 `.fbx`일 때 호출하는
진입점. `parse_geometry`로 얻은 (vertices, faces)를 numpy 배열로
바꿔 `trimesh.Trimesh(..., process=False)`를 만든다.
**`process=False`가 중요**하다 — trimesh의 기본 로드 처리(중복
정점 병합, 퇴화 삼각형 제거 등)를 여기서는 적용하지 않는다. 이
파서가 이미 유효한 메시를 만들었다고 보고, 후속 export 단계에서
trimesh가 임의로 데이터를 바꾸지 않게 하려는 의도 — 다만 이 때문에
`tests/test_fbx.py`의 왕복 테스트가 obj/stl처럼 텍스트나
비인덱스(triangle-soup) 포맷으로 나갔다가 **다시 로드**할 때는
trimesh가 그 시점의 기본 `process=True`로 근접 좌표를 병합해 정점
수가 살짝 줄 수 있다(예: Suzanne 507→505) — 이건 이 파서의 결함이
아니라 trimesh 재로드 처리의 특성이라, glb처럼 인덱스를 그대로
보존하는 바이너리 포맷으로 정확한 정점 수 일치를 확인하고 텍스트
포맷은 면(위상) 개수만 비교하도록 테스트를 나눴다.

---

## 이 파일에 대해 이해했는지 확인할 질문 예시

- FBX 7500 전후로 노드 헤더 필드 크기가 왜 다르며, 이 코드는 그
  차이를 어디서 어떻게 흡수하는가?
- 자식이 없는 리프 노드에서 널 레코드가 생략된다는 사실을 모른 채
  `_read_node`를 짰다면 어떤 파일에서 어떤 식으로 파싱이 깨졌을까?
- `_connected_geometry_ids`가 "안전한 기본값"을 두 겹으로 둔 이유는
  무엇이고, 만약 반대로 "모르면 제외"를 기본값으로 했다면 어떤
  실사용 시나리오에서 문제가 생겼을까?
- `_extract_from_nodes`를 `parse_geometry`에서 분리한 이유는? 만약
  분리하지 않았다면 "Connections 노드가 없는 경우"를 검증하는
  테스트를 어떻게 작성해야 했을까?
- `load_trimesh`가 `process=False`로 Trimesh를 만드는데, 왜 텍스트
  포맷으로 왕복하면 정점 개수가 줄 수 있는가? 이게 이 파서의
  버그인지 아닌지 어떻게 판단했는가?
