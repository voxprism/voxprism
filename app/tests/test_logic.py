"""모델 없이 돌릴 수 있는 로직 테스트: python -m pytest -q tests"""
import numpy as np

from whosaid.pipeline import assign, captions, diarize, overlap


def W(s, e, t, spk=None, **kw):
    return {"start": s, "end": e, "text": t, "speaker": spk, **kw}


def test_overlap_regions_and_exclusive():
    turns = [{"start": 0.0, "end": 4.0, "speaker": "A"}, {"start": 3.0, "end": 6.0, "speaker": "B"},
             {"start": 7.0, "end": 8.0, "speaker": "A"}]
    ov = diarize.overlap_regions(turns)
    assert len(ov) == 1 and ov[0]["start"] == 3.0 and ov[0]["end"] == 4.0 and ov[0]["speakers"] == ["A", "B"]
    ex = diarize.exclusive_from_turns(turns)
    assert [(t["speaker"], t["start"], t["end"]) for t in ex] == [("A", 0.0, 4.0), ("B", 4.0, 6.0), ("A", 7.0, 8.0)]


def test_assign_words():
    ex = [{"start": 0.0, "end": 4.0, "speaker": "A"}, {"start": 4.0, "end": 6.0, "speaker": "B"}]
    words = [W(0.5, 0.9, "안녕"), W(4.2, 4.6, "응"), W(6.3, 6.5, "끝")]
    assign.assign_words(words, ex, ex)
    assert [w["speaker"] for w in words] == ["A", "B", "B"]


def test_build_events_turn_taking_and_overlap():
    words = [W(0.0, 0.4, "오늘", "A"), W(0.5, 0.9, "뭐", "A"), W(1.0, 1.4, "먹지?", "A"),
             W(1.5, 1.9, "치킨", "B"), W(2.0, 2.3, "먹자", "B"),
             W(2.1, 2.5, "피자!", "C", recovered=True),
             W(2.6, 3.0, "좋아", "A")]
    ev = captions.build_events(words)
    texts = [(e["speaker"], e["text"]) for e in ev]
    assert ("A", "오늘 뭐 먹지?") in texts
    assert ("B", "치킨 먹자") in texts
    assert ("C", "피자!") in texts
    assert ("A", "좋아") in texts          # 턴이 바뀌면 A의 자막을 새로 시작
    b = next(e for e in ev if e["speaker"] == "B")
    c = next(e for e in ev if e["speaker"] == "C")
    assert b["overlap"] and c["overlap"] and c["recovered"]


def test_resolve_recovers_dropped_speaker_and_reassigns():
    region = {"id": 0, "start": 10.0, "end": 12.0, "speakers": ["A", "B"]}
    p = overlap.Plan(region=region, w0=9.0, w1=13.0, speakers=["A", "B"], sims=[0.7, 0.6],
                     match_conf=0.3, energy_db=[-20.0, -22.0])
    # 원래 인식: 구간 안 단어 '그거 아니야'가 A에게 붙어 있지만 실제로는 B의 말
    main = [W(10.2, 10.6, "그거", "A"), W(10.7, 11.2, "아니야", "A")]
    per = {(0, 0): [W(10.1, 10.5, "진짜", None), W(10.6, 11.0, "맛있다", None)],   # A 목소리
           (0, 1): [W(10.2, 10.6, "그거", None), W(10.7, 11.2, "아니야", None)]}  # B 목소리
    rec, reassign, details = overlap.resolve([p], per, main)
    assert sorted(set(i for i, _ in reassign)) == [0, 1] and all(s == "B" for _, s in reassign)
    assert [w["text"] for w in rec] == ["진짜", "맛있다"] and all(w["speaker"] == "A" for w in rec)
    assert details[0]["action"] == "reassign+recover"


def test_resolve_skips_leakage():
    region = {"id": 1, "start": 0.0, "end": 1.0, "speakers": ["A", "B"]}
    p = overlap.Plan(region=region, w0=0.0, w1=2.0, speakers=["A", "B"], sims=[0.5, 0.5],
                     match_conf=0.2, energy_db=[-20.0, -21.0])
    main = [W(0.2, 0.6, "안녕하세요", "A")]
    per = {(0, 0): [W(0.2, 0.6, "안녕하세요", None)], (0, 1): [W(0.2, 0.6, "안녕하세요", None)]}
    rec, reassign, _ = overlap.resolve([p], per, main)
    assert rec == [] and reassign == []


