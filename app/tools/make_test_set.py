"""정답이 있는 '겹친 대화' 테스트 영상 만들기.

Zeroth-Korean(CC BY 4.0, 화자 ID 포함) 테스트 세트의 발화를 화자 3~4명의 대화처럼 이어 붙이되,
일부러 말이 겹치게(끼어들기·맞장구) 배치합니다. 누가 언제 무엇을 말했는지 정답(truth.json)이
있으므로 화자 구분·겹친 말 복원 성능을 숫자로 잴 수 있습니다.

  python tools/make_test_set.py --parquet zeroth_test.parquet --out testset --speakers 3 --seed 7
"""
from __future__ import annotations

import argparse
import io
import json
import random
import subprocess
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

SR = 16000
LABELS = "ABCDEF"
COLORS = ["0xFFD84D", "0x5FD3FF", "0x7CF29A", "0xFF9F5A", "0xFF8FD8", "0xB8A6FF"]
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def load_utts(parquet: Path) -> dict[int, list[dict]]:
    tbl = pq.read_table(parquet, columns=["speaker_id", "audio", "text"]).to_pylist()
    by: dict[int, list[dict]] = {}
    for row in tbl:
        wav, sr = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != SR:
            continue
        # 앞뒤 무음 다듬기
        idx = np.where(np.abs(wav) > 0.01)[0]
        if len(idx):
            wav = wav[max(0, idx[0] - 800): idx[-1] + 800]
        by.setdefault(int(row["speaker_id"]), []).append({"wav": wav, "text": row["text"].strip(),
                                                          "dur": len(wav) / SR})
    return by


def rms_norm(x: np.ndarray, db: float) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    return x * (10 ** (db / 20) / rms)


def build(by: dict[int, list[dict]], n_spk: int, seed: int, turns: int, interjections: int):
    rng = random.Random(seed)
    spk_ids = rng.sample(sorted(k for k, v in by.items() if len(v) >= turns // n_spk + 3), n_spk)
    pools = {LABELS[i]: [u for u in by[s] if u["dur"] <= 8.0] for i, s in enumerate(spk_ids)}
    for p in pools.values():
        rng.shuffle(p)
    utts, t, prev = [], 0.8, None
    order = []
    for _ in range(turns):
        choices = [l for l in pools if l != prev]
        prev = rng.choice(choices)
        order.append(prev)
    def free(lab: str, a: float, b: float, margin: float = 0.3) -> bool:
        """같은 화자는 자기 말과 겹칠 수 없음."""
        return all(x["end"] + margin <= a or b + margin <= x["start"] for x in utts if x["speaker"] == lab)

    for lab in order:
        u = pools[lab].pop()
        same_end = max((x["end"] for x in utts if x["speaker"] == lab), default=0.0)
        if utts and rng.random() < 0.45:      # 앞사람 말 끝나기 전에 끼어들기
            start = max(utts[-1]["start"] + 0.8, utts[-1]["end"] - rng.uniform(0.8, 2.2), same_end + 0.3)
            kind = "interrupt" if start < utts[-1]["end"] else "turn"
        else:
            start = max((utts[-1]["end"] if utts else t) + rng.uniform(0.15, 0.7), same_end + 0.3)
            kind = "turn"
        utts.append({"speaker": lab, "start": start, "end": start + u["dur"], "text": u["text"],
                     "wav": u["wav"], "kind": kind})
    # 맞장구/짧은 반응: 긴 발화 한가운데에 다른 화자의 짧은 발화를 통째로 겹치기
    longs = sorted(utts, key=lambda x: x["end"] - x["start"], reverse=True)
    for host in longs[:interjections]:
        mid = (host["start"] + host["end"]) / 2
        others = [l for l in pools if l != host["speaker"] and pools[l]]
        rng.shuffle(others)
        for lab in others:
            short = min(pools[lab], key=lambda u: u["dur"])
            start = mid - short["dur"] / 2
            if short["dur"] > (host["end"] - host["start"]) - 0.6 or not free(lab, start, start + short["dur"]):
                continue
            pools[lab] = [u for u in pools[lab] if u is not short]  # dict 안에 배열이 있어 remove() 대신 동일성 비교
            utts.append({"speaker": lab, "start": start, "end": start + short["dur"], "text": short["text"],
                         "wav": short["wav"], "kind": "backchannel"})
            break
    utts.sort(key=lambda x: x["start"])
    total = max(u["end"] for u in utts) + 1.0
    mix = np.zeros(int(total * SR), dtype=np.float32)
    for u in utts:
        x = rms_norm(u["wav"], rng.uniform(-24, -21))
        a = int(u["start"] * SR)
        mix[a: a + len(x)] += x[: len(mix) - a]
    mix += np.random.default_rng(seed).normal(0, 10 ** (-48 / 20), len(mix)).astype(np.float32)
    mix *= 0.9 / (np.max(np.abs(mix)) + 1e-9)
    # 겹침 정보
    for u in utts:
        u["overlapped_by"] = sorted({v["speaker"] for v in utts if v["speaker"] != u["speaker"] and
                                     min(u["end"], v["end"]) - max(u["start"], v["start"]) >= 0.3})
    return mix, utts, {LABELS[i]: s for i, s in enumerate(spk_ids)}


def render_video(wav_path: Path, utts: list[dict], labels: list[str], out: Path) -> None:
    n = len(labels)
    w = 1280 // n
    filters = []
    for i, lab in enumerate(labels):
        x = i * w + w // 2 - 110
        filters.append(f"drawbox=x={x}:y=250:w=220:h=220:color=0x2B313C@1:t=fill")
        for u in (u for u in utts if u["speaker"] == lab):
            filters.append(f"drawbox=x={x}:y=250:w=220:h=220:color={COLORS[i]}@1:t=fill:"
                           f"enable='between(t,{u['start']:.2f},{u['end']:.2f})'")
        filters.append(f"drawtext=fontfile={FONT}:text='{lab}':x={x + 110}-text_w/2:y=330:fontsize=72:fontcolor=0x0F1115")
    filters.append(f"drawtext=fontfile={FONT}:text='VoxPrism 테스트 대화':x=40:y=40:fontsize=36:fontcolor=white")
    vf = ",".join(filters)
    dur = max(u["end"] for u in utts) + 1.0
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x0F1115:s=1280x720:r=15:d={dur:.2f}",
                    "-i", str(wav_path), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--speakers", type=int, default=3)
    ap.add_argument("--turns", type=int, default=12)
    ap.add_argument("--interjections", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by = load_utts(Path(a.parquet))
    mix, utts, spk_map = build(by, a.speakers, a.seed, a.turns, a.interjections)
    name = f"test_{a.speakers}spk_seed{a.seed}"
    wav_path = out / f"{name}.wav"
    sf.write(wav_path, mix, SR)
    render_video(wav_path, utts, sorted(spk_map), out / f"{name}.mp4")
    truth = {"source": "kresnik/zeroth_korean test split (CC BY 4.0)", "speaker_ids": spk_map,
             "utterances": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in u.items() if k != "wav"}
                            for u in utts]}
    (out / f"{name}.truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    ov = sum(1 for u in utts if u["overlapped_by"])
    print(f"{name}: {len(utts)}개 발화, 겹친 발화 {ov}개, 길이 {len(mix) / SR:.1f}초 → {out}")


if __name__ == "__main__":
    main()
