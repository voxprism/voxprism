#!/bin/bash
# Claude Code SessionStart 훅: git 훅 연결 + 지금 상태 요약(이 출력은 Claude의 맥락에 들어감)
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" 2>/dev/null || exit 0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git config core.hooksPath .githooks 2>/dev/null
  git config commit.template .gitmessage 2>/dev/null
fi

echo "## VoxPrism 세션 시작 정보"
echo "- 브랜치: $(git branch --show-current 2>/dev/null || echo '?')  · 변경 파일: $(git status --porcelain 2>/dev/null | wc -l)개"
echo "- 최근 커밋:"
git log --oneline -3 2>/dev/null | sed 's/^/  - /'
echo "- 진행 중·승인·초안 스펙:"
found=0
for f in specs/[0-9][0-9][0-9]-*/spec.md; do
  [ -f "$f" ] || continue
  st=$(sed -n 's/^status: *//p' "$f" | head -1)
  case "$st" in
    "진행 중"|"승인"|"초안")
      found=1
      open=$(grep -c '^- \[ \] T-' "$(dirname "$f")/tasks.md" 2>/dev/null || echo 0)
      echo "  - $(sed -n 's/^id: *//p' "$f" | head -1) $(sed -n 's/^title: *//p' "$f" | head -1) [$st] 남은 작업 ${open}개" ;;
  esac
done
[ "$found" = 1 ] || echo "  - 없음 (새 기능은 /sdd-spec 부터)"
echo "- 규칙: AGENTS.md (SDD 순서, 비밀 읽기 금지, 커밋·PR에 AI 서명 금지, 서버 변경은 사용자 확인)"
echo "- 인계 문서: docs/06-인수인계.md 의 '지금 상태'와 '다음 할 일'을 먼저 읽을 것"
exit 0
