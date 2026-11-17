"""정답과 결과 자막을 시간 순으로 나란히 출력 (디버깅용).

  python tools/inspect_job.py <job_dir> <truth.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluate as ev  # noqa: E402


def main() -> None:
    job, truth_path = Path(sys.argv[1]), Path(sys.argv[2])
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    res = json.loads((job / "result.json").read_text(encoding="utf-8"))
    m = ev.evaluate(truth, res)
    inv = {v: k for k, v in m["speaker_map"].items() if v}
    rows = []
    for u in truth["utterances"]:
        rows.append((u["start"], f"정답 {u['speaker']} {u['start']:6.2f}-{u['end']:6.2f} {u['kind']:11s} "
                                 f"겹침={','.join(u['overlapped_by']) or '-'} | {u['text']}"))
    for e in res["events"]:
        tag = "복원" if e.get("recovered") else ("동시" if e.get("overlap") else "자막")
        rows.append((e["start"] + 0.001, f"  {tag} {inv.get(e['speaker'], e['speaker'])} "
                                         f"{e['start']:6.2f}-{e['end']:6.2f} | {e['text']}"))
    for _, line in sorted(rows):
        print(line)
    print("\n발화별 재현율:", [(p["speaker"], p["kind"], p["recall"]) for p in m["per_utt"]])


if __name__ == "__main__":
    main()
