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


def E(i, spk, s, e, text="말"):
    return {"id": i, "speaker": spk, "start": s, "end": e, "text": text, "overlap": False}


def test_assign_lanes_fixed_position():
    # SPEC-008: 비어 있는 가장 아래 줄에 넣고, 끝날 때까지 줄을 바꾸지 않는다
    ev = [E(0, "S1", 0.0, 4.0), E(1, "S2", 1.0, 2.0), E(2, "S3", 1.5, 3.0), E(3, "S2", 2.5, 5.0),
          E(4, "_sfx", 0.0, 9.0), E(5, "S1", 6.0, 7.0)]
    lane, n = captions.assign_lanes(ev)
    assert lane == {0: 0, 1: 1, 2: 2, 3: 1, 5: 0} and n == 3
    assert 4 not in lane  # 소리 자막은 줄을 차지하지 않음


def test_fit_lines_by_measured_width():
    m = captions._Measure()
    text = "그녀는 그 과정을 힘들어하지 않고 재미있게 받아들인다"
    assert captions._fit_lines(text, 30, 10_000, m) == [text]
    lines = captions._fit_lines(text, 30, m(text, 30) * 0.6, m)
    assert len(lines) == 2 and " ".join(lines) == text


def test_burn_ass_top_lanes_offscreen_and_outlines():
    speakers = [{"id": "S1", "name": "화자 1", "color": "#FFD84D"}, {"id": "S2", "name": "화자 2", "color": "#5FD3FF"}]
    spk = captions.resolve_speakers(speakers, {})
    ev = [E(0, "S1", 0.0, 2.0, "안녕하세요"), E(1, "S2", 1.0, 3.0, "반가워요"), E(2, "_sfx", 0.0, 1.0, "[웃음]")]
    ev[1]["offscreen"] = True
    vis = {"fps": 5, "frames": [{"t": 0.4, "hl": [{"spk": "S1", "poly": [[0.1, 0.2], [0.3, 0.2], [0.2, 0.9]]}]}]}
    lines = captions.to_ass_burn(ev, spk, 1280, 720, vis).splitlines()
    bub = {t: x for x in lines if "Bubble," in x for t in ("안녕하세요", "반가워요") if t in x}
    y = {t: float(x.split("\\pos(")[1].split(",")[1].split(")")[0]) for t, x in bub.items()}
    assert y["안녕하세요"] < y["반가워요"] < 720 * 0.3          # 위쪽, 먼저 시작한 말이 첫 줄
    assert "[화면 밖]" in bub["반가워요"] and "[화면 밖]" not in bub["안녕하세요"]
    assert "&H00FFD35F" in bub["반가워요"]                      # 글자·테두리 = 화자 색(BGR)
    outl = [x for x in lines if x.startswith("Dialogue: 0,0:00:00.30,0:00:00.50,Shape")]
    assert outl and "m 128 144 l 384 144 256 648" in outl[0] and "&H004DD8FF" in outl[0]
    assert any(x.startswith("Dialogue: 9,") and "[웃음]" in x for x in lines)


# ───────────── SPEC-009: 화면 속 화자 · 잡음 ─────────────

def test_link_tracks_iou_and_cut():
    from whosaid.pipeline import visual as V
    z = np.zeros((5, 2), np.float32)
    d = lambda t, x: V.Det(t=t, box=(x, 10, 40, 40), lm=z, score=0.9)  # noqa: E731
    frames = [(0.0, [d(0.0, 10), d(0.0, 200)]), (0.1, [d(0.1, 12), d(0.1, 202)]), (0.2, [d(0.2, 14)]),
              (0.3, [d(0.3, 16)])]
    tr = V.link_tracks(frames, cuts={0.3})
    assert sorted(len(t.dets) for t in tr) == [1, 2, 3]  # 장면 전환(0.3)에서 끊김


def test_cluster_same_person():
    from whosaid.pipeline import visual as V
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=128), rng.normal(size=128)
    embs = [a + 0.2 * rng.normal(size=128), a + 0.2 * rng.normal(size=128), b + 0.2 * rng.normal(size=128)]
    lab = V.cluster(embs, 0.42)
    assert lab[0] == lab[1] != lab[2]


def _obs(times, act):
    return [(round(t, 2), act(t)) for t in times]


