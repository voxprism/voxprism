#!/usr/bin/env python3
"""PR 위생 검사 (GitHub Actions `pr-hygiene`).

1. PR 제목·본문에서 AI 도구 서명(🤖 Generated with …, 세션 링크 등)을 지운다 — GitHub API로 PR 수정
2. PR 제목이 커밋 규칙 형식인지 검사 (스쿼시 머지 커밋 제목이 됨)
3. SDD: app/whosaid · app/deploy · infra 를 바꾼 PR은 본문에 SPEC-NNN 이 있어야 하고 그 스펙 폴더가 있어야 함

환경 변수: GITHUB_EVENT_PATH, GITHUB_REPOSITORY, GH_TOKEN(수정용), BASE_SHA, HEAD_SHA
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from commit_lint import check_header, is_trace, spec_exists, strip_traces  # noqa: E402

CODE_PATHS = ("app/whosaid/", "app/deploy/", "infra/")


def gh_patch(repo: str, number: int, **fields: str) -> None:
    args = ["gh", "api", "-X", "PATCH", f"repos/{repo}/pulls/{number}"]
    for k, v in fields.items():
        args += ["-f", f"{k}={v}"]
    subprocess.run(args, check=True, capture_output=True)


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event["pull_request"]
    repo, number = os.environ["GITHUB_REPOSITORY"], pr["number"]
    title, body = pr.get("title") or "", pr.get("body") or ""
    errors: list[str] = []

    # 1) 서명 지우기
    new_body, removed = strip_traces(body)
    new_title = title
    if is_trace(title):
        new_title = re.sub("\U0001F916", "", title).strip()
    if removed or new_title != title:
        try:
            gh_patch(repo, number, **({"body": new_body} if removed else {}),
                     **({"title": new_title} if new_title != title else {}))
            print(f"PR에서 자동 생성 서명 {len(removed)}줄을 지웠습니다.")
            body, title = new_body, new_title
        except subprocess.CalledProcessError:
            errors.append("PR 본문의 자동 생성 서명을 지우지 못했습니다(권한). 직접 지워 주세요.")

    # 2) 제목 형식
    errors += [f"PR 제목: {e}" for e in check_header(title.strip())]

    # 3) 스펙 연결
    base, head = os.environ.get("BASE_SHA"), os.environ.get("HEAD_SHA")
    changed = subprocess.run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout.split()
    code_changed = [p for p in changed if p.startswith(CODE_PATHS)]
    specs = sorted(set(re.findall(r"\bSPEC-(\d{3})\b", body + " " + title)))
    if code_changed:
        if not specs:
            errors.append("코드(app/whosaid, app/deploy, infra)를 바꾼 PR은 본문 '관련 스펙'에 SPEC-NNN 이 필요합니다. "
                          f"바뀐 파일 예: {code_changed[0]}")
        for num in specs:
            if not spec_exists(num):
                errors.append(f"SPEC-{num} 폴더(specs/{num}-*/spec.md)가 없습니다.")
    print(f"바뀐 파일 {len(changed)}개, 코드 {len(code_changed)}개, 연결된 스펙 {['SPEC-' + s for s in specs] or '없음'}")

    if errors:
        for e in errors:
            print(f"::error::{e}")
        return 1
    print("PR 위생 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
