"""정답(truth.json) 대비 결과(result.json) 평가.

지표
  CER(전체)        화자를 무시하고 시간 순으로 이어 붙인 글자 오류율 — 일반 자막과 같은 기준
  cpCER            화자별로 이어 붙인 글자를 최적의 화자 대응으로 비교한 오류율 (CHiME 'cpWER'의 글자판)
                   → 말한 사람이 틀리면 오류로 잡힘
  발화 재현율       정답 발화 하나하나가 '올바른 화자' 자막에 얼마나 담겼는지 (1-CER 평균)
  겹친 발화 재현율  다른 사람과 겹친 발화만 따로 계산 — 이 프로젝트가 개선하려는 핵심 지표
  누락 발화        재현율 0.3 미만(사실상 사라진) 발화 수

  python tools/evaluate.py --truth testset/x.truth.json --result jobs/<id>/result.json [--result 다른결과.json ...]
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

_STRIP = re.compile(r"[\s\.,\?!…~\-\"'“”‘’()\[\]♪]+")


def norm(s: str) -> str:
    return _STRIP.sub("", s or "")


def edit(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def sub_edit(ref: str, hyp: str) -> int:
    """ref와 'hyp의 어떤 부분 문자열' 사이의 최소 편집 거리 (hyp 앞뒤는 무시)."""
    prev = [0] * (len(hyp) + 1)
    for i, cr in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, ch in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cr != ch))
        prev = cur
    return min(prev)


def recall(ref: str, hyp: str) -> float:
    """정답 발화 글자가 hyp 안에 얼마나 들어 있는가 (1 - 부분 문자열 CER)."""
    ref, hyp = norm(ref), norm(hyp)
    if not ref:
        return 1.0
    if not hyp:
        return 0.0
    return max(0.0, 1 - sub_edit(ref, hyp) / len(ref))


def evaluate(truth: dict, result: dict) -> dict:
    refs = truth["utterances"]
    hyps = [e for e in result["events"] if e["speaker"] != "_sfx"]
    ref_spk = sorted({u["speaker"] for u in refs})
    hyp_spk = sorted({e["speaker"] for e in hyps})

    # 화자 대응: 시간 겹침이 가장 큰 1:1 매칭 (전수 탐색)
    def ov(a, b):
        return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    M = {(r, h): sum(ov(u, e) for u in refs if u["speaker"] == r for e in hyps if e["speaker"] == h)
         for r in ref_spk for h in hyp_spk}
    pad = hyp_spk + [None] * max(0, len(ref_spk) - len(hyp_spk))
    best_map, best_score = {}, -1.0
    for perm in itertools.permutations(pad, len(ref_spk)):
        score = sum(M.get((r, h), 0.0) for r, h in zip(ref_spk, perm))
        if score > best_score:
            best_map, best_score = dict(zip(ref_spk, perm)), score

    # 전체 CER
    ref_all = norm("".join(u["text"] for u in sorted(refs, key=lambda u: u["start"])))
    hyp_all = norm("".join(e["text"] for e in sorted(hyps, key=lambda e: e["start"])))
    cer = edit(ref_all, hyp_all) / max(1, len(ref_all))

    # cpCER
    ref_txt = {r: norm("".join(u["text"] for u in refs if u["speaker"] == r)) for r in ref_spk}
    hyp_txt = {h: norm("".join(e["text"] for e in sorted(hyps, key=lambda e: e["start"]) if e["speaker"] == h))
               for h in hyp_spk}
    cost = {(r, h): edit(ref_txt[r], hyp_txt[h]) for r in ref_spk for h in hyp_spk}
    best_cp = None
    for perm in itertools.permutations(hyp_spk + [None] * len(ref_spk), len(ref_spk)):
        used = set(p for p in perm if p)
        c = sum(cost[(r, h)] if h else len(ref_txt[r]) for r, h in zip(ref_spk, perm))
        c += sum(len(hyp_txt[h]) for h in hyp_spk if h not in used)
        best_cp = c if best_cp is None else min(best_cp, c)
    cpcer = best_cp / max(1, sum(len(t) for t in ref_txt.values()))

    # 발화 재현율: (1) 올바른 화자 자막 안에서 (2) 화자 상관없이 자막 어딘가에
    per = []
    for u in refs:
        h = best_map.get(u["speaker"])
        near = [e for e in hyps if e["end"] > u["start"] - 0.5 and e["start"] < u["end"] + 0.5]
        txt = " ".join(e["text"] for e in near if e["speaker"] == h) if h else ""
        per.append({"speaker": u["speaker"], "overlapped": bool(u.get("overlapped_by")), "kind": u.get("kind"),
                    "recall": round(recall(u["text"], txt), 3),
                    "recall_any": round(recall(u["text"], " ".join(e["text"] for e in near)), 3)})
    ovl = [p for p in per if p["overlapped"]]
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {
        "speakers_ref": len(ref_spk), "speakers_hyp": len(hyp_spk), "speaker_map": best_map,
        "CER": round(cer, 3), "cpCER": round(cpcer, 3),
        "utt_recall": mean([p["recall"] for p in per]),
        "overlap_utt_recall": mean([p["recall"] for p in ovl]),
        "overlap_utt_recall_any": mean([p["recall_any"] for p in ovl]),
        "missing_utts": sum(1 for p in per if p["recall"] < 0.3),
        "missing_overlap_utts": sum(1 for p in ovl if p["recall"] < 0.3),
        "n_utts": len(per), "n_overlap_utts": len(ovl),
        "per_utt": per,
    }


def baseline_from_asr(asr_json: dict) -> dict:
    """화자 정보 없는 일반 자막(유튜브 자동 자막과 같은 조건): 인식 단어를 한 화자로 이어 붙임."""
    words = sorted(asr_json["words"], key=lambda w: w["start"])
    events, cur = [], None
    for w in words:
        if cur and w["start"] - cur["end"] <= 0.8 and len(cur["text"]) < 32:
            cur["text"] += " " + w["text"]
            cur["end"] = w["end"]
        else:
            cur = {"speaker": "S1", "start": w["start"], "end": w["end"], "text": w["text"]}
            events.append(cur)
    return {"events": events}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", required=True)
    ap.add_argument("--result", action="append", default=[], help="result.json (여러 번 지정 가능)")
    ap.add_argument("--label", action="append")
    ap.add_argument("--baseline-asr", help="asr.json → 화자 없는 일반 자막 기준선으로 평가")
    ap.add_argument("--details", help="발화별 결과를 저장할 JSON 경로")
    a = ap.parse_args()
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))
    rows = []
    if a.baseline_asr:
        m = evaluate(truth, baseline_from_asr(json.loads(Path(a.baseline_asr).read_text(encoding="utf-8"))))
        m["label"] = "일반 자막(화자 없음)"
        rows.append(m)
    for i, rp in enumerate(a.result):
        res = json.loads(Path(rp).read_text(encoding="utf-8"))
        m = evaluate(truth, res)
        m["label"] = (a.label or [])[i] if a.label and i < len(a.label) else Path(rp).parent.name
        rows.append(m)
    keys = ["label", "speakers_ref", "speakers_hyp", "CER", "cpCER", "utt_recall", "overlap_utt_recall",
            "overlap_utt_recall_any", "missing_utts", "missing_overlap_utts", "n_utts", "n_overlap_utts"]
    print(json.dumps([{k: r[k] for k in keys} for r in rows], ensure_ascii=False, indent=1))
    if a.details:
        Path(a.details).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
