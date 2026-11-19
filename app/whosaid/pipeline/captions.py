"""자막 이벤트 생성과 SRT / WebVTT / ASS 내보내기.

기준(넷플릭스 한국어 자막 가이드 등 일반 관행):
  - 한 줄 최대 16자, 최대 2줄
  - 읽기 속도 초당 약 12자, 최소 표시 0.8초
  - 화자가 다르면 다른 자막 이벤트 → 동시에 말하면 두 줄이 함께 표시됨
"""
from __future__ import annotations

from typing import Iterable

LINE_MAX = 16
EVENT_MAX = 32
MAX_DUR = 6.0
MAX_GAP = 0.8
MIN_SHOW = 0.8
CPS = 12.0
TURN_PAUSE = 0.3
SENT_END = tuple(".?!…~")

# 어두운 배경 위에서 잘 보이고 서로 구분되는 밝은 색 (S1부터 차례로)
PALETTE = ["#FFD84D", "#5FD3FF", "#7CF29A", "#FF9F5A", "#FF8FD8", "#B8A6FF",
           "#9FE8E0", "#F2B5A0", "#C8F07A", "#FFFFFF"]
SFX_ID = "_sfx"


def build_events(words: list[dict]) -> list[dict]:
    words = sorted((w for w in words if (w.get("text") or "").strip()), key=lambda w: (w["start"], w["end"]))
    events: list[dict] = []
    open_ev: dict[str, dict] = {}

    def close(spk: str) -> None:
        ev = open_ev.pop(spk, None)
        if ev:
            events.append(ev)

    for w in words:
        spk = w.get("speaker") or "UNK"
        # 다른 화자가 0.3초 이상 쉬고 있으면(턴 교대) 그 화자의 자막을 닫는다.
        # 두 사람이 동시에 말하는 중(단어가 엇갈려 들어옴)에는 서로의 자막을 쪼개지 않는다.
        for other in list(open_ev):
            if other != spk and open_ev[other]["end"] <= w["start"] - TURN_PAUSE:
                close(other)
        ev = open_ev.get(spk)
        rec = bool(w.get("recovered"))
        if ev is not None:
            too_long = len(ev["text"]) + 1 + len(w["text"]) > EVENT_MAX
            if (w["start"] - ev["end"] > MAX_GAP or too_long or w["end"] - ev["start"] > MAX_DUR
                    or (ev["text"].endswith(SENT_END) and len(ev["text"]) >= 8) or ev["recovered"] != rec):
                close(spk)
                ev = None
        if ev is None:
            open_ev[spk] = {"speaker": spk, "start": w["start"], "end": w["end"], "text": w["text"].strip(),
                            "recovered": rec, "uncertain": bool(w.get("uncertain"))}
        else:
            ev["text"] += " " + w["text"].strip()
            ev["end"] = max(ev["end"], w["end"])
            ev["uncertain"] = ev["uncertain"] or bool(w.get("uncertain"))
    for spk in list(open_ev):
        close(spk)
    events.sort(key=lambda e: (e["start"], e["end"]))
    _polish_timing(events)
    mark_overlaps(events)
    for i, e in enumerate(events):
        e["id"] = i
        e["start"], e["end"] = round(e["start"], 3), round(e["end"], 3)
    return events


def _polish_timing(events: list[dict]) -> None:
    by_spk: dict[str, list[dict]] = {}
    for e in events:
        by_spk.setdefault(e["speaker"], []).append(e)
    for lst in by_spk.values():
        lst.sort(key=lambda e: e["start"])
        for i, e in enumerate(lst):
            nxt = lst[i + 1]["start"] - 0.05 if i + 1 < len(lst) else float("inf")
            want = max(e["start"] + MIN_SHOW, e["start"] + len(e["text"]) / CPS, e["end"] + 0.3)
            want = min(want, e["end"] + 1.5)
            e["end"] = max(e["end"], min(want, nxt))


def mark_overlaps(events: list[dict], min_ov: float = 0.15) -> None:
    for e in events:
        e["overlap"] = False
    for i, a in enumerate(events):
        if a["speaker"] == SFX_ID:
            continue
        for b in events[i + 1:]:
            if b["start"] >= a["end"]:
                break
            if b["speaker"] in (a["speaker"], SFX_ID):
                continue
            if min(a["end"], b["end"]) - max(a["start"], b["start"]) >= min_ov:
                a["overlap"] = b["overlap"] = True


def sound_events(raw: list[dict], min_dur: float = 0.8, merge_gap: float = 1.0) -> list[dict]:
    raw = sorted(raw, key=lambda e: e["start"])
    merged: list[dict] = []
    for e in raw:
        if merged and merged[-1]["label"] == e["label"] and e["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"] = max(merged[-1]["end"], e["end"])
        else:
            merged.append(dict(e))
    out = []
    for e in merged:
        if e["end"] - e["start"] < min_dur:
            continue
        text = f"♪ {e['label']} ♪" if e["label"] in ("음악", "노래") else f"[{e['label']}]"
        out.append({"speaker": SFX_ID, "start": round(e["start"], 3), "end": round(e["end"], 3), "text": text,
                    "recovered": False, "uncertain": False, "overlap": False})
    return out


