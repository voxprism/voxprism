---
name: sdd-implement
description: SDD tasks.md의 작업을 하나씩 구현한다(테스트 먼저). 스펙이 승인되고 plan·tasks가 있을 때만.
argument-hint: "SPEC-NNN [T-NN]"
---

# /sdd-implement — 구현

대상: $ARGUMENTS

1. **게이트:** `spec.md` status가 `승인`·`진행 중`이고 `plan.md`·`tasks.md`가 있어야 한다. 아니면 멈추고 무엇이 빠졌는지 말한다.
2. 브랜치: `main`이면 `git switch -c <유형>/spec-NNN-<짧은-이름>` (예: `feat/spec-008-sound-captions`).
3. 처음 시작이면 `spec.md` status를 `진행 중`으로.
4. 작업 하나를 고른다(인자의 T-NN, 없으면 첫 미완료 작업). **한 번에 한 작업만.**
5. 테스트를 먼저 쓰고 실패를 확인 → 구현 → 확인:
   - `cd app && python -m pytest -q tests`
   - `python3 scripts/check_specs.py`
   - 파이프라인 변경이면 평가셋 측정은 서버에서 해야 하므로 사용자에게 요청(서버 명령은 확인 후 실행)
6. 구현하다 스펙과 다르게 해야 한다는 걸 알게 되면 **멈추고** spec/plan을 먼저 고치자고 제안한다. 코드만 바꾸지 않는다.
7. AGENTS.md 코드 규칙 준수: 웹 쪽에 무거운 import 금지, JSON은 `store.write_json`, 사용자 문구는 '해요'체, 내부 코드명 whosaid 유지.
8. `tasks.md`에서 그 작업을 `- [x]`로 → /sdd-commit (꼬리말 `Refs: SPEC-NNN, T-NN`).
9. 남은 작업을 알려 주고, 다 끝났으면 기준선 문서 갱신 → /sdd-pr 을 제안한다.