def test_associate_cooccurrence_and_lips():
    from whosaid.pipeline import visual as V
    # A가 0~10초, B가 10~20초 말함. P1은 0~12초 보이고 A 때 입을 움직임. P2는 8~20초 보이고 B 때 움직임.
    # 8~10초에는 둘 다 보이는데 A가 말하므로 P1 입만 움직임(여러 얼굴 대비).
    excl = [{"start": 0, "end": 10, "speaker": "A"}, {"start": 10, "end": 20, "speaker": "B"}]
    ts = np.arange(0, 20, 0.1)
    p1 = _obs([t for t in ts if t < 12], lambda t: 1.0 if t < 10 else 0.1)
    p2 = _obs([t for t in ts if t >= 8], lambda t: 1.0 if t >= 10 else 0.1)
    mapping, table = V.associate({"P1": p1, "P2": p2}, excl)
    assert mapping == {"A": "P1", "B": "P2"}
    assert table[("P1", "A")]["multi"] > 0 > table[("P2", "A")]["multi"]


def test_associate_refuses_without_evidence():
    from whosaid.pipeline import visual as V
    # 화자 B는 P1이 보일 때 1초만 말함 → 근거 부족, 연결하지 않음. 화자 C는 P1이 보일 때 말한 적이 없음.
    excl = [{"start": 0, "end": 1, "speaker": "B"}, {"start": 30, "end": 40, "speaker": "C"}]
    p1 = _obs(np.arange(0, 10, 0.1), lambda t: 0.5)
    mapping, _ = V.associate({"P1": p1}, excl)
    assert mapping == {}


def test_offscreen_flags():
    from whosaid.pipeline import visual as V
    ev = [E(0, "S1", 0, 2), E(1, "S1", 5, 7), E(2, "S2", 0, 1), E(3, "_sfx", 0, 1)]
    V.offscreen_flags(ev, {"S1": [[0.0, 2.5]]}, {"S1"}, any_face=True)
    assert [e["offscreen"] for e in ev] == [False, True, True, False]
    V.offscreen_flags(ev, {}, set(), any_face=False)  # 얼굴이 하나도 없는 영상은 표시하지 않음
    assert not any(e["offscreen"] for e in ev)


def test_intervals():
    from whosaid.pipeline import visual as V
    assert V.intervals([0.0, 0.1, 0.2, 1.0], 0.1) == [[0.0, 0.3], [1.0, 1.1]]


def test_noise_filter_words_and_speakers():
    from whosaid.pipeline import noise
    ws = [{"start": 0.0, "end": 0.3, "text": "네", "conf": 0.9}, {"start": 0.4, "end": 0.8, "text": "맞아요", "conf": 0.2},
          {"start": 5.0, "end": 5.2, "text": "쿵", "conf": 0.4}, {"start": 9.0, "end": 9.3, "text": "와", "conf": 0.9}]
    kept, n = noise.filter_words(ws, "clova")
    assert [w["text"] for w in kept] == ["네", "와"] and n == 2  # 낮은 신뢰도, 신뢰도 낮은 외톨이
    junk = [{"start": 10 + i * 0.3, "end": 10.25 + i * 0.3, "text": x, "conf": 0.9}
            for i, x in enumerate(["시청해", "주셔서", "감사합니다."])]
    kept, n = noise.filter_words(ws[:1] + junk, "whisper")
    assert [w["text"] for w in kept] == ["네"] and n == 3
    turns = [{"start": 0, "end": 10, "speaker": "A"}, {"start": 10, "end": 10.6, "speaker": "N"}]
    assert noise.noise_speakers(turns, [{"start": 10.1, "end": 10.3, "text": "흠"}]) == {"N"}


def test_label_bodies_keeps_person_when_face_turns_away():
    from whosaid.pipeline import visual as V
    # 사람 둘이 걷는다. 0~0.4초에 P1 얼굴이 왼쪽 몸에서 보이고(3번), 그 뒤엔 뒤돌아 얼굴이 없다.
    left = lambda t: [10 + t * 10, 10, 110 + t * 10, 300]   # noqa: E731
    right = lambda t: [300, 10, 400, 300]                    # noqa: E731
    frames = []
    for i in range(10):
        t = round(i * 0.2, 2)
        links = {"P1": 0} if i < 3 else {}
        frames.append((t, [left(t), right(t)], links))
    lab = V.label_bodies(frames)
    assert all(f.get(0) == "P1" for f in lab)        # 얼굴이 안 보여도 같은 몸은 P1
    assert all(1 not in f for f in lab)              # 얼굴 확인이 없는 몸은 모름
    # 장면 전환 뒤의 몸은 이어 붙이지 않는다
    lab2 = V.label_bodies(frames, cuts={1.0})
    assert lab2[4].get(0) == "P1" and lab2[6] == {}
    # 얼굴 확인이 1번뿐이면 믿지 않는다
    one = [(t, b, ({"P1": 0} if i == 0 else {})) for i, (t, b, _) in enumerate(frames)]
    assert all(f == {} for f in V.label_bodies(one))
