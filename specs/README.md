# 스펙 목록

기능 하나 = 폴더 하나(`spec.md` 무엇·왜 → `plan.md` 어떻게 → `tasks.md` 할 일). 절차는 [SDD 개발 프로세스](../docs/05-SDD-개발-프로세스.md).

| ID | 폴더 | 제목 | 상태 | 요구사항 |
| --- | --- | --- | --- | --- |
| SPEC-001 | [001-job-intake](001-job-intake/spec.md) | 작업 접수와 대기열 | 구현됨 | FR-JOB-01~07 |
| SPEC-002 | [002-speaker-captions](002-speaker-captions/spec.md) | 화자 구분 자막 생성 | 구현됨 | FR-CAP-01~07 |
| SPEC-003 | [003-overlap-recovery](003-overlap-recovery/spec.md) | 겹친 말 복원 | 구현됨 | FR-OVL-01~07 |
| SPEC-004 | [004-caption-viewer](004-caption-viewer/spec.md) | 자막 보기·화자 편집·내보내기 | 구현됨 | FR-VIEW-01~07 |
| SPEC-005 | [005-access-control](005-access-control/spec.md) | 접근 제어 | 구현됨 | FR-AUTH-01~06 |
| SPEC-006 | [006-ncp-deploy](006-ncp-deploy/spec.md) | 네이버 클라우드 인프라와 배포 | 구현됨 | FR-OPS-01~06 |
| SPEC-007 | [007-evaluation](007-evaluation/spec.md) | 품질 평가 체계 | 구현됨 | FR-EVAL-01~04 |
| SPEC-008 | [008-fixed-bubble-captions](008-fixed-bubble-captions/spec.md) | 고정 위치 말풍선 자막과 말하는 사람 표시 | 구현됨 | FR-VIEW-03, FR-VIEW-08~10 |

새 스펙: `python3 scripts/new_spec.py <영문-이름> "<제목>"` (Claude Code에서는 `/sdd-spec <설명>`). 만든 뒤 이 표에 한 줄을 더합니다.
검사: `python3 scripts/check_specs.py` (CI에서도 실행).
