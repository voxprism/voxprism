---
spec: SPEC-009
updated: 2026-11-19
---

# SPEC-009 작업

- [ ] T-01 PRD v2·요구사항(FR-VIS, FR-CAP-08, FR-VIEW-08~10 개정, NFR-PERF-03, NFR-PRIV-02)·스펙
  - 확인: `python3 scripts/check_specs.py`
- [ ] T-02 화면 분석 모듈과 연결 알고리즘 (FR-VIS-01~03)
  - 파일: app/whosaid/pipeline/visual.py
  - 확인: test_link_tracks_iou_and_cut, test_cluster_same_person, test_associate_*; 개발 샘플 9장면
- [ ] T-03 잡음 거르기와 파이프라인 연결 (FR-CAP-08, FR-VIS-04~06)
  - 파일: pipeline/noise.py, pipeline/run.py, config.py
  - 확인: test_noise_filter_words_and_speakers, test_offscreen_flags
- [ ] T-04 웹: 윤곽 캔버스, 위쪽 고정 자막, '화면 밖', 화자 카드 얼굴 (FR-VIS-04~05, FR-VIEW-08~09)
  - 파일: web/static/job.*, app.css, web/main.py, deploy/nginx-whosaid.conf
- [ ] T-05 MP4: 위쪽 줄 + 윤곽 + 화면 밖 (FR-VIEW-10)
  - 파일: pipeline/captions.py, subtitles.py
  - 확인: test_burn_ass_top_lanes_offscreen_and_outlines
- [ ] T-06 운영: 라이브러리·모델 설치 스크립트 (NFR-PERF-03)
  - 파일: app/requirements.txt, deploy/fetch_models.sh, deploy/setup_server.sh, infra/deploy.sh
- [ ] T-07 기준선 문서(02·03·04·06), SPEC-008 개정 이력
- [ ] T-08 서버 배포·샘플 재처리·시간 측정·평가셋 회귀 확인
