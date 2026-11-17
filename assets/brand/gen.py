#!/usr/bin/env python3
"""VoxPrism 브랜드 에셋 생성기.

글자는 모두 path로 바꿔 넣어서(SVG에 폰트 의존 없음) 어디서 열어도 똑같이 보이게 합니다.
PNG는 rsvg-convert로 만듭니다.

    python3 gen.py            # out/ 에 SVG·PNG 생성
"""
from __future__ import annotations

import math
import pathlib
import subprocess

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = pathlib.Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

INTER_BOLD = ("/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf", 0)
INTER_MED = ("/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf", 0)
NOTO_KR_MED = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1)
NOTO_KR_BOLD = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1)

# 화자 색 (앱의 captions.PALETTE 앞 3색과 같음)
SPK = ["#FFD84D", "#5FD3FF", "#7CF29A"]
SPK_LIGHT = ["#E3A600", "#1F96D6", "#22A95E"]   # 흰 배경용으로 진하게
INK_DARK_BG = "#EEF1F8"
INK_LIGHT_BG = "#151B34"
NAVY = "#0B1020"
NAVY2 = "#16203F"

_fonts: dict = {}


def _font(spec):
    if spec not in _fonts:
        path, idx = spec
        face = hb.Face(hb.Blob.from_file_path(path), idx)
        tt = TTFont(path, fontNumber=idx) if path.endswith(".ttc") else TTFont(path)
        _fonts[spec] = (face, hb.Font(face), tt, tt.getGlyphSet(), tt.getGlyphOrder())
    return _fonts[spec]


def shape(text: str, spec, size: float, letter_spacing: float = 0.0):
    """글자별 (glyph name, x, y_offset) 목록과 전체 폭(px)."""
    face, font, tt, gs, order = _font(spec)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    scale = size / face.upem
    out, cx = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((order[info.codepoint], cx + pos.x_offset * scale, pos.y_offset * scale))
        cx += pos.x_advance * scale + letter_spacing
    return out, cx - letter_spacing


def text_path(text: str, spec, size: float, x: float, y: float, letter_spacing: float = 0.0,
              start: int = 0, end: int | None = None) -> str:
    """기준선 (x, y)에 놓인 글자의 SVG path d. start/end로 글자 일부만 뽑을 수 있음."""
    face, font, tt, gs, order = _font(spec)
    glyphs, _ = shape(text, spec, size, letter_spacing)
    scale = size / face.upem
    pen = SVGPathPen(gs)
    for name, gx, gy in glyphs[start:end]:
        gs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + gx, y - gy)))
    return pen.getCommands()


def text_width(text: str, spec, size: float, letter_spacing: float = 0.0) -> float:
    return shape(text, spec, size, letter_spacing)[1]


def rounded_poly(pts, r: float) -> str:
    d = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        a = (p1[0] + v1[0] / l1 * r, p1[1] + v1[1] / l1 * r)
        b = (p1[0] + v2[0] / l2 * r, p1[1] + v2[1] / l2 * r)
        d.append(f"{'M' if i == 0 else 'L'}{a[0]:.1f} {a[1]:.1f}")
        d.append(f"Q{p1[0]:.1f} {p1[1]:.1f} {b[0]:.1f} {b[1]:.1f}")
    return " ".join(d) + " Z"


def wave(x0: float, x1: float, y: float, amp: float, cycles: float, phase: float = 0.0,
         taper: float = 0.35, n: int = 90) -> str:
    pts = []
    for i in range(n + 1):
        t = i / n
        a = amp * (1 - taper * t) * math.sin(math.pi * t) ** 0.35  # 양 끝을 0으로 모음
        pts.append((x0 + (x1 - x0) * t, y - a * math.sin(2 * math.pi * cycles * t + phase)))
    return "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)


# ── 마크(512 상자 기준) ────────────────────────────────────────────
T, BL, BR = (240.0, 136.0), (108.0, 376.0), (372.0, 376.0)
SLOPE = (BR[0] - T[0]) / (BR[1] - T[1])  # 오른쪽 면: x = T.x + (y - T.y) * SLOPE
ENTRY = (T[0] - (290 - T[1]) * SLOPE, 290.0)
BARS_Y = [214.0, 278.0, 342.0]
BARS_END = [448.0, 476.0, 438.0]


