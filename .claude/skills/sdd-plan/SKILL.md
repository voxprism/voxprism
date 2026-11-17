---
name: sdd-plan
description: 승인된 SDD 스펙의 설계(plan.md)를 쓴다. 스펙 status가 승인 또는 진행 중일 때만 쓴다.
argument-hint: "SPEC-NNN"
---

# /sdd-plan — 설계

대상: $ARGUMENTS

1. `specs/NNN-*/spec.md` 머리말의 `status`가 `승인`·`진행 중`인지 확인한다. 아니면 **멈추고** 사용자에게 승인을 요청한다.
2. `docs/02-상세설계.md`의 관련 절과 `docs/03-기능-구현.md`의 코드 지도, 실제 코드를 읽는다.
3. `plan.md`를 채운다: 접근, 바뀌는 곳(파일·함수), 데이터·API 변경과 하위 호환, 대안 비교와 결정 이유,
   테스트·평가 계획(SPEC-002·003을 건드리면 평가셋 v2 측정 필수 — NFR-QUAL-01), 배포·되돌리기, 위험.
4. 기준 설계를 바꾸는 결정이면 `docs/02-상세설계.md` 15절 결정 기록에 넣을 줄을 plan에 적어 둔다(머지 때 반영).
5. 사용자에게 요약 보고 → 커밋 `spec(<영역>): SPEC-NNN 설계` + `Refs: SPEC-NNN`.
