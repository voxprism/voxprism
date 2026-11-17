# 기여 가이드

VoxPrism은 **스펙 주도 개발(SDD)**을 합니다. 코드보다 스펙이 먼저이고, 모든 변경은 브랜치 → PR → CI → 머지 순서로 들어갑니다.
절차 전체는 [docs/05-SDD-개발-프로세스.md](docs/05-SDD-개발-프로세스.md), AI 에이전트 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.

## 처음 한 번

```bash
git clone https://github.com/voxprism/voxprism.git && cd voxprism
./scripts/setup-dev.sh          # git 훅(commit-msg·pre-commit·pre-push)과 커밋 메시지 틀 연결
python3 -m venv .venv && . .venv/bin/activate && pip install -r app/requirements-ci.txt
cd app && python -m pytest -q tests
```

## 브랜치

| 형식 | 예 | 쓰임 |
| --- | --- | --- |
| `<유형>/spec-NNN-<짧은-이름>` | `feat/spec-008-sound-captions` | 스펙이 있는 변경 |
| `<유형>/<짧은-이름>` | `docs/fix-typo`, `ci/cache-pip` | 스펙이 필요 없는 변경 |

`main`은 보호됩니다: 직접 push·강제 push 금지, PR과 CI(`test`, `secret-scan`, `pr-hygiene`) 통과가 필요합니다. 머지는 **스쿼시 머지**만 씁니다.

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/) 형식에 한국어 요약을 씁니다. `.githooks/commit-msg`가 검사하고, `git commit`(메시지 없이)을 하면 `.gitmessage` 틀이 열립니다.

```text
<유형>(<범위>): <요약>

<본문 — 무엇을, 왜>

Refs: SPEC-NNN, T-NN
Closes #12
```

| 규칙 | 내용 |
| --- | --- |
| 유형 | 아래 표 중 하나 |
| 범위 | 영어 소문자: `pipeline` `asr` `diarize` `overlap` `captions` `web` `api` `worker` `auth` `infra` `deploy` `eval` `docs` `spec` `repo` `brand` |
| 요약 | 한국어, 50자 안팎(최대 72자), 명령형 현재("추가", "고침"), 끝에 마침표 없음 |
| 본문 | 무엇을 왜 바꿨는지. 어떻게는 코드가 말해 줌. 한 줄 72자 안팎 |
| 꼬리말 | `feat`·`fix`·`perf`는 `Refs: SPEC-NNN` 필수(SDD). 작업 번호 `T-NN`, 이슈 `Closes #N` |
| 큰 변경 | `feat(api)!:` + 꼬리말 `BREAKING CHANGE: …` |
| 금지 | AI 도구 서명(`Co-Authored-By: <AI>`, `Generated with …`, 세션 링크, 🤖). 훅이 자동으로 지우고, CI가 다시 검사합니다 |

| 유형 | 뜻 | 라벨 | 스펙 |
| --- | --- | --- | --- |
| `feat` | 새 기능·동작 변경 | ✨ feat | 필수 |
| `fix` | 스펙대로 동작하지 않던 것 고침 | 🐛 bug | 필수(기존 스펙) |
| `perf` | 속도·자원 개선 | ⚡ perf | 필수 |
| `spec` | 스펙 문서(spec·plan·tasks) 작성·개정 | 📐 spec | 그 스펙 |
| `refactor` | 동작이 같은 구조 개선 | ♻️ refactor | 권장 |
| `test` | 테스트·평가 | ✅ test | — |
| `docs` | 문서 | 📝 docs | — |
| `style` | 포맷·공백 | 🔧 chore | — |
| `build` | 의존성·패키징 | 🔧 chore | — |
| `ci` | GitHub Actions·훅·스크립트 | 🔧 chore | — |
| `chore` | 그 밖의 잡무 | 🔧 chore | — |
| `revert` | 되돌리기 | — | — |

**좋은 예**

```text
feat(overlap): 화자 확신이 낮으면 단어 재배정을 하지 않음

겹친 구간의 1·2위 화자 조합 점수 차가 0.05 미만이면 원래 배정을 유지하고
복원 단어에만 uncertain 표시를 남긴다. 잘못된 재배정이 cpCER을 올리던 문제.

Refs: SPEC-003, T-05
```

## PR

1. 제목은 커밋 규칙 형식(스쿼시 머지 커밋 제목이 됩니다).
2. 본문은 템플릿을 채웁니다: **관련 스펙**, 무엇·왜, 확인 방법, SDD 체크리스트.
3. `app/whosaid/`, `app/deploy/`, `infra/`를 바꾸면 본문에 `SPEC-NNN`이 없을 때 CI가 실패합니다.
4. 파이프라인(SPEC-002·003) 변경은 평가셋 v2 결과 표, 화면 변경은 스크린샷을 붙입니다.
5. 라벨: 유형 1개 + 영역 1개(`area: pipeline|web|infra|eval`) + 필요하면 우선순위.

## 이슈

템플릿 4가지: 🐛 버그 리포트 · ✨ 기능 제안(→ 스펙 필요) · 📐 스펙 작성·개정 · 📝 문서. 보안 문제는 공개 이슈 대신 [SECURITY.md](SECURITY.md)를 따릅니다.

## 라벨

`.github/labels.json`이 기준입니다. 바꾼 뒤 `./scripts/sync_labels.sh`로 저장소에 반영합니다.
