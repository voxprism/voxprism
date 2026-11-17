---
name: sdd-commit
description: 변경을 저장소 커밋 규칙(Conventional Commits 한국어 요약 + Refs 꼬리말, AI 서명 없음)으로 커밋한다. 커밋할 때는 항상 이 규칙을 쓴다.
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git add *) Bash(git commit *) Bash(git log *)
---

# /sdd-commit — 커밋

1. `git status`, `git diff`로 변경을 확인한다. `secrets/`, `*.env`, `infra/state.env`, 키 파일이 스테이지되지 않았는지 본다.
2. 의도별로 나눠 커밋한다(한 커밋 = 한 가지 이유).
3. 메시지 형식 (자세한 규칙: CONTRIBUTING.md):
   ```text
   <유형>(<범위>): <한국어 요약, 50자 안팎, 마침표 없음>

   <본문: 무엇을, 왜. 한 줄 72자 안팎>

   Refs: SPEC-NNN, T-NN
   ```
   - 유형: feat fix docs spec refactor perf test build ci chore revert style
   - 범위: pipeline asr diarize overlap captions web api worker auth infra deploy eval docs spec repo
   - `feat`·`fix`·`perf`는 `Refs: SPEC-NNN` 필수.
4. **금지:** `Co-Authored-By`(AI), `Generated with …`, `Claude-Session`, 🤖, AI 도구 이름·링크. 작성자는 git 설정 그대로 둔다.
5. 메시지는 임시 파일에 써서 `git commit -F <파일>` 또는 heredoc으로. `--no-verify` 금지 — 훅이 막으면 메시지를 고친다.