def mark_group(theme: str = "dark", simple: bool = False, uid: str = "m") -> tuple[str, str]:
    """(defs, body) — 512x512 좌표계."""
    ink = INK_DARK_BG if theme == "dark" else INK_LIGHT_BG
    cols = SPK if theme == "dark" else SPK_LIGHT
    defs = (f'<linearGradient id="{uid}-glass" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{ink}" stop-opacity="{0.16 if theme == "dark" else 0.10}"/>'
            f'<stop offset="1" stop-color="{ink}" stop-opacity="0.02"/></linearGradient>')
    body = []
    prism = rounded_poly([T, BR, BL], 20)
    sw = 16 if not simple else 30
    if not simple:
        # 섞여 들어오는 두 목소리
        body.append(f'<path d="{wave(26, ENTRY[0] - 4, ENTRY[1], 34, 2.0, 0.0)}" fill="none" stroke="{ink}" '
                    f'stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>')
        body.append(f'<path d="{wave(26, ENTRY[0] - 4, ENTRY[1], 24, 3.1, 1.9)}" fill="none" stroke="{ink}" '
                    f'stroke-opacity="0.45" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>')
    body.append(f'<path d="{prism}" fill="url(#{uid}-glass)"/>')
    for y, c in zip(BARS_Y, cols):
        ex = T[0] + (y - T[1]) * SLOPE
        if not simple:
            body.append(f'<path d="M{ENTRY[0]:.1f} {ENTRY[1]:.1f} L{ex:.1f} {y:.1f}" stroke="{c}" '
                        f'stroke-width="7" stroke-linecap="round" stroke-opacity="0.95"/>')
    body.append(f'<path d="{prism}" fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>')
    bw = 30 if not simple else 44
    for y, c, end in zip(BARS_Y, cols, BARS_END):
        ex = T[0] + (y - T[1]) * SLOPE + (20 if not simple else 30)
        body.append(f'<path d="M{ex:.1f} {y:.1f} L{end:.1f} {y:.1f}" stroke="{c}" stroke-width="{bw}" '
                    f'stroke-linecap="round"/>')
    return defs, "\n".join(body)


def bg_rect(w: float, h: float, r: float, uid: str = "bg") -> tuple[str, str]:
    defs = (f'<radialGradient id="{uid}" cx="0.25" cy="0.15" r="1.1">'
            f'<stop offset="0" stop-color="{NAVY2}"/><stop offset="0.6" stop-color="{NAVY}"/>'
            f'<stop offset="1" stop-color="#070A14"/></radialGradient>')
    return defs, f'<rect width="{w}" height="{h}" rx="{r}" fill="url(#{uid})"/>'


def svg(w: float, h: float, defs: str, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'role="img" aria-label="{title}">\n<title>{title}</title>\n<defs>{defs}</defs>\n{body}\n</svg>\n')


def save(name: str, content: str, png: list[tuple[str, int]] | None = None) -> None:
    p = OUT / name
    p.write_text(content, encoding="utf-8")
    for png_name, width in png or []:
        subprocess.run(["rsvg-convert", "-w", str(width), "-o", str(OUT / png_name), str(p)], check=True)


def wordmark(x: float, y: float, size: float, theme: str, uid: str) -> tuple[str, str, float]:
    ink = INK_DARK_BG if theme == "dark" else INK_LIGHT_BG
    cols = SPK if theme == "dark" else SPK_LIGHT
    ls = -0.02 * size
    text = "VoxPrism"
    w_vox = text_width("Vox", INTER_BOLD, size, ls) + ls
    w_all = text_width(text, INTER_BOLD, size, ls)
    defs = (f'<linearGradient id="{uid}-g" gradientUnits="userSpaceOnUse" x1="{x + w_vox:.1f}" y1="0" '
            f'x2="{x + w_all:.1f}" y2="0"><stop offset="0" stop-color="{cols[0]}"/>'
            f'<stop offset="0.55" stop-color="{cols[1]}"/><stop offset="1" stop-color="{cols[2]}"/></linearGradient>')
    vox = text_path(text, INTER_BOLD, size, x, y, ls, 0, 3)
    prism = text_path(text, INTER_BOLD, size, x, y, ls, 3, None)
    body = f'<path d="{vox}" fill="{ink}"/>\n<path d="{prism}" fill="url(#{uid}-g)"/>'
    return defs, body, w_all


