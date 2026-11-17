"""인식된 단어를 화자에게 배정합니다 (WhisperX 방식의 시간 겹침 기준)."""
from __future__ import annotations

import bisect


def _covering(turns: list[dict], starts: list[float], t: float) -> list[dict]:
    i = bisect.bisect_right(starts, t)
    out = []
    # 앞쪽 구간 중 t를 덮는 것 (긴 구간도 있으니 넉넉히 뒤로 탐색)
    for j in range(i - 1, max(-1, i - 40), -1):
        if turns[j]["start"] <= t < turns[j]["end"]:
            out.append(turns[j])
    return out


def assign_words(words: list[dict], exclusive: list[dict], turns: list[dict], max_dist: float = 1.0) -> None:
    """각 단어에 'speaker' 키를 채웁니다.

    1) 겹침 없는(exclusive) 화자 구간 중 단어 중앙 시점을 덮는 화자
    2) 없으면 전체 화자 구간 중 단어와 가장 많이 겹치는 화자
    3) 그래도 없으면 max_dist 초 이내에서 가장 가까운 화자
    """
    ex = sorted(exclusive, key=lambda t: t["start"])
    ex_starts = [t["start"] for t in ex]
    tr = sorted(turns, key=lambda t: t["start"])
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        cov = _covering(ex, ex_starts, mid)
        spk = cov[0]["speaker"] if cov else None
        if spk is None and tr:
            best, best_ov = None, 0.0
            for t in tr:
                if t["start"] > w["end"]:
                    break
                ov = min(t["end"], w["end"]) - max(t["start"], w["start"])
                if ov > best_ov:
                    best, best_ov = t, ov
            if best is not None:
                spk = best["speaker"]
        if spk is None and ex:
            nearest = min(ex, key=lambda t: max(t["start"] - mid, mid - t["end"], 0.0))
            dist = max(nearest["start"] - mid, mid - nearest["end"], 0.0)
            if dist <= max_dist:
                spk = nearest["speaker"]
        w["speaker"] = spk or "UNK"
