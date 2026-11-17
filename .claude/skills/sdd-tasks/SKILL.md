---
name: sdd-tasks
description: SDD 설계(plan.md)를 작업 목록(tasks.md)으로 나눈다.
argument-hint: "SPEC-NNN"
---

# /sdd-tasks — 작업 나누기

대상: $ARGUMENTS

1. `spec.md`(승인 이상)와 `plan.md`가 있는지 확인한다. 없으면 멈춘다.
2. `tasks.md`를 쓴다. 형식:
   ```markdown
   - [ ] T-01 <할 일> (FR-…)
     - 파일: <경로 (함수)>
     - 확인: <테스트 이름 또는 확인 방법>
   ```
   - 한 작업 = 커밋 1~3개 크기. 테스트를 쓰는 작업을 구현 작업보다 앞에 둔다.
   - 모든 요구사항 ID가 적어도 한 작업에 나타나야 한다.
   - 마지막 작업: 기준선 문서(01·02·03·04 중 해당 절) 갱신 + `python3 scripts/check_specs.py`.
3. 커밋 `spec(<영역>): SPEC-NNN 작업 목록` + `Refs: SPEC-NNN`.