def build() -> None:
    # 1) 마크 (투명 배경) — 어두운 배경용 / 밝은 배경용
    for theme in ("dark", "light"):
        d, b = mark_group(theme, uid=f"mk{theme}")
        save(f"mark-{theme}.svg", svg(512, 512, d, b, "VoxPrism"))

    # 2) 앱 아이콘(배경 포함): 조직 아바타·파비콘
    d1, b1 = bg_rect(512, 512, 112)
    d2, b2 = mark_group("dark", uid="av")
    save("avatar.svg", svg(512, 512, d1 + d2, b1 + "\n" + b2, "VoxPrism"), [("avatar.png", 500)])
    d2, b2 = mark_group("dark", simple=True, uid="fi")
    save("favicon.svg", svg(512, 512, d1 + d2, b1 + "\n" + f'<g transform="translate(-22 0)">{b2}</g>', "VoxPrism"),
         [("favicon-32.png", 32), ("apple-touch-icon.png", 180)])

    # 3) 가로 로고(마크 + 글자) — README 머리말용, 밝은/어두운 배경 각각
    for theme in ("dark", "light"):
        h = 160
        s = h / 512
        dm, bm = mark_group(theme, uid=f"lk{theme}")
        dw, bw, ww = wordmark(176, 112, 92, theme, f"lw{theme}")
        w = 176 + ww + 8
        body = f'<g transform="scale({s:.4f})">{bm}</g>\n{bw}'
        save(f"logo-{theme}.svg", svg(round(w), h, dm + dw, body, "VoxPrism"))

    # 4) 배너 1280x640 (README 맨 위 + GitHub 소셜 미리보기)
    W, H = 1280, 640
    dbg, bbg = bg_rect(W, H, 0, "bnbg")
    dm, bm = mark_group("dark", uid="bn")
    ms = 452 / 512
    parts = [bbg]
    # 은은한 격자
    grid = []
    for gx in range(0, W + 1, 40):
        grid.append(f"M{gx} 0V{H}")
    for gy in range(0, H + 1, 40):
        grid.append(f"M0 {gy}H{W}")
    parts.append(f'<path d="{" ".join(grid)}" stroke="#FFFFFF" stroke-opacity="0.035" stroke-width="1"/>')
    parts.append(f'<g transform="translate(30 128) scale({ms:.4f})">{bm}</g>')
    tx = 520
    dw, bw, _ = wordmark(tx, 250, 118, "dark", "bnw")
    parts.append(bw)
    parts.append(f'<path d="{text_path("겹친 말까지, 누가 말했는지 보이게", NOTO_KR_MED, 42, tx + 4, 330)}" '
                 f'fill="{INK_DARK_BG}"/>')
    parts.append(f'<path d="{text_path("Speaker-aware captions for overlapping speech", INTER_MED, 25, tx + 4, 380)}" '
                 f'fill="#8E99B8"/>')
    # 동시에 말한 두 줄 자막 예시
    cap_y = 470
    for i, (name, line, col) in enumerate([("진행자", "오늘 저녁 뭐 먹지?", SPK[0]),
                                           ("게스트 1", "치킨 먹자, 치킨!", SPK[1])]):
        y = cap_y + i * 58
        nw = text_width(name, NOTO_KR_BOLD, 24)
        lw = text_width(line, NOTO_KR_MED, 26)
        bx, bwid = tx + 4, nw + lw + 52
        parts.append(f'<rect x="{bx}" y="{y - 34}" width="{bwid:.0f}" height="46" rx="10" fill="#000000" '
                     f'fill-opacity="0.55" stroke="{col}" stroke-opacity="0.35"/>')
        parts.append(f'<path d="{text_path(name, NOTO_KR_BOLD, 24, bx + 16, y - 2)}" fill="{col}"/>')
        parts.append(f'<path d="{text_path(line, NOTO_KR_MED, 26, bx + 16 + nw + 20, y - 2)}" fill="#FFFFFF"/>')
    parts.append(f'<path d="{text_path("CLOVA Speech · pyannote · SepFormer · NAVER Cloud", INTER_MED, 18, tx + 4, 604)}" '
                 f'fill="#6C7795"/>')
    save("banner.svg", svg(W, H, dbg + dm + dw, "\n".join(parts), "VoxPrism — 겹친 말까지, 누가 말했는지 보이게"),
         [("banner.png", 1280)])


if __name__ == "__main__":
    build()
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:24s} {p.stat().st_size:>8d} B")
