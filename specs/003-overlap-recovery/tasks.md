---
spec: SPEC-003
updated: 2026-11-18
---

# SPEC-003 작업

- [x] T-01 화자 대표 목소리 벡터 (FR-OVL-02)
  - 파일: app/whosaid/pipeline/diarize.py (speaker_centroids)
- [x] T-02 SepFormer 분리와 에너지 계산 (FR-OVL-01)
  - 파일: app/whosaid/pipeline/separate.py
- [x] T-03 구간 계획과 전체 화자 재식별 (FR-OVL-01, FR-OVL-02)
  - 파일: app/whosaid/pipeline/overlap.py (plan_regions, match_speakers)
  - 확인: tests/test_logic.py::test_reidentify_secondary_speaker
- [x] T-04 배치 재인식과 시각 복원 (FR-OVL-03)
  - 파일: app/whosaid/pipeline/overlap.py (build_batch, map_back), asr.py (recognize_batch)
  - 확인: tests/test_logic.py::test_batch_map_back
- [x] T-05 단어 재배정·복원·누설 제거 (FR-OVL-04, FR-OVL-05, FR-OVL-06)
  - 파일: app/whosaid/pipeline/overlap.py (resolve)
  - 확인: tests/test_logic.py::test_resolve_recovers_dropped_speaker_and_reassigns, test_resolve_skips_leakage, test_resolve_drops_duplicate_near_boundary
- [x] T-06 파이프라인 연결과 끄기 옵션 (FR-OVL-07)
  - 파일: app/whosaid/pipeline/run.py
- [x] T-07 자막 쪼개짐 수정(TURN_PAUSE)과 복원 표시 (FR-OVL-05)
  - 파일: app/whosaid/pipeline/captions.py, web/static/job.js, app.css
- [x] T-08 평가셋 v2로 기준선 측정 (NFR-QUAL-01)
  - 확인: docs/eval_v2.json
