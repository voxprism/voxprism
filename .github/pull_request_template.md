<!-- 제목: <유형>(<범위>): <요약>  예) feat(overlap): 배치 재인식 실패 시 구간별 재시도 -->

## 관련 스펙

- 스펙: SPEC-NNN <!-- app/whosaid·app/deploy·infra 를 바꾸면 필수. 문서·CI만 바꾸면 '없음' -->
- 요구사항: FR-…, NFR-…
- 이슈: Closes #

## 무엇을 바꿨나요

-

## 왜 바꿨나요

-

## 어떻게 확인했나요

- [ ] `cd app && python -m pytest -q tests` 통과
- [ ] `python3 scripts/check_specs.py` 통과
- [ ] 파이프라인(SPEC-002·003) 변경: 평가셋 v2 결과 표 첨부 (cpCER ≤ 0.40, 겹친 발화 재현율 ≥ 0.70)
- [ ] 화면 변경: 스크린샷 + 접근성 점검표(docs/04-디자인.md 5절)
- [ ] 배포 변경: `./infra/deploy.sh code` 후 `/api/health` 확인

## SDD 체크리스트

- [ ] 스펙(`spec.md`)과 설계(`plan.md`)를 코드보다 먼저 고쳤고, 구현이 스펙과 일치한다
- [ ] `tasks.md` 체크 상태를 갱신했다
- [ ] 기준선 문서(01 요구사항·02 상세설계·03 기능 구현·04 디자인) 중 영향받는 절을 고쳤다
- [ ] 커밋 메시지가 규칙을 따르고 꼬리말에 `Refs: SPEC-NNN`이 있다
- [ ] 비밀 값·서버 주소·개인 정보가 없다