def wrap(text: str, line_max: int = LINE_MAX) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= line_max:
        return [text]
    mid = len(text) / 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return [text[: len(text) // 2], text[len(text) // 2:]]
    cut = min(spaces, key=lambda i: abs(i - mid))
    return [text[:cut].strip(), text[cut + 1:].strip()]


# ───────────────────── 화자 표시 정보(이름·색·병합) ─────────────────────

def resolve_speakers(speakers: list[dict], edits: dict | None) -> dict[str, dict]:
    """speakers(result.json) + edits(speakers.json) → {원래 id: {id, name, color}} (병합 반영)."""
    edits = edits or {}
    base = {s["id"]: dict(s) for s in speakers}
    for sid, ed in edits.items():
        if sid in base:
            if ed.get("name"):
                base[sid]["name"] = ed["name"].strip()[:30]
            base[sid]["merge_into"] = ed.get("merge_into") or None

    def final(sid: str, depth: int = 0) -> str:
        tgt = base.get(sid, {}).get("merge_into")
        if tgt and tgt in base and tgt != sid and depth < 10:
            return final(tgt, depth + 1)
        return sid

    out = {}
    for sid in base:
        f = final(sid)
        out[sid] = {"id": f, "name": base[f]["name"], "color": base[f]["color"]}
    out[SFX_ID] = {"id": SFX_ID, "name": "소리", "color": "#DDDDDD"}
    out.setdefault("UNK", {"id": "UNK", "name": "?", "color": "#FFFFFF"})
    return out


def _ts_srt(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_vtt(t: float) -> str:
    return _ts_srt(t).replace(",", ".")


def _ts_ass(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _label(ev: dict, who: dict) -> str:
    if ev["speaker"] == SFX_ID:
        return ""
    return f"[{who['name']}] "


def to_srt(events: Iterable[dict], spk: dict[str, dict]) -> str:
    lines = []
    for n, ev in enumerate(events, 1):
        who = spk.get(ev["speaker"], spk["UNK"])
        body = "\n".join(wrap(_label(ev, who) + ev["text"], LINE_MAX + 6))
        lines.append(f"{n}\n{_ts_srt(ev['start'])} --> {_ts_srt(ev['end'])}\n{body}\n")
    return "\n".join(lines)


def to_vtt(events: Iterable[dict], spk: dict[str, dict]) -> str:
    events = list(events)
    css = ["WEBVTT", "", "STYLE",
           "::cue { background: rgba(0,0,0,0.75); font-family: 'Noto Sans KR', sans-serif; }"]
    seen = set()
    for who in spk.values():
        cls = who["id"].replace("_", "")
        if cls not in seen:
            seen.add(cls)
            css.append(f"::cue(.{cls}) {{ color: {who['color']}; }}")
    out = ["\n".join(css), ""]
    for n, ev in enumerate(events, 1):
        who = spk.get(ev["speaker"], spk["UNK"])
        cls = who["id"].replace("_", "")
        text = _label(ev, who) + ev["text"]
        body = "\n".join(f"<c.{cls}>{_vtt_escape(line)}</c>" for line in wrap(text, LINE_MAX + 6))
        out.append(f"{n}\n{_ts_vtt(ev['start'])} --> {_ts_vtt(ev['end'])}\n<v {_vtt_escape(who['name'])}>{body}\n")
    return "\n".join(out)


def _vtt_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ass_escape(s: str) -> str:
    return s.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


def to_ass(events: Iterable[dict], spk: dict[str, dict], width: int = 1280, height: int = 720,
           font: str = "Noto Sans CJK KR") -> str:
    width, height = width or 1280, height or 720
    fs = max(18, round(height * 0.052))
    margin_v = round(height * 0.05)
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    box = "&H50000000"  # BorderStyle 3: 반투명 검은 상자(가독성)
    styles_done = set()
    for who in spk.values():
        if who["id"] in styles_done:
            continue
        styles_done.add(who["id"])
        if who["id"] == SFX_ID:
            head.append(f"Style: SFX,{font},{round(fs * 0.85)},{_ass_color('#DDDDDD')},&H000000FF,{box},&H00000000,"
                        f"0,1,0,0,100,100,0,0,3,{max(2, fs // 6)},0,8,40,40,{margin_v},1")
        else:
            head.append(f"Style: {who['id']},{font},{fs},{_ass_color(who['color'])},&H000000FF,{box},&H00000000,"
                        f"1,0,0,0,100,100,0,0,3,{max(2, fs // 6)},0,2,40,40,{margin_v},1")
    head += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    rows = []
    for ev in events:
        who = spk.get(ev["speaker"], spk["UNK"])
        style = "SFX" if who["id"] == SFX_ID else who["id"]
        if style not in styles_done and style != "SFX":
            style = next(iter(styles_done))
        lines = wrap(_label(ev, who) + ev["text"], LINE_MAX + 6)
        text = r"\N".join(_ass_escape(x) for x in lines)
        rows.append(f"Dialogue: 0,{_ts_ass(ev['start'])},{_ts_ass(ev['end'])},{style},{_ass_escape(who['name'])},"
                    f"0,0,0,,{text}")
    return "\n".join(head + rows) + "\n"


# ───────────────────── 자막 입힌 MP4용 ASS (SPEC-008) ─────────────────────
# 웹 플레이어와 같은 모양: 위쪽 고정 줄(lane)에 말풍선, 말하는 사람 윤곽(SPEC-009).
# 내려받는 ASS(to_ass)는 편집하기 쉽게 그대로 둔다.

_FONT_FILES = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")


def assign_lanes(events: Iterable[dict]) -> tuple[dict[int, int], int]:
    """시작 순서대로 비어 있는 가장 위(첫) 줄에 넣는다. 끝날 때까지 줄을 바꾸지 않는다(웹 job.js와 같은 규칙)."""
    ends: list[float] = []
    lane: dict[int, int] = {}
    dialog = sorted((e for e in events if e["speaker"] != SFX_ID), key=lambda e: (e["start"], e.get("id", 0)))
    for e in dialog:
        i = next((k for k, t in enumerate(ends) if t <= e["start"] + 1e-6), None)
        if i is None:
            i = len(ends)
            ends.append(0.0)
        ends[i] = e["end"]
        lane[e.get("id", id(e))] = i
    return lane, max(1, len(ends))


class _Measure:
    """글자 폭 재기. 폰트가 없으면 한글 1em·그 밖 0.55em으로 어림한다."""

    def __init__(self) -> None:
        self.fonts: dict[int, object] = {}
        self.path = None
        try:
            import os

            from PIL import ImageFont  # noqa: F401
            self.path = next((p for p in _FONT_FILES if os.path.exists(p)), None)
        except ImportError:
            self.path = None

    def __call__(self, text: str, size: int) -> float:
        # libass의 글자 크기는 em이 아니라 (ascent+descent) 높이 기준이라, 같은 비율로 줄여서 잰다.
        if self.path:
            try:
                from PIL import ImageFont
                if size not in self.fonts:
                    f = ImageFont.truetype(self.path, 100, index=1)  # ttc 1번 = KR
                    asc, desc = f.getmetrics()
                    self.fonts[size] = (ImageFont.truetype(self.path, size, index=1), 100 / (asc + desc))
                font, k = self.fonts[size]
                return float(font.getlength(text)) * k
            except Exception:  # noqa: BLE001
                self.path = None
        return sum(size / 1.45 * (1.0 if ord(ch) > 0x2E80 else 0.3 if ch == " " else 0.58) for ch in text)


def _rrect(x: float, y: float, w: float, h: float, r: float) -> str:
    """둥근 사각형 ASS 그리기 명령(왼쪽 위 x,y)."""
    r = min(r, w / 2, h / 2)
    k = r * 0.45
    x2, y2 = x + w, y + h

    def f(v: float) -> str:
        return f"{v:.1f}"

    return (f"m {f(x + r)} {f(y)} l {f(x2 - r)} {f(y)} b {f(x2 - k)} {f(y)} {f(x2)} {f(y + k)} {f(x2)} {f(y + r)} "
            f"l {f(x2)} {f(y2 - r)} b {f(x2)} {f(y2 - k)} {f(x2 - k)} {f(y2)} {f(x2 - r)} {f(y2)} "
            f"l {f(x + r)} {f(y2)} b {f(x + k)} {f(y2)} {f(x)} {f(y2 - k)} {f(x)} {f(y2 - r)} "
            f"l {f(x)} {f(y + r)} b {f(x)} {f(y + k)} {f(x + k)} {f(y)} {f(x + r)} {f(y)}")


def _fit_lines(text: str, size: int, avail: float, measure) -> list[str]:
    """글자 폭을 재서 avail 안에 들어가도록 단어 단위로 고르게 나눈다(최대 3줄)."""
    total = measure(text, size)
    k = 1
    while k < 3 and total / k > avail:
        k += 1
    if k == 1:
        return [text]
    words, lines, cur = text.split(" "), [], ""
    target = total / k
    for wd in words:
        cand = f"{cur} {wd}" if cur else wd
        if cur and measure(cand, size) > target * 1.08 and len(lines) < k - 1:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    lines.append(cur)
    return lines


def to_ass_burn(events: Iterable[dict], spk: dict[str, dict], width: int = 1280, height: int = 720,
                visual: dict | None = None, font: str = "Noto Sans CJK KR") -> str:
    """자막 입힌 MP4용 ASS (SPEC-009): 위쪽 고정 줄 말풍선(테두리 = 화자 색), '화면 밖' 표시,
    그리고 visual.json 의 말하는 사람 윤곽(같은 색 테두리 + 옅은 채움)."""
    events = list(events)
    w, h = width or 1280, height or 720
    measure = _Measure()
    fs = max(16, round(min(w, h) * 0.046))  # 세로 영상에서도 폭에 맞게
    pad, bw = max(4, round(fs * 0.28)), max(2, round(fs * 0.1))
    dark = _ass_color("#0A0C10")

    def label(e: dict) -> str:
        who = spk.get(e["speaker"], spk["UNK"])
        off = " [화면 밖]" if e.get("offscreen") else ""
        return f"{who['name']}{'?' if e.get('uncertain') else ''}{off}  {e['text']}"

    avail = w * 0.92 - 2 * (pad + bw)
    dialog = [e for e in events if e["speaker"] != SFX_ID]
    split = {e.get("id", id(e)): _fit_lines(label(e), fs, avail, measure) for e in dialog}
    nlines = max([len(v) for v in split.values()] + [1])
    line_h = fs * 1.02  # libass 한 줄 높이 ≈ 글자 크기
    lane_h = nlines * line_h + 2 * (pad + bw)
    gap = fs * 0.45
    top0 = round(h * 0.035)
    lane, _ = assign_lanes(events)

    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
         "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
         "Alignment, MarginL, MarginR, MarginV, Encoding"),
        f"Style: Bubble,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,8,0,0,0,1",
        f"Style: Shape,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        (f"Style: SFX,{font},{round(fs * 0.85)},{_ass_color('#DDDDDD')},&H000000FF,&H50000000,&H00000000,"
         f"0,1,0,0,100,100,0,0,3,{max(2, fs // 6)},0,2,40,40,{round(h * 0.06)},1"),
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    rows: list[str] = []

    def add(layer: int, s: float, e: float, style: str, text: str) -> None:
        rows.append(f"Dialogue: {layer},{_ts_ass(s)},{_ts_ass(e)},{style},,0,0,0,,{text}")

    # 말하는 사람 윤곽: visual.json 프레임마다 0.2초짜리 도형
    if visual and visual.get("frames"):
        step = 1.0 / float(visual.get("fps") or 5)
        lw = max(2.0, w * 0.004)
        for f in visual["frames"]:
            s0, s1 = max(0.0, f["t"] - step / 2), f["t"] + step / 2
            for hl in f["hl"]:
                who = spk.get(hl["spk"], spk["UNK"])
                col = _ass_color(who["color"])
                pts = [(x * w, y * h) for x, y in hl["poly"]]
                if len(pts) < 3:
                    continue
                path = "m " + f"{pts[0][0]:.0f} {pts[0][1]:.0f} l " + " ".join(f"{x:.0f} {y:.0f}" for x, y in pts[1:])
                add(0, s0, s1, "Shape", f"{{\\pos(0,0)\\p1\\1c{col}\\1a&HD8&\\3c{col}\\bord{lw:.1f}\\blur{lw:.1f}}}{path}")
                add(1, s0, s1, "Shape", f"{{\\pos(0,0)\\p1\\1a&HFF&\\3c{col}\\bord{lw / 2:.1f}}}{path}")

    for e in dialog:
        who = spk.get(e["speaker"], spk["UNK"])
        col = _ass_color(who["color"])
        k = lane.get(e.get("id", id(e)), 0)
        box_top = top0 + k * (lane_h + gap)
        lines = split[e.get("id", id(e))]
        tw = min(max(measure(x, fs) for x in lines), avail)
        bub_w = tw + 2 * pad + fs * 0.4
        box_h = len(lines) * line_h + 2 * pad
        cx = w / 2
        body = r"\N".join(_ass_escape(x) for x in lines)
        dash = "\\3a&H40&" if e.get("offscreen") else ""
        add(2, e["start"], e["end"], "Shape", f"{{\\pos(0,0)\\p1\\1c{dark}\\1a&H18&\\3c{col}{dash}\\bord{bw}}}"
            f"{_rrect(cx - bub_w / 2, box_top, bub_w, box_h, fs * 0.45)}")
        add(3, e["start"], e["end"], "Bubble", f"{{\\an8\\pos({cx:.1f},{box_top + pad:.1f})\\1c{col}}}{body}")

    for e in events:
        if e["speaker"] == SFX_ID:
            add(9, e["start"], e["end"], "SFX", _ass_escape(e["text"]))
    return "\n".join(head + rows) + "\n"
