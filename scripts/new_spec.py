#!/usr/bin/env python3
"""새 스펙 폴더 만들기: 다음 번호로 specs/NNN-<이름>/ 에 spec·plan·tasks 틀을 복사합니다.

  python3 scripts/new_spec.py sound-captions "소리 자막 켜기"
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"


def main() -> int:
    if len(sys.argv) != 3 or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", sys.argv[1]):
        print('사용법: new_spec.py <영문-소문자-이름> "<제목>"', file=sys.stderr)
        return 2
    slug, title = sys.argv[1], sys.argv[2].strip()
    nums = [int(d.name[:3]) for d in SPECS.iterdir() if d.is_dir() and re.match(r"^\d{3}-", d.name)]
    num = f"{(max(nums) if nums else 0) + 1:03d}"
    target = SPECS / f"{num}-{slug}"
    target.mkdir()
    today = datetime.date.today().isoformat()
    for name in ("spec.md", "plan.md", "tasks.md"):
        text = (SPECS / "_templates" / name).read_text(encoding="utf-8")
        text = text.replace("SPEC-000", f"SPEC-{num}").replace("기능 이름", title).replace("YYYY-MM-DD", today)
        (target / name).write_text(text, encoding="utf-8")
    print(f"만들었습니다: {target.relative_to(ROOT)}  (SPEC-{num})")
    print("다음: spec.md 작성 → specs/README.md 표에 한 줄 추가 → 사람 승인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
