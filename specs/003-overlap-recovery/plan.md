---
spec: SPEC-003
status: 구현됨
updated: 2026-11-18
---

# SPEC-003 설계

## 1. 접근

겹침 구간마다 **분리 → 재식별 → (모두 모아) 배치 재인식 → 단어 단위 판정**. 의사코드와 상수는 [상세설계 8절](../../docs/02-상세설계.md#8-겹친-말-복원-알고리즘)이 기준입니다.

| 상수 | 값 | 뜻 |
| --- | --- | --- |
| `MIN_REGION` | 0.4초 | 처리할 최소 겹침 |
| `CONTEXT` / `MAX_WINDOW` | 1.5초 / 12초 | 분리 창 |
| `GAP` | 1.2초 | 배치 파일의 조각 사이 무음 |
| `PRIOR` | 0.05 | 구간 표시 화자 가산점 |
| `NEAR` / `WORD_SIM` | 0.8초 / 0.6 | 같은 단어 판정 |
| 확신도 기준 | 0.05 | 미만이면 uncertain |
| 에너지 제외 | −18dB | 큰 조각보다 이만큼 작으면 재인식 제외 |

## 2. 바뀌는 곳

| 영역 | 파일·함수 |
| --- | --- |
| 대표 목소리 | `pipeline/diarize.py` `get_embedder`, `embed`, `speaker_centroids` |
| 분리 | `pipeline/separate.py` `get_separator`, `separate`, `normalize`, `rms_db` |
| 계획·재식별 | `pipeline/overlap.py` `plan_regions`, `match_speakers`, `Plan` |
| 배치 | `pipeline/overlap.py` `build_batch`, `map_back`; `pipeline/asr.py` `recognize_batch` |
| 판정 | `pipeline/overlap.py` `resolve`, `similarity`, `_has_match` |
| 연결 | `pipeline/run.py` 4단계, 재배정 단어에 `reassigned=True` |
| 표시 | `captions.build_events`(복원 단어를 원래 단어와 섞지 않음), `job.js`/`app.css`('복원', '?') |

## 3. 데이터

- `overlap.json`: `n_regions`, `n_processed`, `n_recovered_words`, `regions[]`(구간, 화자, 유사도, 확신도, 에너지, 원래/분리 텍스트, 이동 단어 수, 판정, 추가 텍스트).
- 단어: `recovered`, `uncertain`, `region`, `reassigned`. 이벤트: `recovered`, `uncertain`.

## 4. 대안

| 대안 | 결정 | 이유 |
| --- | --- | --- |
| v1: 구간에 표시된 두 화자에게 분리음을 바로 배정 | 폐기 | 두 번째 화자 표시가 자주 틀려 cpCER 악화 |
| 구간마다 따로 재인식 | 안 함 | API 호출 수·지연 증가, 짧은 조각은 인식이 나쁨 |
| MossFormer2 등 다른 분리 모델 | 보류 | 실제 클립 평가 후 비교(다음 스펙) |
| 분리 전 보컬 추출(Demucs) | 보류 | 배경음악 문제 확인 후 |

## 5. 테스트·평가

- 단위: `test_resolve_recovers_dropped_speaker_and_reassigns`, `test_resolve_skips_leakage`, `test_reidentify_secondary_speaker`, `test_resolve_drops_duplicate_near_boundary`, `test_batch_map_back`, `test_similarity`.
- 평가: SPEC-007 평가셋에서 복원 켬/끔 비교. 이 스펙을 바꾸는 PR은 결과 표 첨부 필수.
