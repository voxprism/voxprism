---
spec: SPEC-008
updated: 2026-11-19
---

# SPEC-008 작업

- [ ] T-01 웹: 고정 줄 말풍선과 화자 표시줄, 꼬리·선 (FR-VIEW-08, FR-VIEW-09, FR-VIEW-03)
  - 파일: app/whosaid/web/static/job.html, job.js, app.css
  - 확인: 예시 ③ 5초·18.8초·40초 화면, 400px 폭, 위치 '위'
- [ ] T-02 MP4: 같은 모양의 ASS 만들기와 렌더 연결 (FR-VIEW-10)
  - 파일: app/whosaid/pipeline/captions.py, subtitles.py, pipeline/run.py
  - 확인: tests/test_logic.py, 1280×720·720×1280 프레임
- [ ] T-03 기준선 문서 갱신 (01·02·03·04)
  - 확인: `python3 scripts/check_specs.py`
- [ ] T-04 배포와 실제 화면 확인
  - 확인: 서버 예시 ③에서 동시 발화 장면, MP4 다시 만들기
