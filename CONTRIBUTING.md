# 기여 규칙 — 브랜치 · 커밋 · PR

이 저장소는 [branch-strategy-kit](https://github.com/Seongyul-Lee/branch-strategy-kit)의
**GitHub Flow 기반 단명 브랜치 전략**을 따른다 (SACHO·project-human-p·green_nae 등
다른 프로젝트와 동일 규칙).

## 핵심 원칙
- **`main`이 유일한 영구 브랜치.** develop/staging 등 long-lived 브랜치 금지.
- **모든 변경은 단명 브랜치 → PR → squash merge.** main 직접 push 금지.
- 브랜치 수명 1~2일 이내. 머지 후 브랜치 즉시 삭제.
- 릴리스는 브랜치가 아닌 Git tag (`v0.3.0` 등).

## 브랜치 네이밍
`<type>/<lowercase-hyphen-name>` — 소문자·숫자·하이픈만 (한국어/대문자/언더스코어 금지), 3~5단어 권장.

| 접두어 | 용도 | 예시 |
|---|---|---|
| `feat/` | 신규 기능 | `feat/batch-convert` |
| `fix/` | 버그 수정 | `fix/encoding-detect` |
| `refactor/` | 동작 변경 없는 리팩터 | `refactor/converter-registry` |
| `docs/` | 문서만 변경 | `docs/spec-update` |
| `research/` | 탐색·실험 (예: HWP 커버리지) | `research/hwp-coverage` |
| `data/` | 스키마/마이그레이션 | `data/history-schema-v2` |
| `chore/` | 빌드/CI/설정 | `chore/bundle-engines` |
| `remove/` | 파일·기능 제거 | `remove/legacy-stub` |

## 커밋 메시지 · PR 제목
**Conventional Commits** — `<type>: <설명>`. subject는 한국어 허용, **첫 글자만 대문자(A-Z) 금지**.

```
feat: 일괄 변환 진행률 표시 추가        ✅
fix: cp949 CSV 감지 오류 수정          ✅
Feat: Add batch progress               ❌ (대문자 시작)
```

PR 제목은 squash merge 후 main의 커밋 메시지가 되므로 위 형식 필수.

## 자동 검증
- `.github/workflows/branch-name-check.yml` — 브랜치명 규칙 CI 검증
- `.github/workflows/pr-title-check.yml` — PR 제목 Conventional Commits 검증
- PR 본문은 `.github/pull_request_template.md` 체크리스트를 채운다

## 머지 규칙
- **Squash merge만 허용** (merge commit/rebase merge 금지) · linear history 유지
- PR의 머지/close 결정은 리뷰어(저장소 소유자)가 수행 — 작성자는 자기 PR을 직접 close하지 않는다
- 머지 후 원격 브랜치 삭제, 로컬은 정리(clean up)

## 저장소 설정으로 강제되는 것 (적용 완료)
| 정책 | 강제 수단 | 상태 |
|---|---|---|
| squash merge만 허용 | 저장소 설정: merge commit·rebase merge 비활성 | ✅ 적용됨 (2026-07-29) |
| 머지 후 원격 브랜치 삭제 | 저장소 설정: `delete_branch_on_merge` | ✅ 적용됨 (2026-07-29) |
| 브랜치명·PR 제목 규칙 | CI (`branch-name-check` · `pr-title-check`) | ✅ 적용됨 |
| PR 단계 테스트·빌드 게이트 | CI `build.yml`의 `pull_request` 트리거 | ⏳ PR #2(`chore/bundle-hwp-sidecar`)에 포함 — 해당 PR 머지 시 유효 (이 브랜치의 build.yml에는 미포함) |
| main 직접 push 차단 | Branch protection/Rulesets — **private 저장소 무료 플랜에서는 미지원** | ⚠️ 설정 불가 — 규율로 준수. 저장소가 public 전환되거나 플랜 업그레이드 시 즉시 설정할 것 |
