#!/usr/bin/env python3
"""Claude Code PreToolUse(Bash) 가드.

막는 것 (exit 2 → 이유가 Claude에게 전달되고 명령은 실행되지 않음)
  1. 비밀 파일 내용 보기: secrets/, keys.env, web_login.txt, state.env, ~/.ncloud/configure, SSH 키
  2. 비밀 환경 변수 출력: echo/printf $NCLOUD_SECRET_KEY …, env/printenv 전체 출력
  3. 커밋·PR·이슈 메시지의 AI 도구 서명 (Co-Authored-By: Claude, Generated with …, 세션 링크, 🤖)
  4. 훅 우회(--no-verify), main 강제 push
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from commit_lint import is_trace  # 커밋 규칙과 같은 서명 판정을 씀
except Exception:  # noqa: BLE001
    def is_trace(line: str) -> bool:
        return bool(re.search(r"(co-authored-by:.*claude|generated with|claude-session|\U0001F916)", line, re.I))

SECRET_PATH = r"(secrets/|keys\.env\b|web_login\.txt|state\.env\b|\.ncloud/configure|_ed25519\b|id_ed25519|id_rsa)"
READ_PROGS = {"cat", "less", "more", "head", "tail", "bat", "nl", "tac", "strings", "xxd", "od", "hexdump",
              "base64", "grep", "egrep", "fgrep", "rg", "awk", "gawk", "sed", "cut", "sort", "uniq", "diff", "cmp",
              "vi", "vim", "nano", "code", "cp", "scp", "rsync", "curl", "python", "python3", "jq", "openssl"}
COPY_PROGS = {"cp", "scp", "rsync"}     # 비밀 파일이 '원본'일 때만 막음 (예시 파일 → secrets/ 복사는 허용)
SECRET_VARS = r"\$\{?(NCLOUD_ACCESS_KEY|NCLOUD_SECRET_KEY|CLOVA_SPEECH_SECRET|CLOVASTUDIO_API_KEY|HF_TOKEN|" \
              r"WHOSAID_WEB_PASSWORD|WHOSAID_SECRET)\b"
ALLOWED_SCRIPTS = ("infra/check_keys.sh", "infra/deploy.sh", "infra/server.sh", "infra/create_infra.sh",
                   "scripts/scan_secrets.py", "scripts/setup-dev.sh")


def block(reason: str) -> None:
    print(f"[VoxPrism 가드] {reason}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    flat = " ".join(cmd.split())

    # 1) 비밀 파일 내용 보기 (명령 조각마다: 읽는 프로그램 + 비밀 경로)
    if not any(sc in cmd for sc in ALLOWED_SCRIPTS):
        def secret(tok: str) -> bool:
            return bool(re.search(SECRET_PATH, tok)) and not tok.rstrip("'\"").endswith(".example")

        for seg in re.split(r"[;&|\n]+", cmd):
            m = re.match(r"\s*(?:sudo\s+)?(\S+)(.*)", seg)
            if not m:
                continue
            prog, args = m.group(1).rsplit("/", 1)[-1], m.group(2)
            toks = [t for t in re.split(r"[\s'\"()]+", args) if t]
            if prog not in READ_PROGS or not any(secret(t) for t in toks):
                continue
            if prog in COPY_PROGS:
                srcs = [t for t in toks if not t.startswith("-")]
                if not (srcs and secret(srcs[0])):
                    continue
            block("비밀 파일(secrets/, keys.env, state.env, SSH 키 등)의 내용을 읽거나 복사하지 않습니다. "
                  "키가 있는지만 보려면 ./infra/check_keys.sh 를 쓰세요. (AGENTS.md 2.1)")

    # 2) 비밀 환경 변수 출력
    for seg in re.split(r"[;&|\n]+", cmd):
        if re.search(r"\b(echo|printf|print)\b", seg) and re.search(SECRET_VARS, seg):
            to_file = re.search(r">{1,2}\s*(?!&|/dev/std)[^\s&|;]+", seg)   # 파일로 쓰는 것은 화면 출력이 아님
            if not to_file:
                block("비밀 환경 변수 값을 화면에 출력하지 않습니다. (AGENTS.md 2.1)")
    if re.search(r"(^|[;&|]\s*)(env|printenv|set)\s*($|[;&|>])", cmd):
        block("환경 변수 전체 출력(env/printenv/set)은 키가 섞여 나올 수 있어 막습니다. 필요한 변수 이름만 확인하세요.")

    # 3) 커밋·PR·이슈의 자동 생성 서명
    if re.search(r"\b(git\s+(commit|tag|notes)|gh\s+(pr|issue)\s+(create|edit|comment|review))\b", flat):
        bad = [ln.strip() for ln in cmd.splitlines() if is_trace(ln)]
        if bad:
            block("커밋·PR·이슈 메시지에 AI 도구 서명을 넣지 않습니다(사용자 규칙). 이 줄을 빼고 다시 실행하세요: "
                  + bad[0][:80])

    # 4) 훅 우회·main 강제 push
    if re.search(r"\bgit\s+commit\b.*(--no-verify|\s-n\b)", flat):
        block("git 훅을 건너뛰지 않습니다(--no-verify 금지). 훅이 막은 이유를 고치세요.")
    if re.search(r"\bgit\s+push\b.*(--force|\s-f\b|--force-with-lease)", flat) and re.search(r"\bmain\b", flat):
        block("main 에 강제 push 하지 않습니다.")


if __name__ == "__main__":
    main()
