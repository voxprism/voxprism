"""전체 처리 흐름(워커가 호출).

  준비(ffmpeg) → 음성 인식(CLOVA Speech) → 잡음 거르기 → 화자 분리(pyannote) → 단어-화자 배정
  → 겹친 발화 복원(분리·재인식·매칭) → 화면 속 화자 찾기(얼굴–목소리 연결, 윤곽)
  → 자막 이벤트(화면 밖 표시) · 화자 카드 · 자막 파일
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .. import config, store, subtitles
from . import asr, assign, captions, diarize, media, noise, overlap, visual

log = logging.getLogger("whosaid.pipeline")

STAGE_RANGE = {"prepare": (0, 7), "asr": (7, 27), "diarize": (27, 50), "overlap": (50, 74), "visual": (74, 93),
               "captions": (93, 99)}


class UserError(RuntimeError):
    """사용자에게 그대로 보여줄 수 있는 오류."""


class Progress:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._last = 0.0

    def __call__(self, stage: str, frac: float = 0.0, message: str | None = None, force: bool = False) -> None:
        now = time.time()
        if not force and frac > 0 and now - self._last < 0.7:
            return
        self._last = now
        lo, hi = STAGE_RANGE[stage]
        store.set_status(self.job_id, state="running", stage=stage,
                         progress=round(lo + (hi - lo) * min(max(frac, 0.0), 1.0), 1),
                         message=message or "")


def _attach_job_log(d: Path) -> logging.Handler:
    h = logging.FileHandler(d / "job.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)
    return h


def build_speakers(events: list[dict], turns: list[dict]) -> tuple[list[dict], dict[str, str]]:
    talk: dict[str, float] = {}
    for t in turns:
        talk[t["speaker"]] = talk.get(t["speaker"], 0.0) + (t["end"] - t["start"])
    lines: dict[str, list[dict]] = {}
    for e in events:
        if e["speaker"] not in ("UNK", captions.SFX_ID):
            lines.setdefault(e["speaker"], []).append(e)
    order = sorted(lines, key=lambda s: (-talk.get(s, 0.0), -len(lines[s])))
    id_map = {raw: f"S{i + 1}" for i, raw in enumerate(order)}
    speakers = []
    for i, raw in enumerate(order):
        evs = lines[raw]
        speakers.append({
            "id": id_map[raw], "raw": raw, "name": f"화자 {i + 1}",
            "color": captions.PALETTE[i % len(captions.PALETTE)],
            "talk_time": round(talk.get(raw, sum(e["end"] - e["start"] for e in evs)), 1),
            "lines": len(evs), "recovered_lines": sum(1 for e in evs if e.get("recovered")),
            "samples": [e["text"] for e in sorted(evs, key=lambda e: -len(e["text"]))[:2]],
            "thumbs": [],
        })
    return speakers, id_map


def _thumbnails(d: Path, video: Path, speakers: list[dict], turns: list[dict], overlaps: list[dict],
                id_map: dict[str, str]) -> None:
    (d / "thumbs").mkdir(exist_ok=True)
    rev = {v: k for k, v in id_map.items()}
    for s in speakers:
        raw = rev.get(s["id"])
        mine = [t for t in turns if t["speaker"] == raw]
        # 혼자 말하는(겹치지 않는) 긴 구간의 가운데 장면을 고름
        def alone(t):
            return not any(o["start"] < t["end"] and o["end"] > t["start"] for o in overlaps)
        cands = sorted(mine, key=lambda t: (alone(t), t["end"] - t["start"]), reverse=True)
        picks: list[float] = []
        for t in cands:
            mid = (t["start"] + t["end"]) / 2
            if all(abs(mid - p) > 5 for p in picks):
                picks.append(mid)
            if len(picks) >= 3:
                break
        for k, t in enumerate(sorted(picks)):
            out = d / "thumbs" / f"{s['id']}_{k}.jpg"
            if media.grab_frame(video, t, out):
                s["thumbs"].append({"file": f"thumbs/{out.name}", "t": round(t, 2)})


def _apply_visual(d: Path, V: dict | None, speakers: list[dict], id_map: dict[str, str], events: list[dict],
                  pinfo: dict) -> int:
    """화면 분석 결과를 S 번호로 바꿔 visual.json 으로 쓰고, 자막에 '화면 밖'을, 화자 카드에 얼굴을 붙인다.
    돌려줌: 얼굴과 연결된 화자 수."""
    for e in events:
        e["offscreen"] = False
    if not V:
        (d / "visual.json").unlink(missing_ok=True)
        return 0
    face_of = {id_map[r]: p for r, p in V["speaker_face"].items() if r in id_map}
    visible = {id_map[r]: iv for r, iv in V["visible"].items() if r in id_map}
    visual.offscreen_flags(events, visible, set(face_of), V["any_face"])
    faces = visual.save_faces(d / "preview.mp4", (pinfo.get("width") or 1280, pinfo.get("height") or 720),
                              {p: V["_face_pick"].get(p) for p in face_of.values()}, d / "faces")
    for s in speakers:
        p = face_of.get(s["id"])
        s["person"] = p
        s["face"] = faces.get(p) if p else None
    frames = []
    for f in V["frames"]:
        hl = [dict(h, spk=id_map[h["spk"]]) for h in f["hl"] if h["spk"] in id_map]
        if hl:
            frames.append({"t": f["t"], "hl": hl})
    out = {k: v for k, v in V.items() if not k.startswith("_")}
    out.update({"speaker_face": face_of, "visible": visible, "frames": frames,
                "people": [dict(x, speaker=id_map.get(x["speaker"])) if x.get("speaker") else x for x in V["people"]],
                "scores": [dict(x, speaker=id_map.get(x["speaker"], x["speaker"])) for x in V["scores"]]})
    store.write_json(d / "visual.json", out)
    return len(face_of)


def process(job_id: str) -> None:
    d = store.job_dir(job_id)
    opts = store.get_options(job_id)
    P = Progress(job_id)
    handler = _attach_job_log(d)
    t0 = time.time()
    timings: dict[str, float] = {}
    warnings: list[str] = []
    store.set_status(job_id, state="running", stage="prepare", progress=0, message="시작합니다",
                     started_at=t0, warnings=[])
    try:
        src = d / opts["input"]
        # ── 1. 준비 ──────────────────────────────────────────
        P("prepare", 0.05, "영상 정보를 확인하고 있어요", force=True)
        info = media.probe(src)
        if not info["has_audio"]:
            raise UserError("소리(오디오 트랙)가 없는 파일입니다.")
        if info["duration"] > config.MAX_DURATION_SEC:
            raise UserError(f"영상 길이는 최대 {int(config.MAX_DURATION_SEC // 60)}분까지 처리할 수 있어요.")
        wav_path = d / "audio.wav"
        media.extract_audio(src, wav_path)
        P("prepare", 0.35, "재생용 영상을 만들고 있어요", force=True)
        media.make_preview(src, d / "preview.mp4", info)
        pinfo = media.probe(d / "preview.mp4")
        wav, sr = media.load_wav(wav_path)
        timings["prepare"] = round(time.time() - t0, 1)

        # ── 2. 음성 인식 ─────────────────────────────────────
        t = time.time()
        engine = asr.resolve_engine(opts.get("engine"))
        use_pyannote = config.pyannote_available() and opts.get("diarizer", "auto") != "clova"
        n_spk = opts.get("num_speakers") or None
        P("asr", 0.05, "CLOVA Speech로 말소리를 글자로 바꾸고 있어요" if engine == "clova"
          else "Whisper로 말소리를 글자로 바꾸고 있어요", force=True)
        A = asr.recognize(wav_path, engine=engine, diarization=not use_pyannote,
                          speaker_min=n_spk, speaker_max=n_spk, want_sed=bool(opts.get("sound_events", True)))
        engine = A["engine"]
        words, n_noise_words = noise.filter_words(A["words"], engine)
        warnings += A["warnings"]
        store.write_json(d / "asr.json", {k: A[k] for k in ("engine", "words", "sound_events", "warnings")})
        if A.get("raw") is not None:
            store.write_json(d / "asr_raw.json", A["raw"])
        timings["asr"] = round(time.time() - t, 1)
        if not words:
            raise UserError("인식된 말소리가 없습니다. 대화가 있는 영상인지 확인해 주세요.")

        # ── 3. 화자 분리 ─────────────────────────────────────
        t = time.time()
        diar_model = None
        turns: list[dict] = []
        excl: list[dict] = []
        if use_pyannote:
            P("diarize", 0.0, "목소리로 누가 말했는지 구분하고 있어요", force=True)
            try:
                D = diarize.diarize(wav, sr, num_speakers=n_spk,
                                    progress=lambda f: P("diarize", f, "목소리로 누가 말했는지 구분하고 있어요"))
                turns, excl, diar_model = D["turns"], D["exclusive"], D["model"]
            except Exception as e:  # noqa: BLE001
                log.exception("pyannote 실패")
                warnings.append(f"pyannote 화자 분리 실패로 CLOVA Speech 화자 정보를 사용했습니다: {str(e)[:120]}")
                use_pyannote = False
        if not use_pyannote:
            if engine == "clova" and not any(w.get("src_spk") for w in words):
                P("diarize", 0.3, "CLOVA Speech 화자 인식을 요청하고 있어요", force=True)
                A2 = asr.recognize(wav_path, engine="clova", diarization=True, speaker_min=n_spk, speaker_max=n_spk)
                words = A2["words"]
            if engine == "clova":
                turns = diarize.turns_from_words(words)
                excl = diarize.exclusive_from_turns(turns)
                diar_model = "clova-speech"
            else:
                turns = [{"start": 0.0, "end": info["duration"], "speaker": "1"}]
                excl = list(turns)
                diar_model = "none"
                warnings.append("화자 분리 모델을 쓸 수 없어 모든 말을 한 화자로 표시합니다.")
        noisy = noise.noise_speakers(turns, words)
        if noisy:
            log.info("잡음 화자 제거: %s", sorted(noisy))
            turns = [x for x in turns if x["speaker"] not in noisy]
            excl = [x for x in excl if x["speaker"] not in noisy]
        overlaps = diarize.overlap_regions(turns) if use_pyannote else []
        store.write_json(d / "diarization.json",
                         {"model": diar_model, "turns": turns, "exclusive": excl, "overlaps": overlaps})
        assign.assign_words(words, excl, turns)
        timings["diarize"] = round(time.time() - t, 1)

        # ── 4. 겹친 발화 복원 ────────────────────────────────
        t = time.time()
        recovered: list[dict] = []
        details: list[dict] = []
        n_plans = 0
        if use_pyannote and overlaps and opts.get("recover_overlap", True):
            P("overlap", 0.0, f"겹친 말 {len(overlaps)}곳을 분리하고 있어요", force=True)
            cents = diarize.speaker_centroids(wav, sr, turns, overlaps)
            plans = overlap.plan_regions(
                wav, sr, overlaps, turns, cents,
                progress=lambda f: P("overlap", 0.7 * f, f"겹친 말 {len(overlaps)}곳을 분리하고 있어요"))
            n_plans = len(plans)
            if plans:
                P("overlap", 0.72, "분리한 목소리를 다시 인식하고 있어요", force=True)
                batch = d / "overlap_batch.wav"
                index = overlap.build_batch(plans, sr, batch)
                if index:
                    bw = asr.recognize_batch(batch, engine)
                    per = overlap.map_back(bw, index, plans)
                    recovered, reassign, details = overlap.resolve(plans, per, words)
                    for i, spk in reassign:
                        words[i]["speaker"] = spk
                        words[i]["reassigned"] = True
                    batch.unlink(missing_ok=True)
        store.write_json(d / "overlap.json", {"n_regions": len(overlaps), "n_processed": n_plans,
                                              "n_recovered_words": len(recovered), "regions": details})
        timings["overlap"] = round(time.time() - t, 1)

        # ── 5. 화면 속 화자 찾기 (SPEC-009) ───────────────────
        t = time.time()
        V = None
        if info["has_video"] and opts.get("visual", True) and turns:
            if visual.models_ready(config.VISION_DIR):
                P("visual", 0.0, "화면 속 얼굴을 찾고 있어요", force=True)
                try:
                    V = visual.analyze(d / "preview.mp4", (pinfo.get("width") or 1280, pinfo.get("height") or 720),
                                       turns, excl, d / "faces", config.VISION_DIR,
                                       progress=lambda f, m="": P("visual", f, m or "화면 속 사람을 찾고 있어요"),
                                       threads=config.CPU_THREADS)
                except Exception as e:  # noqa: BLE001
                    log.exception("화면 분석 실패")
                    warnings.append(f"화면 속 화자 찾기에 실패해 윤곽 강조 없이 자막만 만들었습니다: {str(e)[:120]}")
            else:
                warnings.append("화면 분석 모델이 설치되지 않아 말하는 사람 윤곽 강조를 건너뛰었습니다.")
        timings["visual"] = round(time.time() - t, 1)

        # ── 6. 자막 ──────────────────────────────────────────
        t = time.time()
        P("captions", 0.1, "자막과 화자 카드를 만들고 있어요", force=True)
        events = captions.build_events(words + recovered)
        speakers, id_map = build_speakers(events, turns)
        for e in events:
            e["speaker"] = id_map.get(e["speaker"], e["speaker"])
        if opts.get("sound_events", True):
            events += captions.sound_events(A.get("sound_events") or [])
        events.sort(key=lambda e: (e["start"], e["end"]))
        captions.mark_overlaps(events)
        for i, e in enumerate(events):
            e["id"] = i
        onscreen = _apply_visual(d, V, speakers, id_map, events, pinfo)
        if info["has_video"]:
            P("captions", 0.4, "화자별 장면을 고르고 있어요", force=True)
            _thumbnails(d, d / "preview.mp4", speakers, turns, overlaps, id_map)
        timings["captions"] = round(time.time() - t, 1)
        timings["total"] = round(time.time() - t0, 1)

        stats = {
            "duration": round(info["duration"], 1),
            "speakers": len(speakers),
            "lines": sum(1 for e in events if e["speaker"] != captions.SFX_ID),
            "overlap_regions": len(overlaps),
            "overlap_seconds": round(sum(o["end"] - o["start"] for o in overlaps), 1),
            "overlap_lines": sum(1 for e in events if e.get("overlap")),
            "recovered_lines": sum(1 for e in events if e.get("recovered")),
            "reassigned_words": sum(1 for w in words if w.get("reassigned")),
            "sound_lines": sum(1 for e in events if e["speaker"] == captions.SFX_ID),
            "noise_words": n_noise_words,
            "noise_speakers": len(noisy),
            "onscreen_speakers": onscreen,
            "offscreen_lines": sum(1 for e in events if e.get("offscreen")),
        }
        result = {
            "job_id": job_id,
            "engine": engine, "diarization_model": diar_model,
            "video": {"width": pinfo.get("width") or 1280, "height": pinfo.get("height") or 720,
                      "has_video": info["has_video"]},
            "speakers": speakers, "events": events, "stats": stats, "timings": timings,
        }
        store.write_json(d / "result.json", result)
        subtitles.write_all(job_id)
        store.write_json(d / "summary.json", {"duration": stats["duration"], "speakers": stats["speakers"],
                                              "recovered_lines": stats["recovered_lines"]})
        store.set_status(job_id, state="done", stage="done", progress=100, message="완료",
                         finished_at=time.time(), timings=timings, warnings=warnings)
        log.info("작업 완료 %s: %s", job_id, stats)
    except UserError as e:
        store.set_status(job_id, state="error", message=str(e), warnings=warnings)
    except Exception as e:  # noqa: BLE001
        log.exception("작업 실패 %s", job_id)
        store.set_status(job_id, state="error", message="처리 중 오류가 발생했습니다.",
                         detail=f"{type(e).__name__}: {str(e)[:500]}", warnings=warnings)
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def render(job_id: str) -> None:
    """자막을 영상에 입힌 MP4 생성 (사용자가 요청할 때만)."""
    d = store.job_dir(job_id)
    req = d / "render.request"
    store.write_json(d / "render.json", {"state": "running", "started_at": time.time()})
    try:
        subtitles.write_all(job_id)
        media.burn_in(d / "preview.mp4", subtitles.write_burn(job_id), d / "burned.mp4")
        store.write_json(d / "render.json", {"state": "done", "finished_at": time.time()})
    except Exception as e:  # noqa: BLE001
        log.exception("렌더 실패 %s", job_id)
        store.write_json(d / "render.json", {"state": "error", "message": str(e)[:300]})
    finally:
        req.unlink(missing_ok=True)
