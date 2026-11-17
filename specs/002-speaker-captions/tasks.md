---
spec: SPEC-002
updated: 2026-11-18
---

# SPEC-002 작업

- [x] T-01 ffmpeg 준비 단계: 16kHz 모노, 브라우저 재생용 미리보기 (FR-CAP-01)
  - 파일: app/whosaid/pipeline/media.py
- [x] T-02 CLOVA Speech 장문 인식과 단어 변환 (FR-CAP-01, NFR-SOV-01)
  - 파일: app/whosaid/pipeline/asr_clova.py
- [x] T-03 faster-whisper 대체 엔진과 엔진 선택 (FR-CAP-01)
  - 파일: app/whosaid/pipeline/asr_whisper.py, asr.py
- [x] T-04 이벤트 탐지 자동 끄기와 소리 자막 (FR-CAP-07)
  - 파일: app/whosaid/pipeline/asr.py, captions.py (sound_events)
- [x] T-05 pyannote 화자 분리, 겹침·배타 구간 (FR-CAP-02)
  - 파일: app/whosaid/pipeline/diarize.py
  - 확인: tests/test_logic.py::test_overlap_regions_and_exclusive
- [x] T-06 화자 분리 대체 경로 (FR-CAP-03)
  - 파일: app/whosaid/pipeline/run.py, diarize.py (turns_from_words)
- [x] T-07 단어-화자 배정 (FR-CAP-04)
  - 파일: app/whosaid/pipeline/assign.py
  - 확인: tests/test_logic.py::test_assign_words
- [x] T-08 화자별 자막 이벤트와 표시 시간 (FR-CAP-05)
  - 파일: app/whosaid/pipeline/captions.py
  - 확인: tests/test_logic.py::test_build_events_turn_taking_and_overlap
- [x] T-09 화자 카드와 썸네일 (FR-CAP-06, NFR-A11Y-01)
  - 파일: app/whosaid/pipeline/run.py
- [x] T-10 워커 시작 시 모델 미리 로드 (NFR-PERF-02)
  - 파일: app/whosaid/worker.py (warmup)
