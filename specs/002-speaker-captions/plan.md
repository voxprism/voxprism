---
spec: SPEC-002
status: 구현됨
updated: 2026-11-18
---

# SPEC-002 설계

## 1. 접근

받아쓰기(CLOVA Speech)와 화자 구분(pyannote)을 따로 돌린 뒤 **시간으로 합칩니다**(WhisperX 방식). 화자 구분은 겹침이 없는 배타 구간(exclusive)을 함께 받아, 단어 가운데 시점이 누구 구간인지로 배정합니다. 자막은 화자별로 열린 이벤트를 따로 관리해 다른 사람의 말이 섞이지 않게 합니다. 단계·파라미터는 [상세설계 7절](../../docs/02-상세설계.md#7-파이프라인-단계)·[9절](../../docs/02-상세설계.md#9-자막-생성).

## 2. 바뀌는 곳

| 영역 | 파일·함수 |
| --- | --- |
| 준비 | `pipeline/media.py` `probe`, `extract_audio`, `make_preview` |
| 인식 | `pipeline/asr.py` `resolve_engine`, `recognize`; `asr_clova.py` `recognize`, `to_words`, `to_sound_events`; `asr_whisper.py` |
| 화자 분리 | `pipeline/diarize.py` `get_pipeline`, `diarize`, `overlap_regions`, `exclusive_from_turns`, `turns_from_words` |
| 배정 | `pipeline/assign.py` `assign_words` |
| 자막 | `pipeline/captions.py` `build_events`, `_polish_timing`, `mark_overlaps`, `sound_events`, `wrap` |
| 화자 카드 | `pipeline/run.py` `build_speakers`, `_thumbnails` |

## 3. 데이터

`asr.json`, `diarization.json`, `result.json`(speakers·events·stats) — [상세설계 5.3](../../docs/02-상세설계.md#53-resultjson).

## 4. 대안

| 대안 | 결정 | 이유 |
| --- | --- | --- |
| CLOVA Speech 화자 인식만 사용 | 대체 경로로만 | 겹침 구간·배타 구간을 주지 않아 복원(SPEC-003)이 불가 |
| pyannote 3.1 | 대체 경로 | community-1은 pyannote가 공개 벤치마크에서 3.1보다 낫다고 발표했고, 배타 구간 출력을 지원 |
| 문장 단위 배정 | 안 함 | 끼어들기에서 한 문장에 두 화자가 섞임 |

## 5. 테스트

- `test_overlap_regions_and_exclusive`, `test_assign_words`, `test_build_events_turn_taking_and_overlap`, `test_writers_and_merge`.
- 품질: [SPEC-007](../007-evaluation/spec.md) 평가셋의 cpCER (NFR-QUAL-01).
