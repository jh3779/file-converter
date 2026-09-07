# FBX 테스트 픽스처 — 출처·라이선스

이 디렉터리의 파일 7개는 [ufbx](https://github.com/ufbx/ufbx) 저장소의
`data/` 폴더(그 저장소 자체 테스트 스위트용 실제 Maya/Blender 익스포트
샘플)에서 그대로 가져온 것이다. 바이트 단위로 원본과 동일함을
`shasum -a 256`로 직접 확인했다(아래 표).

- **저장소**: https://github.com/ufbx/ufbx
- **고정 커밋**: `fcc5d6ba444cfd3eb80677dba5e37e493941abe5`
- **라이선스**: 저장소 루트 `LICENSE` 파일이 MIT/Public Domain(Unlicense)
  이중 라이선스를 선언한다(`data/` 하위에 별도 라이선스 파일 없음 —
  `data/README.md`, `data/LICENSE` 등 확인, 전부 404 → 저장소 루트
  라이선스가 그대로 적용됨). 두 라이선스 모두 재배포·수정·상업적 사용을
  포함해 사실상 제한이 없어(MIT: 저작권 고지 유지 조건, Unlicense: 조건
  없음), 이 프로젝트의 테스트 스위트에 그대로 포함해도 문제없다.
- **README 발췌**: 저장소 README가 "Public dataset: 4.7GB / 323 files —
  Loaded, validated, and compared against reference .obj files"라고
  자체 테스트 스위트의 일부임을 설명한다 — `data/`는 서드파티 자산이
  아니라 이 저장소 자체가 만들고 관리하는 테스트 픽스처다.

## 파일 목록

| 파일 | 원본 경로 | 용도 |
|---|---|---|
| `maya_cube_7400_binary.fbx` | `data/maya_cube_7400_binary.fbx` | 비압축 FBX 7400(4바이트 오프셋), 정점 8·폴리곤 6(4각형) 기본 큐브 |
| `maya_cube_7500_binary.fbx` | `data/maya_cube_7500_binary.fbx` | 비압축 FBX 7500(8바이트 오프셋), 위와 동일한 큐브 |
| `maya_cube_6100_binary.fbx` | `data/maya_cube_6100_binary.fbx` | FBX 6.x(지원 범위 밖) — Geometry가 `Objects` 아래 없이 다른 오브젝트 모델을 씀, 명확한 오류로 거부되는지 확인용 |
| `blender_282_suzanne_7400_binary.fbx` | `data/blender_282_suzanne_7400_binary.fbx` | zlib 압축 배열 실사용 검증용(정점 507·폴리곤 500) |
| `blender_282_suzanne.obj` | `data/blender_282_suzanne.obj` | 위 파일의 참조 OBJ(정점 개수·좌표 대조용) |
| `blender_340_z_up_7400_binary.fbx` | `data/blender_340_z_up_7400_binary.fbx` | Z-up 씬(Cube+Light+Camera+Cone), 축 정규화·Connections 필터링 검증용 |
| `blender_340_z_up.obj` | `data/blender_340_z_up.obj` | 위 파일의 참조 OBJ(Cube만 포함 — Blender가 선택된 오브젝트만 내보낸 것으로 보임) |

## 검증 방법(재현 가능)

```bash
# 커밋 고정 후 data/<파일명>을 그대로 받아 SHA256 비교
curl -s "https://raw.githubusercontent.com/ufbx/ufbx/fcc5d6ba444cfd3eb80677dba5e37e493941abe5/data/<파일명>" \
  | shasum -a 256
shasum -a 256 tests/fixtures/fbx/<파일명>
# 두 해시가 일치함을 이 스파이크 프로덕션화 작업 중 7개 파일 전부 확인했다.
```
