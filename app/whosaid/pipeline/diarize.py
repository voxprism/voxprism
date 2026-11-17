"""화자 분리(pyannote) · 겹침 구간 계산 · 화자 임베딩(대표 목소리 벡터)."""
from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

from .. import config

log = logging.getLogger(__name__)
_pipe = None
_pipe_name: str | None = None
_emb = None
_lock = threading.Lock()


def _torch():
    import torch
    torch.set_num_threads(config.CPU_THREADS)
    return torch


def get_pipeline():
    """pyannote 화자 분리 파이프라인 (community-1 → 실패 시 3.1)."""
    global _pipe, _pipe_name
    with _lock:
        if _pipe is None:
            torch = _torch()
            from pyannote.audio import Pipeline
            last_err: Exception | None = None
            for name in dict.fromkeys([config.DIARIZATION_MODEL, "pyannote/speaker-diarization-3.1"]):
                try:
                    log.info("pyannote 파이프라인 로드: %s", name)
                    p = Pipeline.from_pretrained(name, token=config.HF_TOKEN)
                    if p is None:
                        raise RuntimeError("from_pretrained가 None을 반환(약관 동의 필요)")
                    p.to(torch.device("cpu"))
                    _pipe, _pipe_name = p, name
                    break
                except Exception as e:  # noqa: BLE001
                    log.warning("파이프라인 %s 로드 실패: %s", name, e)
                    last_err = e
            if _pipe is None:
                raise RuntimeError(f"화자 분리 모델을 불러오지 못했습니다: {last_err}")
        return _pipe


def pipeline_name() -> str | None:
    return _pipe_name


class _Hook:
    """pyannote 진행 단계를 0~1 비율로 바꿔 콜백합니다."""
    WEIGHTS = {"segmentation": (0.0, 0.25), "speaker_counting": (0.25, 0.3),
               "embeddings": (0.3, 0.9), "discrete_diarization": (0.9, 1.0)}

    def __init__(self, cb: Callable[[float], None]):
        self.cb = cb

    def __call__(self, step_name, step_artifact, file=None, total=None, completed=None):
        lo, hi = self.WEIGHTS.get(step_name, (0.0, 1.0))
        frac = hi
        if total and completed is not None:
            frac = lo + (hi - lo) * (completed / max(total, 1))
        try:
            self.cb(min(1.0, max(0.0, frac)))
        except Exception:  # noqa: BLE001
            pass


def diarize(wav: np.ndarray, sr: int, *, num_speakers: int | None = None, min_speakers: int | None = None,
            max_speakers: int | None = None, progress: Callable[[float], None] | None = None) -> dict:
    torch = _torch()
    pipe = get_pipeline()
    kwargs: dict = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)
    else:
        if min_speakers:
            kwargs["min_speakers"] = int(min_speakers)
        if max_speakers:
            kwargs["max_speakers"] = int(max_speakers)
    waveform = torch.from_numpy(np.ascontiguousarray(wav, dtype=np.float32)).unsqueeze(0)
    out = pipe({"waveform": waveform, "sample_rate": sr}, hook=_Hook(progress) if progress else None, **kwargs)
    ann = getattr(out, "speaker_diarization", out)
    excl = getattr(out, "exclusive_speaker_diarization", None)
    turns = [{"start": float(s.start), "end": float(s.end), "speaker": str(lbl)}
             for s, _, lbl in ann.itertracks(yield_label=True)]
    turns.sort(key=lambda t: (t["start"], t["end"]))
    if excl is not None:
        ex_turns = [{"start": float(s.start), "end": float(s.end), "speaker": str(lbl)}
                    for s, _, lbl in excl.itertracks(yield_label=True)]
        ex_turns.sort(key=lambda t: t["start"])
    else:
        ex_turns = exclusive_from_turns(turns)
    return {"turns": turns, "exclusive": ex_turns, "model": _pipe_name}


def exclusive_from_turns(turns: list[dict]) -> list[dict]:
    """겹치는 구간에서는 먼저 말을 시작한 화자를 남겨 한 시점에 한 화자만 있게 만듭니다."""
    bounds = sorted({t["start"] for t in turns} | {t["end"] for t in turns})
    out: list[dict] = []
    for a, b in zip(bounds, bounds[1:]):
        mid = (a + b) / 2
        active = [t for t in turns if t["start"] <= mid < t["end"]]
        if not active:
            continue
        spk = min(active, key=lambda t: t["start"])["speaker"]
        if out and out[-1]["speaker"] == spk and abs(out[-1]["end"] - a) < 1e-6:
            out[-1]["end"] = b
        else:
            out.append({"start": a, "end": b, "speaker": spk})
    return out


