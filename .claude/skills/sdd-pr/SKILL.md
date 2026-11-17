---
name: sdd-pr
description: 현재 브랜치의 PR을 템플릿대로 만든다(스펙 연결, 확인 결과, AI 서명 없음). 머지는 사람이 한다.
allowed-tools: Bash(git status *) Bash(git log *) Bash(git diff *) Bash(gh pr create *) Bash(gh pr view *) Bash(python3 scripts/*)
---

# /sdd-pr — PR

1. 확인: `cd app && python -m pytest -q tests`, `python3 scripts/check_specs.py`, `python3 scripts/commit_lint.py --range origin/main..HEAD` 통과,
   `tasks.md` 체크, 기준선 문서 갱신.
2. push는 사용자 확인 후: `git push -u origin <브랜치>`.
3. 제목 = 커밋 규칙 형식 `<유형>(<범위>): <요약>` (스쿼시 머지 커밋 제목이 된다).
4. 본문 = `.github/pull_request_template.md`를 채운 것: 관련 스펙(SPEC-NNN 필수), 요구사항, 무엇·왜, 확인 방법(테스트 출력 요약, 평가 표, 스크린샷), 체크리스트.
   임시 파일에 써서 `gh pr create --base main --title "<제목>" --body-file <파일> --label "<유형 라벨>" --label "area: …"`.
5. **금지:** 본문·제목에 `Generated with`, 🤖, 세션 링크, AI 도구 이름. (CI가 지우지만 처음부터 넣지 않는다)
6. PR 주소를 알려 준다. 머지·자동 머지는 하지 않는다 — 사람이 CI 녹색을 보고 결정한다.
