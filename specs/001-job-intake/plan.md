---
spec: SPEC-001
status: 구현됨
updated: 2026-11-18
---

# SPEC-001 설계

## 1. 접근

DB 없이 **작업 1건 = 폴더 1개**. 웹은 업로드를 받아 `options.json`과 `status.json(queued)`만 만들고, 워커가 폴더를 이름순으로 훑어 처리합니다. 같은 파일을 두 프로세스가 쓰지 않도록 파일마다 쓰기 주인을 정하고, 모든 JSON은 임시 파일 → `os.replace`로 원자적으로 바꿉니다. 자세한 파일 표는 [상세설계 5절](../../docs/02-상세설계.md#5-작업-저장소).

## 2. 바뀌는 곳

| 영역 | 파일·함수 | 내용 |
| --- | --- | --- |
| 업로드 API | `web/main.py` `create_job` | 확장자·크기·빈 파일 검사, 1MB씩 저장, 옵션 정리 |
| 저장소 | `store.py` | `new_job_id`, `create_job`, `set_status`, `list_jobs`, `next_queued`, `recover_interrupted`, `delete_job` |
| 워커 | `worker.py` `main` | 복구 → 모델 미리 로드 → 1초 주기 대기열 루프, SIGTERM 시 현재 작업 후 종료 |
| 진행률 | `pipeline/run.py` `Progress`, `STAGE_RANGE` | 단계별 구간, 0.7초 간격 제한 |
| 입력 검사 | `pipeline/run.py` `UserError` | 오디오 없음, 길이 초과, 인식 결과 없음 |
| 화면 | `static/index.*`, `static/job.*` | 업로드 폼·XHR 진행률·최근 작업 / 단계 표시 |

## 3. 데이터·API

- `POST /api/jobs` → `{id}`; `GET /api/jobs`; `GET /api/jobs/{id}`; `DELETE /api/jobs/{id}` ([상세설계 10절](../../docs/02-상세설계.md#10-api)).
- 작업 ID `YYYYMMDD-HHMMSS-<6hex>`: 이름순 = 접수순, 정규식으로 경로 조작 차단.

## 4. 대안

| 대안 | 결정 | 이유 |
| --- | --- | --- |
| SQLite + 작업 테이블 | 안 함 | 단일 서버·단일 워커에서 이점 적음, 디버깅은 폴더가 편함 |
| Redis/Celery 큐 | 안 함 | 구성 요소 추가 대비 이득 없음 |

## 5. 테스트

- `tests/test_web.py::test_upload_status_edit_download` — 업로드·상태·편집·다운로드 흐름(워커 없이 결과를 직접 써서 확인).
- 재시작 복구는 수동: 처리 중 `systemctl restart whosaid-worker` → 상태 확인.
