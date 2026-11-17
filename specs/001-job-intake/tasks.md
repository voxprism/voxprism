---
spec: SPEC-001
updated: 2026-11-18
---

# SPEC-001 작업

- [x] T-01 작업 폴더 저장소와 원자적 JSON 쓰기 (FR-JOB-03, NFR-SEC-03)
  - 파일: app/whosaid/store.py
- [x] T-02 업로드 API: 형식·크기·빈 파일 검사, 옵션 정리 (FR-JOB-01, FR-JOB-02)
  - 파일: app/whosaid/web/main.py (create_job)
  - 확인: tests/test_web.py::test_upload_status_edit_download
- [x] T-03 워커 대기열 루프와 렌더 요청 처리 (FR-JOB-03)
  - 파일: app/whosaid/worker.py
- [x] T-04 단계별 진행률과 사용자 오류 (FR-JOB-04, FR-JOB-05)
  - 파일: app/whosaid/pipeline/run.py (Progress, UserError)
- [x] T-05 목록·삭제 API, 처리 중 삭제 거부 (FR-JOB-06)
  - 파일: app/whosaid/web/main.py, app/whosaid/store.py
- [x] T-06 재시작 복구 1회 (FR-JOB-07, NFR-REL-01)
  - 파일: app/whosaid/store.py (recover_interrupted), app/deploy/whosaid-worker.service
- [x] T-07 업로드 화면과 진행 화면 (FR-JOB-02, FR-JOB-04)
  - 파일: app/whosaid/web/static/index.*, job.*
