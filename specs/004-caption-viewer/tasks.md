---
spec: SPEC-004
updated: 2026-11-18
---

# SPEC-004 작업

- [x] T-01 미리보기 영상 (FR-VIEW-01)
  - 파일: app/whosaid/pipeline/media.py (make_preview)
- [x] T-02 자막 오버레이: 화자 색·이름표·동시·복원·불확실 (FR-VIEW-02, NFR-A11Y-01, NFR-A11Y-02)
  - 파일: app/whosaid/web/static/job.js, app.css
- [x] T-03 보기 설정과 전체 화면 (FR-VIEW-03)
  - 파일: app/whosaid/web/static/job.html, job.js
- [x] T-04 대본·클릭 이동·따라가기 (FR-VIEW-04)
  - 파일: app/whosaid/web/static/job.js
- [x] T-05 화자 편집 API와 병합 (FR-VIEW-05)
  - 파일: app/whosaid/web/main.py (edit_speakers), pipeline/captions.py (resolve_speakers)
  - 확인: tests/test_logic.py::test_writers_and_merge
- [x] T-06 SRT·VTT·ASS·JSON 내려받기 (FR-VIEW-06)
  - 파일: app/whosaid/subtitles.py, pipeline/captions.py, web/main.py (download)
  - 확인: tests/test_web.py::test_upload_status_edit_download
- [x] T-07 자막 입힌 MP4 요청·렌더 (FR-VIEW-07)
  - 파일: app/whosaid/web/main.py (request_render), pipeline/run.py (render), media.py (burn_in)
- [x] T-08 키보드 조작과 레이블 (NFR-A11Y-03)
  - 파일: app/whosaid/web/static/*.html
