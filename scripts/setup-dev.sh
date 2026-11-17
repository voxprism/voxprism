#!/bin/bash
# 개발 환경 한 번 설정: git 훅·커밋 메시지 틀 연결. 저장소를 새로 받은 뒤 한 번 실행합니다.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x .githooks/* scripts/*.py scripts/*.sh 2>/dev/null || true
git config core.hooksPath .githooks
git config commit.template .gitmessage
git config pull.rebase true
command -v python3 >/dev/null || { echo "python3 가 필요합니다" >&2; exit 1; }
echo "✓ git 훅 연결: commit-msg(서명 제거·형식 검사), pre-commit(비밀 검사), pre-push(main 직접 push 차단)"
echo "✓ 커밋 메시지 틀: .gitmessage"
[ -n "$(git config user.name)" ] && [ -n "$(git config user.email)" ] \
  || echo "! git user.name / user.email 을 설정하세요 (커밋 작성자)"
[ -f secrets/keys.env ] || echo "· 키 파일이 없습니다: mkdir -p secrets && cp infra/keys.env.example secrets/keys.env && chmod 600 secrets/keys.env"
[ -f infra/state.env ] || echo "· 서버 정보가 없습니다: infra/state.env.example 참고 (기존 서버면 운영자에게 받기, 새로 만들면 create_infra.sh)"