def overlap_regions(turns: list[dict], min_dur: float = 0.25, merge_gap: float = 0.2) -> list[dict]:
    """두 명 이상이 동시에 말하는 구간 목록 [{start, end, speakers:[...]}]."""
    bounds = sorted({t["start"] for t in turns} | {t["end"] for t in turns})
    raw: list[dict] = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a <= 1e-6:
            continue
        mid = (a + b) / 2
        active = {t["speaker"] for t in turns if t["start"] <= mid < t["end"]}
        if len(active) >= 2:
            raw.append({"start": a, "end": b, "speakers": set(active)})
    merged: list[dict] = []
    for r in raw:
        if merged and r["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"] = r["end"]
            merged[-1]["speakers"] |= r["speakers"]
        else:
            merged.append(dict(r))
    out = []
    for i, r in enumerate(m for m in merged if m["end"] - m["start"] >= min_dur):
        out.append({"id": i, "start": round(r["start"], 3), "end": round(r["end"], 3),
                    "speakers": sorted(r["speakers"])})
    return out


def turns_from_words(words: list[dict], gap: float = 1.0) -> list[dict]:
    """pyannote를 못 쓸 때: CLOVA Speech가 단 화자 라벨(src_spk)로 발화 구간을 만듭니다."""
    turns: list[dict] = []
    for w in words:
        spk = w.get("src_spk") or "1"
        if turns and turns[-1]["speaker"] == spk and w["start"] - turns[-1]["end"] <= gap:
            turns[-1]["end"] = max(turns[-1]["end"], w["end"])
        else:
            turns.append({"start": w["start"], "end": w["end"], "speaker": spk})
    return turns


# ───────────────────────── 화자 임베딩 ─────────────────────────

def get_embedder():
    global _emb
    with _lock:
        if _emb is None:
            _torch()
            from pyannote.audio import Inference, Model
            log.info("임베딩 모델 로드: %s", config.EMBEDDING_MODEL)
            model = Model.from_pretrained(config.EMBEDDING_MODEL, token=config.HF_TOKEN)
            _emb = Inference(model, window="whole")
        return _emb


def embed(wav: np.ndarray, sr: int) -> np.ndarray | None:
    if wav is None or len(wav) < int(0.5 * sr):
        return None
    torch = _torch()
    inf = get_embedder()
    x = torch.from_numpy(np.ascontiguousarray(wav, dtype=np.float32)).unsqueeze(0)
    v = np.asarray(inf({"waveform": x, "sample_rate": sr})).reshape(-1)
    n = np.linalg.norm(v)
    if not np.isfinite(n) or n == 0:
        return None
    return v / n


def _subtract(intervals: list[tuple[float, float]], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for a, b in intervals:
        pieces = [(a, b)]
        for h0, h1 in holes:
            nxt = []
            for p0, p1 in pieces:
                if h1 <= p0 or h0 >= p1:
                    nxt.append((p0, p1))
                else:
                    if h0 > p0:
                        nxt.append((p0, h0))
                    if h1 < p1:
                        nxt.append((h1, p1))
            pieces = nxt
        out.extend(pieces)
    return out


def speaker_centroids(wav: np.ndarray, sr: int, turns: list[dict], overlaps: list[dict],
                      max_pieces: int = 8, min_len: float = 1.0, max_len: float = 6.0) -> dict[str, np.ndarray]:
    """겹치지 않는(혼자 말하는) 구간들로 화자별 대표 목소리 벡터를 계산합니다."""
    holes = [(o["start"] - 0.1, o["end"] + 0.1) for o in overlaps]
    by_spk: dict[str, list[tuple[float, float]]] = {}
    for t in turns:
        by_spk.setdefault(t["speaker"], []).append((t["start"], t["end"]))
    cents: dict[str, np.ndarray] = {}
    for spk, ivs in by_spk.items():
        pieces = [p for p in _subtract(ivs, holes) if p[1] - p[0] >= min_len]
        if not pieces:  # 혼자 말한 구간이 너무 짧으면 겹침 포함 구간이라도 사용
            pieces = [p for p in ivs if p[1] - p[0] >= 0.6]
        pieces.sort(key=lambda p: p[1] - p[0], reverse=True)
        vecs = []
        for a, b in pieces[:max_pieces]:
            mid = (a + b) / 2
            half = min(b - a, max_len) / 2
            seg = wav[int((mid - half) * sr): int((mid + half) * sr)]
            v = embed(seg, sr)
            if v is not None:
                vecs.append(v)
        if vecs:
            c = np.mean(vecs, axis=0)
            cents[spk] = c / (np.linalg.norm(c) or 1.0)
    return cents