def test_reidentify_secondary_speaker():
    # 화자 분리는 겹침 구간을 [A, B]로 표시했지만, 분리된 두 번째 목소리는 실제로 C와 닮음
    c = {"A": np.array([1.0, 0.0, 0.0]), "B": np.array([0.0, 1.0, 0.0]), "C": np.array([0.0, 0.0, 1.0])}
    e0 = np.array([0.9, 0.1, 0.0]); e0 /= np.linalg.norm(e0)
    e1 = np.array([0.0, 0.3, 0.9]); e1 /= np.linalg.norm(e1)
    spk, sims, conf = overlap.match_speakers([e0, e1], c, ["A", "B"])
    assert spk == ["A", "C"] and conf > 0
    # 둘 다 구간 밖 화자인 조합은 고르지 않음
    spk2, _, _ = overlap.match_speakers([c["C"], c["B"] * 0 + np.array([0, 0, 1.0])], c, ["A", "B"])
    assert "A" in spk2 or "B" in spk2


def test_resolve_drops_duplicate_near_boundary():
    region = {"id": 2, "start": 16.4, "end": 16.9, "speakers": ["A", "B"]}
    p = overlap.Plan(region=region, w0=15.0, w1=18.0, speakers=["A", "B"], sims=[0.5, 0.5],
                     match_conf=0.3, energy_db=[-20.0, -20.0])
    main = [W(15.4, 15.8, "생각도", "A"), W(15.81, 16.35, "하지", "A"), W(16.45, 16.8, "이번", "B")]
    per = {(0, 0): [W(16.25, 16.48, "하지", None), W(16.51, 17.0, "않는다.", None)],
           (0, 1): [W(16.45, 16.8, "이번", None)]}
    rec, reassign, _ = overlap.resolve([p], per, main)
    assert [w["text"] for w in rec] == ["않는다."] and rec[0]["speaker"] == "A"
    assert reassign == []


def test_writers_and_merge():
    speakers = [{"id": "S1", "name": "화자 1", "color": "#FFD84D"}, {"id": "S2", "name": "화자 2", "color": "#5FD3FF"}]
    spk = captions.resolve_speakers(speakers, {"S1": {"name": "유재석"}, "S2": {"merge_into": "S1"}})
    assert spk["S2"]["name"] == "유재석" and spk["S2"]["color"] == "#FFD84D"
    ev = [{"id": 0, "speaker": "S1", "start": 0.0, "end": 1.5, "text": "안녕하세요 여러분 반갑습니다 오늘은 특별한 날", "overlap": False},
          {"id": 1, "speaker": "_sfx", "start": 0.5, "end": 2.0, "text": "[웃음]", "overlap": False}]
    srt = captions.to_srt(ev, spk)
    assert "[유재석]" in srt and "00:00:01,500" in srt
    vtt = captions.to_vtt(ev, spk)
    assert vtt.startswith("WEBVTT") and "::cue(.S1)" in vtt
    ass = captions.to_ass(ev, spk, 1280, 720)
    assert "Style: S1," in ass and "Dialogue: 0,0:00:00.00,0:00:01.50,S1" in ass and "Style: SFX" in ass


def test_similarity():
    assert overlap.similarity("그거 아니야!", "그거아니야") == 1.0
    assert overlap.similarity("", "가") == 0.0
    assert 0 < overlap.similarity("오늘 뭐 먹지", "오늘 뭐 먹을까") < 1


def test_batch_map_back(tmp_path):
    region = {"id": 0, "start": 5.0, "end": 6.0, "speakers": ["A", "B"]}
    src = np.random.default_rng(0).normal(0, 0.1, (2, 16000 * 3)).astype(np.float32)
    p = overlap.Plan(region=region, w0=4.0, w1=7.0, speakers=["A", "B"], sims=[0.5, 0.5],
                     match_conf=0.2, energy_db=[-20.0, -20.0], sources=src)
    idx = overlap.build_batch([p], 16000, tmp_path / "b.wav")
    assert len(idx) == 2 and abs(idx[0][2] - overlap.GAP) < 1e-6
    off1 = idx[1][2]
    words = [{"start": overlap.GAP + 1.2, "end": overlap.GAP + 1.5, "text": "가"},
             {"start": off1 + 1.1, "end": off1 + 1.4, "text": "나"}]
    per = overlap.map_back(words, idx, [p])
    assert per[(0, 0)][0]["start"] == 5.2 and per[(0, 1)][0]["text"] == "나"
