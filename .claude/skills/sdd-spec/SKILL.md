---
name: sdd-spec
description: 새 기능이나 동작 변경을 시작할 때 SDD 스펙(spec.md) 초안을 만든다. "기능 추가해 줘", "~하게 바꿔 줘"처럼 구현 요청이 오면 코드보다 먼저 이것부터 한다.
argument-hint: "<기능 설명>"
---

# /sdd-spec — 스펙 초안

요청: $ARGUMENTS

1. 읽기: `docs/06-인수인계.md`(지금 상태), `specs/README.md`(기존 스펙), `docs/01-요구사항-분석.md`(요구사항 ID).
   겹치는 스펙이 있으면 새로 만들지 말고 **그 스펙 개정**을 제안한다(머리말 `status: 진행 중`, 개정 이력 한 줄).
2. 새 스펙이면 `python3 scripts/new_spec.py <영문-소문자-이름> "<제목>"`.
3. `spec.md`를 채운다. 구현 방법(파일·함수·라이브러리)은 쓰지 않는다.
   - 배경과 문제(근거 포함), 목표 / 하지 않는 것, 사용자 시나리오
   - 요구사항: 새 FR/NFR는 `docs/01-요구사항-분석.md` 해당 표에 **먼저** 추가하고(번호 이어 붙임, 수용 기준 포함) 머리말 `requirements`에 넣는다
   - 수용 시나리오(Gherkin 한국어: 시나리오/조건/만일/그러면), 영향과 위험
   - 모르는 것은 지어내지 말고 `[확인 필요: …]`로 남긴다
4. `specs/README.md` 표에 한 줄 추가 → `python3 scripts/check_specs.py` 통과 확인.
5. 사용자에게 **목표·요구사항 ID·열린 질문**을 짧게 보여 주고 승인을 받는다.
   - 승인 전에는 plan·코드로 넘어가지 않는다.
   - 승인받으면 `status: 승인`, `updated` 오늘 날짜.
6. 커밋(/sdd-commit 규칙): `spec(<영역>): SPEC-NNN <제목> 초안` + 꼬리말 `Refs: SPEC-NNN`.
