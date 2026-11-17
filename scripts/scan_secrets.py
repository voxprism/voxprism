#!/usr/bin/env python3
"""비밀 값·개인 정보가 저장소에 들어가는 것을 막습니다. 값은 절대 출력하지 않습니다.

  scan_secrets.py --staged   pre-commit 훅: 스테이지된 변경의 추가 줄 검사
  scan_secrets.py --all      CI: 추적 중인 모든 파일 검사(패턴만)

검사 1) 금지 경로: secrets/, *.env(예시 파일 제외), 키 파일, infra/state.env, 로그
검사 2) 패턴: 개인 키, Hugging Face·GitHub·OpenAI 토큰, 'KEY=값' 꼴 대입
검사 3) (로컬만) secrets/keys.env·web_login.txt의 실제 값, infra/state.env의 집 IP가 그대로 들어갔는지
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCKED_PATHS = [
    re.compile(r"^secrets/"),
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)[^/]*\.env$"),            # keys.env, state.env … (*.env.example 은 허용)
    re.compile(r"\.(pem|key|p12|pfx)$"),
    re.compile(r"(^|/)id_(rsa|ed25519|ecdsa)(\.pub)?$"),
    re.compile(r"_ed25519(\.pub)?$"),
    re.compile(r"(^|/)known_hosts$"),
    re.compile(r"^infra/.*\.log$"),
    re.compile(r"(^|/)\.ncloud/"),
]
PATTERNS = [
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Hugging Face 토큰", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("GitHub 토큰", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("OpenAI·Anthropic 키", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{30,}\b")),
    ("키 대입", re.compile(
        r"\b(NCLOUD_(ACCESS|SECRET)_KEY|CLOVA_SPEECH_SECRET|CLOVASTUDIO_API_KEY|HF_TOKEN|"
        r"WHOSAID_WEB_PASSWORD|WHOSAID_SECRET)\s*=\s*['\"]?[A-Za-z0-9_\-+/=]{12,}")),
    ("CLOVA 헤더 값", re.compile(r"X-CLOVASPEECH-API-KEY['\"]?\s*[:=]\s*['\"][A-Za-z0-9]{16,}")),
]
ALLOW_MARK = "scan-secrets: allow"   # 같은 줄에 이 표시가 있으면 패턴 검사 생략(예시 문서용)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def local_values() -> list[tuple[str, str]]:
    """(이름, 값) — 이 PC에만 있는 실제 비밀 값과 집 IP. 값은 비교에만 쓰고 출력하지 않는다."""
    vals: list[tuple[str, str]] = []
    for rel in ("secrets/keys.env", "secrets/web_login.txt", "infra/state.env"):
        p = ROOT / rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if rel == "infra/state.env" and k != "MYIP":
                continue                      # 자원 번호·서버 IP는 비밀이 아님. 집 IP만 막음
            if rel == "secrets/web_login.txt" and k not in ("password", "session_secret"):
                continue                      # id=whosaid 같은 공개 값은 제외
            if len(v) >= 7:
                vals.append((f"{rel}의 {k}", v))
    return vals


def blocked(path: str) -> bool:
    if path.endswith(".example"):
        return False
    return any(r.search(path) for r in BLOCKED_PATHS)


def scan_text(path: str, lines: list[str], values: list[tuple[str, str]]) -> list[str]:
    hits = []
    for no, line in enumerate(lines, 1):
        if ALLOW_MARK not in line:
            for name, rx in PATTERNS:
                if rx.search(line):
                    hits.append(f"{path}:{no}: {name} 형태가 보입니다")
        for name, val in values:
            if val in line:
                hits.append(f"{path}:{no}: {name} 값이 그대로 들어 있습니다")
    return hits


def staged() -> list[str]:
    hits = []
    names = [n for n in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if n]
    hits += [f"{n}: 올리면 안 되는 파일입니다(.gitignore 확인)" for n in names if blocked(n)]
    values = local_values()
    diff = git("diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACMR")
    cur, buf = None, {}
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            buf.setdefault(cur, [])
        elif line.startswith("+") and not line.startswith("+++") and cur:
            buf[cur].append(line[1:])
    for path, added in buf.items():
        hits += scan_text(path, added, values)
    return hits


def all_files() -> list[str]:
    hits = []
    values = local_values()
    for path in git("ls-files").splitlines():
        if blocked(path):
            hits.append(f"{path}: 올리면 안 되는 파일입니다")
            continue
        p = ROOT / path
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        hits += scan_text(path, text.splitlines(), values)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--all", action="store_true")
    a = ap.parse_args()
    hits = staged() if a.staged else all_files()
    if hits:
        print("비밀 값·개인 정보가 들어갈 수 있어 멈췄습니다 (값은 표시하지 않음):", file=sys.stderr)
        for h in hits[:30]:
            print("  - " + h, file=sys.stderr)
        print("의도한 예시라면 그 줄에 'scan-secrets: allow'를 붙이세요. 실제 값이면 지우고 키를 새로 발급하세요.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
