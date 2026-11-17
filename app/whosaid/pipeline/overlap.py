"""겹친 발화 복원.

일반 자막 엔진은 두 사람이 동시에 말하면 더 큰 목소리 한쪽만 받아 적거나 두 말을 섞어 버립니다.
이 모듈은 화자 분리가 찾아낸 '겹침 구간'마다:
  1) 구간 앞뒤 문맥을 포함해 오디오를 잘라 SepFormer로 두 목소리를 분리하고
  2) 분리된 각 목소리를 화자 임베딩으로 실제 화자에게 매칭한 뒤
  3) 모든 분리 음성을 '무음 간격을 둔 한 파일'로 이어 붙여 한 번에 재인식(배치 재인식)하고
  4) 원래 인식 결과와 비교해 (a) 잘못 배정된 단어를 바로잡고 (b) 묻혀서 빠진 화자의 말을 추가합니다.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import diarize, media, separate

log = logging.getLogger(__name__)

MIN_REGION = 0.4      # 이보다 짧은 겹침은 처리하지 않음(초)
CONTEXT = 1.5         # 겹침 구간 앞뒤로 붙이는 문맥(초)
MAX_WINDOW = 12.0     # 분리할 창의 최대 길이(초)
GAP = 1.2             # 배치 재인식 파일에서 조각 사이 무음(초)
EDGE = 0.15           # 구간 경계 허용 오차(초)
PRIOR = 0.05          # 화자 분리가 그 구간에 표시한 화자에게 주는 가산점(코사인)
NEAR = 0.8            # 같은 단어로 볼 시간 거리(초)
WORD_SIM = 0.6        # 같은 단어로 볼 글자 유사도
_PUNCT = re.compile(r"[\s\.,\?!…~\-\"'“”‘’()\[\]]+")


def _norm(text: str) -> str:
    return _PUNCT.sub("", text or "")


def similarity(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _text(ws: list[dict]) -> str:
    return " ".join(w["text"] for w in ws).strip()


@dataclass
class Plan:
    region: dict
    w0: float
    w1: float
    speakers: list[str]                      # 분리 출력 0,1 에 매칭된 화자
    sims: list[float]                        # 매칭된 화자와의 코사인 유사도
    match_conf: float                        # 두 매칭 경우의 점수 차(클수록 확실)
    energy_db: list[float]                   # 겹침 구간 안 분리음 에너지
    sources: np.ndarray | None = field(default=None, repr=False)


def _coverage(turns: list[dict], spk: str, a: float, b: float) -> float:
    return sum(max(0.0, min(t["end"], b) - max(t["start"], a)) for t in turns if t["speaker"] == spk)


def plan_regions(wav: np.ndarray, sr: int, overlaps: list[dict], turns: list[dict],
                 centroids: dict[str, np.ndarray], max_regions: int = 150,
                 progress: Callable[[float], None] | None = None) -> list[Plan]:
    regions = [r for r in overlaps if r["end"] - r["start"] >= MIN_REGION]
    regions.sort(key=lambda r: r["end"] - r["start"], reverse=True)
    regions = sorted(regions[:max_regions], key=lambda r: r["start"])
    dur = len(wav) / sr
    plans: list[Plan] = []
    for k, r in enumerate(regions):
        if progress:
            progress(k / max(len(regions), 1))
        cand = sorted(r["speakers"], key=lambda s: _coverage(turns, s, r["start"], r["end"]), reverse=True)[:2]
        if len(cand) < 2 or len(centroids) < 2:
            continue
        rel = [t for t in turns if t["speaker"] in cand and t["end"] > r["start"] and t["start"] < r["end"]]
        w0 = max(min(t["start"] for t in rel), r["start"] - CONTEXT, 0.0)
        w1 = min(max(t["end"] for t in rel), r["end"] + CONTEXT, dur)
        if w1 - w0 > MAX_WINDOW:  # 겹침 구간을 가운데 두고 자르기
            c = (r["start"] + r["end"]) / 2
            w0, w1 = max(0.0, c - MAX_WINDOW / 2), min(dur, c + MAX_WINDOW / 2)
        clip = wav[int(w0 * sr): int(w1 * sr)]
        if len(clip) < int(0.8 * sr):
            continue
        try:
            src = separate.separate(clip, sr)
        except Exception:  # noqa: BLE001
            log.exception("분리 실패: 구간 %s", r)
            continue
        a, b = int((r["start"] - w0) * sr), int((r["end"] - w0) * sr)
        energy = [separate.rms_db(src[i, a:b]) for i in range(2)]
        # 임베딩은 겹침 구간 ±0.5초(최소 1.2초)에서 계산
        ea = max(0, int((r["start"] - 0.5 - w0) * sr))
        eb = min(len(clip), int((r["end"] + 0.5 - w0) * sr))
        if eb - ea < int(1.2 * sr):
            ea, eb = 0, len(clip)
        embs = [diarize.embed(src[i, ea:eb], sr) for i in range(2)]
        if any(e is None for e in embs):
            continue
        spk, sims, conf = match_speakers(embs, centroids, r["speakers"])
        if spk is None:
            continue
        plans.append(Plan(region=r, w0=w0, w1=w1, speakers=spk, sims=sims,
                          match_conf=conf, energy_db=energy, sources=src))
    return plans


def match_speakers(embs: list[np.ndarray], centroids: dict[str, np.ndarray], region_speakers: list[str]):
    """분리된 두 목소리를 '모든' 화자의 대표 목소리와 비교해 서로 다른 두 화자를 고릅니다.

    화자 분리는 겹친 구간의 두 번째 화자를 엉뚱한 사람으로 표시하는 일이 잦아서, 그 구간에 표시된
    화자에게는 가산점(PRIOR)만 주고 최종 선택은 목소리 유사도로 합니다. 둘 다 구간 밖 화자인
    조합은 믿지 않고 구간 표시 화자들 안에서 다시 고릅니다.
    """
    names = list(centroids)
    raw = [[float(e @ centroids[x]) for x in names] for e in embs]
    score = [[raw[i][j] + (PRIOR if names[j] in region_speakers else 0.0) for j in range(len(names))] for i in range(2)]
    pairs = sorted(((score[0][a] + score[1][b], a, b) for a in range(len(names)) for b in range(len(names)) if a != b),
                   reverse=True)
    pairs_ok = [p for p in pairs if names[p[1]] in region_speakers or names[p[2]] in region_speakers]
    if not pairs_ok:
        return None, None, 0.0
    best = pairs_ok[0]
    second = pairs_ok[1][0] if len(pairs_ok) > 1 else best[0] - 1.0
    a, b = best[1], best[2]
    return [names[a], names[b]], [raw[0][a], raw[1][b]], (best[0] - second) / 2


def build_batch(plans: list[Plan], sr: int, out_wav: Path, min_rel_db: float = -18.0) -> list[tuple]:
    """분리 음성들을 무음 간격을 두고 한 파일로 이어 붙입니다. 반환: [(plan_idx, src_idx, offset, length)]"""
    pieces, index, cursor = [], [], 0.0
    gap = np.zeros(int(GAP * sr), dtype=np.float32)
    pieces.append(gap)
    cursor += GAP
    for pi, p in enumerate(plans):
        loud = max(p.energy_db)
        for si in range(2):
            if p.energy_db[si] < loud + min_rel_db:  # 거의 비어 있는 출력은 건너뜀
                continue
            seg = separate.normalize(p.sources[si])
            index.append((pi, si, cursor, len(seg) / sr))
            pieces.append(seg)
            pieces.append(gap)
            cursor += len(seg) / sr + GAP
    if not index:
        return []
    media.write_wav(out_wav, np.concatenate(pieces), sr)
    return index


def map_back(words: list[dict], index: list[tuple], plans: list[Plan]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        for pi, si, off, length in index:
            if off - 0.05 <= mid <= off + length + 0.05:
                base = plans[pi].w0 - off
                out.setdefault((pi, si), []).append({
                    "start": round(w["start"] + base, 3), "end": round(w["end"] + base, 3),
                    "text": w["text"], "conf": w.get("conf"),
                })
                break
    return out


def _mid(w: dict) -> float:
    return (w["start"] + w["end"]) / 2


def _has_match(word: dict, pool: list[dict]) -> float:
    """pool 안에서 시간상 가까운(NEAR) 단어 중 가장 비슷한 글자 유사도."""
    best = 0.0
    for q in pool:
        if abs(_mid(q) - _mid(word)) <= NEAR:
            best = max(best, similarity(word["text"], q["text"]))
    return best


def resolve(plans: list[Plan], per_source: dict[tuple, list[dict]], main_words: list[dict]):
    """반환: (복원 단어 목록, 화자 재배정 목록 [(단어 index, 새 화자)], 구간별 상세)

    1) 원래 자막의 단어마다, 두 분리음 중 어느 쪽에 같은 단어가 같은 시각에 있는지 보고 주인을 정한다
       (한쪽에만 뚜렷이 있을 때만 옮김).
    2) 화자별로, 분리음 단어 중 그 화자의 원래 자막(구간 ±1초)에 이미 있는 단어는 빼고 나머지를 복원한다.
    3) 복원하려는 말이 상대 화자의 원래 자막과 거의 같으면 새어 들어온 소리로 보고 버린다.
    """
    recovered, reassign, details = [], [], []
    for pi, p in enumerate(plans):
        r = p.region
        lo, hi = r["start"] - EDGE, r["end"] + EDGE
        A, B = p.speakers
        src = {p.speakers[si]: [w for w in per_source.get((pi, si), []) if lo <= _mid(w) <= hi] for si in range(2)}
        # 분리 실패로 두 분리음이 같은 말이면 에너지가 큰 쪽만 남김
        if src[A] and src[B] and similarity(_text(src[A]), _text(src[B])) >= 0.6:
            weaker = B if p.energy_db[0] >= p.energy_db[1] else A
            src[weaker] = []
        uncertain = p.match_conf < 0.05
        m_idx = [i for i, w in enumerate(main_words) if lo <= _mid(w) <= hi]
        m_text = _text([main_words[i] for i in m_idx])
        cur = {i: main_words[i].get("speaker") for i in m_idx}

        moved = 0
        if not uncertain:
            for i in m_idx:
                w = main_words[i]
                sa, sb = _has_match(w, src[A]), _has_match(w, src[B])
                best, s_best, s_other = (A, sa, sb) if sa >= sb else (B, sb, sa)
                if s_best >= WORD_SIM and s_best - s_other >= 0.2 and cur[i] != best:
                    cur[i] = best
                    reassign.append((i, best))
                    moved += 1

        added = []
        win_lo, win_hi = r["start"] - 1.0, r["end"] + 1.0
        for spk in (A, B):
            if not src[spk]:
                continue
            mine = [main_words[i] for i in range(len(main_words))
                    if win_lo <= _mid(main_words[i]) <= win_hi and cur.get(i, main_words[i].get("speaker")) == spk]
            new = [w for w in src[spk] if _has_match(w, mine) < WORD_SIM]
            if not new:
                continue
            other_text = _text([main_words[i] for i in m_idx if cur[i] != spk])
            if other_text and similarity(_text(new), other_text) >= 0.6:
                continue
            for w in new:
                recovered.append({**w, "speaker": spk, "recovered": True, "uncertain": uncertain, "region": r["id"]})
            added.append({"speaker": spk, "text": _text(new)})
        action = "+".join(x for x in (("reassign" if moved else ""), ("recover" if added else "")) if x) or "keep"
        details.append({
            "region": r["id"], "start": r["start"], "end": r["end"], "speakers": p.speakers,
            "region_labels": r["speakers"], "sims": [round(x, 3) for x in p.sims],
            "match_conf": round(p.match_conf, 3), "energy_db": [round(x, 1) for x in p.energy_db],
            "main_text": m_text, "sep_text": {A: _text(src[A]), B: _text(src[B])},
            "moved_words": moved, "action": action, "added": added,
        })
    return recovered, reassign, details
