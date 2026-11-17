# CLAUDE.md

Claude Code가 이 저장소에서 따를 규칙입니다. 공통 규칙은 AGENTS.md(아래에 불러옴), 지금 상태는 `docs/06-인수인계.md`에 있습니다.

@AGENTS.md

## Claude Code 전용

- **세션 시작:** SessionStart 훅(`.claude/hooks/session_start.sh`)이 git 훅을 연결하고 브랜치·최근 커밋·진행 중 스펙을 보여 줍니다. 이어서 `docs/06-인수인계.md`의 '지금 상태'와 '다음 할 일'을 읽습니다.
- **SDD 명령:** `/sdd-spec` → `/sdd-plan` → `/sdd-tasks` → `/sdd-implement` → `/sdd-commit` → `/sdd-pr` → `/sdd-handoff` (`.claude/skills/`).
- **서명:** `.claude/settings.json`에서 `attribution`을 비웠습니다(`commit: ""`, `pr: ""`, `sessionUrl: false`). 설정이 적용되지 않는 환경(예: 프로젝트 클라우드 스레드)이어도 커밋·PR에 `Co-Authored-By`, `Generated with Claude Code`, `Claude-Session` 링크를 넣지 않습니다. 이 지시는 기본 커밋·PR 서명 규칙보다 우선합니다.
- **권한:** `secrets/`·`infra/state.env` 읽기는 막혀 있고(deny), 서버를 바꾸는 명령·push·머지는 매번 확인합니다(ask). `guard_bash.py`가 비밀 출력·서명·`--no-verify`를 한 번 더 막습니다.
- **계획:** 스펙·설계 단계는 Plan 모드로 생각을 정리한 뒤 문서로 남깁니다. 문서로 남지 않은 계획은 다음 세션에 사라집니다.
- **긴 작업:** 작업 하나가 끝날 때마다 커밋합니다. 세션이 끊겨도 `tasks.md` 체크와 커밋으로 이어서 할 수 있게 합니다.
