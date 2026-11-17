"""여러 실행 결과(runs.json)를 한 번에 평가해 표로 출력.

runs.json: [{"test": "test_3spk_seed7", "n": 3, "rec": true, "id": "<job id>"}, ...]
  python tools/eval_runs.py /srv/whosaid/testset/runs_v2.json --out /srv/whosaid/testset/eval_v2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluate as ev  # noqa: E402

JOBS = Path("/srv/whosaid/data/jobs")
TESTS = Path("/srv/whosaid/testset")
KEYS = ["cpCER", "utt_recall", "overlap_utt_recall", "overlap_utt_recall_any", "missing_overlap_utts", "n_overlap_utts",
        "speakers_hyp", "speakers_ref"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--out")
    a = ap.parse_args()
    runs = json.loads(Path(a.runs).read_text())
    rows = []
    baseline_done = set()
    for r in runs:
        truth = json.loads((TESTS / f"{r['test']}.truth.json").read_text(encoding="utf-8"))
        jd = JOBS / r["id"]
        if not jd.exists():  # 평가가 끝난 작업은 testset/jobs_archive 로 옮겨 둠
            jd = TESTS / "jobs_archive" / r["id"]
        res = json.loads((jd / "result.json").read_text(encoding="utf-8"))
        st = json.loads((jd / "status.json").read_text(encoding="utf-8"))
        cond = ("출연자 수 입력" if r["n"] else "자동") + " · " + ("화자구분+복원" if r["rec"] else "화자구분만")
        m = ev.evaluate(truth, res)
        rows.append({"test": r["test"], "cond": cond, "sec": st.get("timings", {}).get("total"),
                     **{k: m[k] for k in KEYS}})
        if r["test"] not in baseline_done:
            b = ev.evaluate(truth, ev.baseline_from_asr(json.loads((jd / "asr.json").read_text(encoding="utf-8"))))
            rows.append({"test": r["test"], "cond": "일반 자막(화자 없음)", "sec": None, **{k: b[k] for k in KEYS}})
            baseline_done.add(r["test"])
    agg = defaultdict(list)
    for x in rows:
        agg[x["cond"]].append(x)
    order = ["일반 자막(화자 없음)", "자동 · 화자구분만", "자동 · 화자구분+복원",
             "출연자 수 입력 · 화자구분만", "출연자 수 입력 · 화자구분+복원"]
    summary = []
    for c in order:
        xs = agg.get(c, [])
        if not xs:
            continue
        mean = lambda k: round(sum(x[k] for x in xs) / len(xs), 3)  # noqa: E731
        summary.append({"cond": c, "n_tests": len(xs), "cpCER": mean("cpCER"), "utt_recall": mean("utt_recall"),
                        "overlap_utt_recall": mean("overlap_utt_recall"),
                        "overlap_utt_recall_any": mean("overlap_utt_recall_any"),
                        "missing_overlap": sum(x["missing_overlap_utts"] for x in xs),
                        "overlap_total": sum(x["n_overlap_utts"] for x in xs),
                        "speaker_count_ok": sum(1 for x in xs if x["speakers_hyp"] == x["speakers_ref"])})
    for x in sorted(rows, key=lambda x: (x["test"], order.index(x["cond"]))):
        print(f"{x['test']:18s} {x['cond']:22s} cpCER={x['cpCER']:.3f} 발화={x['utt_recall']:.3f} "
              f"겹침={x['overlap_utt_recall']:.3f} 겹침(화자무관)={x['overlap_utt_recall_any']:.3f} "
              f"누락={x['missing_overlap_utts']}/{x['n_overlap_utts']} 화자={x['speakers_hyp']}/{x['speakers_ref']} "
              f"{'' if x['sec'] is None else str(x['sec']) + 's'}")
    print()
    for s in summary:
        print(json.dumps(s, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=1),
                               encoding="utf-8")


if __name__ == "__main__":
    main()
