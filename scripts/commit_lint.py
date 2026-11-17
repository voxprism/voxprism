#!/usr/bin/env python3
"""커밋 메시지 규칙 검사기 (git 훅과 CI가 함께 씀).

  commit_lint.py --fix FILE        commit-msg 훅: AI 도구 서명 줄을 지우고 형식을 검사(파일을 고쳐 씀)
  commit_lint.py --check FILE      파일 하나를 검사만
  commit_lint.py --title "제목"     PR 제목(= 스쿼시 커밋 제목) 형식 검사
  commit_lint.py --range A..B      범위 안의 모든 커밋 검사(CI). 서명 줄이 있으면 실패

규칙 원문: CONTRIBUTING.md 「커밋 메시지」
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ("feat", "fix", "docs", "spec", "refactor", "perf", "test", "build", "ci", "chore", "revert", "style")
NEEDS_SPEC = ("feat", "fix", "perf")          # 동작을 바꾸는 유형은 스펙을 가리켜야 함 (SDD)
HEADER_RE = re.compile(
    r"^(?P<type>" + "|".join(TYPES) + r")(?:\((?P<scope>[a-z0-9][a-z0-9-]*)\))?(?P<bang>!)?: (?P<subject>\S.*)$")
SKIP_RE = re.compile(r"^(Merge |Revert \"|fixup! |squash! |amend! )")
HEADER_MAX = 72
SPEC_RE = re.compile(r"\bSPEC-(\d{3})\b")

# 커밋·PR에 남기지 않는 자동 생성 서명 (사람 공동 작성자의 Co-authored-by 는 그대로 둔다)
AI_TOOLS = r"(claude|anthropic|copilot|chatgpt|openai|gpt-\d|gemini|codex|cursor|devin|aider|windsurf)"
TRACE_RES = [
    re.compile(r"^\s*co-authored-by:.*" + AI_TOOLS, re.I),
    re.compile(r"^\s*co-authored-by:.*noreply@anthropic\.com", re.I),
    re.compile(r"generated (with|by)\b.*" + AI_TOOLS, re.I),
    re.compile(r"^\s*(claude-session|ai-session|session-url)\s*:", re.I),
    re.compile(r"(claude\.ai/code|claude\.com/claude-code|chatgpt\.com/codex)", re.I),
    re.compile("\U0001F916"),  # 🤖
]


def is_trace(line: str) -> bool:
    return any(r.search(line) for r in TRACE_RES)


def strip_traces(text: str) -> tuple[str, list[str]]:
    """서명 줄을 지운 메시지와 지운 줄 목록."""
    kept, removed = [], []
    for line in text.splitlines():
        (removed if is_trace(line) else kept).append(line)
    out = "\n".join(kept).rstrip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return (out + "\n") if out else "", removed


def _without_comments(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        if line.startswith("# ------------------------ >8"):
            break
        if line.startswith("#"):
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def spec_exists(num: str) -> bool:
    return any((ROOT / "specs").glob(f"{num}-*/spec.md"))


def check_header(header: str) -> list[str]:
    errs = []
    if SKIP_RE.match(header):
        return errs
    m = HEADER_RE.match(header)
    if not m:
        errs.append("첫 줄은 '<유형>(<범위>): <요약>' 형식이어야 합니다. "
                    f"유형: {', '.join(TYPES)} / 범위: 영어 소문자·숫자·하이픈. 예) feat(overlap): 배치 재인식 추가")
        return errs
    if len(header) > HEADER_MAX:
        errs.append(f"첫 줄이 {len(header)}자입니다. {HEADER_MAX}자 이내로 줄여 주세요(권장 50자).")
    if m["subject"].rstrip().endswith("."):
        errs.append("요약 끝에 마침표를 찍지 않습니다.")
    return errs


def check_message(text: str, where: str = "") -> list[str]:
    lines = _without_comments(text)
    if not lines:
        return [f"{where}메시지가 비어 있습니다."]
    header = lines[0]
    errs = [where + e for e in check_header(header)]
    if SKIP_RE.match(header):
        return errs
    if len(lines) > 1 and lines[1].strip():
        errs.append(f"{where}첫 줄 다음은 빈 줄이어야 합니다.")
    traces = [ln for ln in lines if is_trace(ln)]
    if traces:
        errs.append(f"{where}자동 생성 서명이 있습니다: {traces[0][:60]}")
    m = HEADER_RE.match(header)
    body = "\n".join(lines[1:])
    refs = SPEC_RE.findall(body) + SPEC_RE.findall(header)
    if m and m["type"] in NEEDS_SPEC and not re.search(r"^Refs:.*SPEC-\d{3}", body, re.M):
        errs.append(f"{where}'{m['type']}' 커밋은 꼬리말에 'Refs: SPEC-NNN'이 필요합니다(SDD). "
                    "스펙 없는 잡무라면 유형을 chore/ci/docs/build로 바꿔 주세요.")
    for num in sorted(set(refs)):
        if not spec_exists(num):
            errs.append(f"{where}SPEC-{num} 폴더(specs/{num}-*/spec.md)가 없습니다.")
    return errs


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fix", metavar="FILE")
    g.add_argument("--check", metavar="FILE")
    g.add_argument("--title")
    g.add_argument("--range", metavar="A..B")
    a = ap.parse_args()

    if a.fix:
        p = Path(a.fix)
        text, removed = strip_traces(p.read_text(encoding="utf-8"))
        if removed:
            p.write_text(text, encoding="utf-8")
            print(f"[commit-msg] 자동 생성 서명 {len(removed)}줄을 지웠습니다.", file=sys.stderr)
        errs = check_message(text)
    elif a.check:
        errs = check_message(Path(a.check).read_text(encoding="utf-8"))
    elif a.title is not None:
        errs = check_header(a.title.strip())
        if is_trace(a.title):
            errs.append("PR 제목에 자동 생성 표시가 있습니다.")
    else:
        out = git("log", "--no-merges", "--format=%H%x1f%B%x1e", a.range)
        errs = []
        for rec in filter(None, (r.strip("\n") for r in out.split("\x1e"))):
            sha, _, msg = rec.partition("\x1f")
            errs += check_message(msg, where=f"{sha[:8]}: ")
    if errs:
        print("커밋 메시지 규칙을 지키지 않았습니다 (CONTRIBUTING.md 참고):", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
