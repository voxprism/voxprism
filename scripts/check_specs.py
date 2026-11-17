#!/usr/bin/env python3
"""SDD 스펙 폴더 검사 (CI `test` 작업과 /sdd-* 명령이 실행).

검사 항목
  - specs/NNN-이름/ 마다 spec.md · plan.md · tasks.md 가 있고 머리말이 올바른가
  - 스펙의 requirements 가 docs/01-요구사항-분석.md 에 있는 ID 인가
  - 모든 FR 요구사항이 어떤 스펙엔가 연결돼 있는가 (NFR 은 경고만)
  - 상태가 '구현됨'이면 tasks.md 의 작업이 모두 체크됐는가
  - specs/README.md 표에 모든 스펙이 있는가
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
REQ_DOC = ROOT / "docs" / "01-요구사항-분석.md"
STATUSES = ("초안", "승인", "진행 중", "구현됨", "폐기")
DIR_RE = re.compile(r"^(\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*$")
REQ_ID_RE = re.compile(r"^(FR-[A-Z]+-\d{2}|NFR-[A-Z0-9]+-\d{2})$")
TASK_RE = re.compile(r"^- \[( |x)\] (T-\d{2})\b")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("맨 위에 '---'로 시작하는 머리말이 없습니다")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("머리말이 '---'로 닫히지 않았습니다")
    data: dict = {}
    for raw in text[4:end].splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"머리말 줄을 읽을 수 없습니다: {raw!r}")
        key, val = line.split(":", 1)
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            data[key.strip()] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            data[key.strip()] = val.strip("'\"")
    return data


def known_requirements() -> tuple[set[str], set[str]]:
    text = REQ_DOC.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\|\s*((?:FR-[A-Z]+|NFR-[A-Z0-9]+)-\d{2})\s*\|", text, re.M))
    return {i for i in ids if i.startswith("FR-")}, {i for i in ids if i.startswith("NFR-")}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    frs, nfrs = known_requirements()
    covered: set[str] = set()
    readme = (SPECS / "README.md").read_text(encoding="utf-8") if (SPECS / "README.md").exists() else ""
    seen_ids: set[str] = set()

    dirs = sorted(d for d in SPECS.iterdir() if d.is_dir() and not d.name.startswith("_"))
    for d in dirs:
        m = DIR_RE.match(d.name)
        if not m:
            errors.append(f"{d.name}: 폴더 이름은 'NNN-영문-소문자' 형식이어야 합니다")
            continue
        sid = f"SPEC-{m.group(1)}"
        if sid in seen_ids:
            errors.append(f"{d.name}: {sid} 번호가 중복됩니다")
        seen_ids.add(sid)
        for f in ("spec.md", "plan.md", "tasks.md"):
            if not (d / f).exists():
                errors.append(f"{d.name}/{f} 가 없습니다")
        if not (d / "spec.md").exists():
            continue
        try:
            fm = front_matter(d / "spec.md")
        except ValueError as e:
            errors.append(f"{d.name}/spec.md: {e}")
            continue
        if fm.get("id") != sid:
            errors.append(f"{d.name}/spec.md: id 는 {sid} 여야 합니다 (지금: {fm.get('id')})")
        if not fm.get("title"):
            errors.append(f"{d.name}/spec.md: title 이 비었습니다")
        status = fm.get("status")
        if status not in STATUSES:
            errors.append(f"{d.name}/spec.md: status 는 {', '.join(STATUSES)} 중 하나 (지금: {status})")
        if not DATE_RE.match(str(fm.get("updated", ""))):
            errors.append(f"{d.name}/spec.md: updated 는 YYYY-MM-DD")
        reqs = fm.get("requirements") or []
        if not isinstance(reqs, list):
            errors.append(f"{d.name}/spec.md: requirements 는 [ID, ID] 목록")
            reqs = []
        if not reqs and status not in ("초안", "폐기"):
            errors.append(f"{d.name}/spec.md: 승인 이후에는 requirements 가 비면 안 됩니다")
        for r in reqs:
            if not REQ_ID_RE.match(r):
                errors.append(f"{d.name}/spec.md: 요구사항 ID 형식이 아닙니다: {r}")
            elif r not in frs | nfrs:
                errors.append(f"{d.name}/spec.md: {r} 가 docs/01-요구사항-분석.md 에 없습니다 (먼저 추가)")
        if status != "폐기":
            covered.update(reqs)
        if sid not in readme:
            errors.append(f"specs/README.md 표에 {sid} 가 없습니다")

        for f in ("plan.md", "tasks.md"):
            p = d / f
            if p.exists():
                try:
                    pfm = front_matter(p)
                    if pfm.get("spec") != sid:
                        errors.append(f"{d.name}/{f}: spec 은 {sid} 여야 합니다")
                except ValueError as e:
                    errors.append(f"{d.name}/{f}: {e}")
        if (d / "tasks.md").exists():
            tasks = [TASK_RE.match(ln) for ln in (d / "tasks.md").read_text(encoding="utf-8").splitlines()]
            tasks = [t for t in tasks if t]
            ids = [t.group(2) for t in tasks]
            dup = {i for i in ids if ids.count(i) > 1}
            if dup:
                errors.append(f"{d.name}/tasks.md: 작업 번호 중복 {sorted(dup)}")
            if status == "구현됨":
                open_tasks = [t.group(2) for t in tasks if t.group(1) == " "]
                if open_tasks:
                    errors.append(f"{d.name}: 상태가 '구현됨'인데 끝나지 않은 작업이 있습니다 {open_tasks}")
            if status in ("진행 중", "구현됨") and not tasks:
                errors.append(f"{d.name}/tasks.md: 작업(- [ ] T-01 …)이 없습니다")

    for r in sorted(frs - covered):
        errors.append(f"{r}: 어떤 스펙에도 연결되지 않았습니다 (스펙 requirements 에 추가)")
    for r in sorted(nfrs - covered):
        warnings.append(f"{r}: 스펙에 연결되지 않은 비기능 요구사항 (공통 규칙이면 괜찮음)")

    for w in warnings:
        print(f"[경고] {w}")
    if errors:
        print(f"스펙 검사 실패 ({len(errors)}건):", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    print(f"스펙 검사 통과: 스펙 {len(dirs)}개, FR {len(frs)}개 모두 연결")
    return 0


if __name__ == "__main__":
    sys.exit(main())
