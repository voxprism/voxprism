#!/bin/bash
# .github/labels.json 의 라벨을 GitHub 저장소에 맞춥니다.  ./scripts/sync_labels.sh [--prune]
#   --prune : 목록에 없는 라벨은 지움 (GitHub 기본 라벨 정리용)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
python3 - "$REPO" "${1:-}" <<'PY'
import json, subprocess, sys
repo, prune = sys.argv[1], sys.argv[2] == "--prune"
want = json.load(open(".github/labels.json", encoding="utf-8"))
have = json.loads(subprocess.run(["gh", "label", "list", "-R", repo, "--limit", "200", "--json", "name"],
                                 check=True, capture_output=True, text=True).stdout)
have_names = {l["name"] for l in have}
for l in want:
    subprocess.run(["gh", "label", "create", l["name"], "-R", repo, "--color", l["color"],
                    "--description", l["description"], "--force"], check=True, capture_output=True)
    print(("갱신 " if l["name"] in have_names else "추가 ") + l["name"])
if prune:
    for name in sorted(have_names - {l["name"] for l in want}):
        subprocess.run(["gh", "label", "delete", name, "-R", repo, "--yes"], check=True, capture_output=True)
        print("삭제 " + name)
PY
