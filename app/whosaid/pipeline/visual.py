"""화면 속 말하는 사람 찾기 (SPEC-009).

1. 프레임 읽기: 미리보기 영상을 FACE_FPS로 읽는다(짧은 변 기준 축소).
2. 얼굴 찾기·이어 붙이기: YuNet 얼굴 + 5점 랜드마크 → 연속 프레임 IoU로 얼굴 트랙, 장면 전환에서 끊는다.
3. 입 움직임: 입 주변 조각의 프레임 간 차이에서 머리 흔들림(눈 주변 차이)을 뺀 값.
4. 같은 사람 묶기: SFace 얼굴 특징 평균을 트랙끼리 비교해 사람(P1, P2…)으로 묶는다.
5. 얼굴–목소리 연결: 그 사람이 화면에 있을 때, 화자 S 혼자 말하는 시간의 입 움직임이
   다른 시간보다 얼마나 큰지(효과 크기)를 보고, 1:1로 가장 잘 맞는 쌍만 연결한다. 확신 없으면 연결하지 않는다.
6. 윤곽: 연결된 사람이 화면에 있고 그 목소리가 나오는 프레임만 YOLO 사람 분할로 몸 윤곽을 구한다.

결과는 visual.json(웹·MP4가 그림)과 화자별 '화면에 보이는 구간'(자막 '화면 밖' 판정)이다.
모델 파일은 MODEL_DIR/vision/ 아래: face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx,
yolo11n-seg.onnx. 하나라도 없으면 이 단계는 건너뛴다(자막은 그대로 나온다).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FACE_FPS = 10.0          # 얼굴·입 움직임
SEG_FPS = 5.0            # 사람 윤곽(강조할 프레임만)
FRAME_SHORT = 480        # 분석용 프레임 짧은 변
MIN_FACE = 28            # 이보다 작은 얼굴(픽셀)은 입 움직임을 믿지 않음
TRACK_GAP = 0.35         # 이보다 오래 안 보이면 트랙을 끊음(초)
SAME_PERSON = 0.42       # SFace 코사인 유사도: 이 이상이면 같은 사람
MIN_SUPPORT = 1.5        # 연결 근거: 화면에 보이며 그 화자가 말한 시간(초) 최소
BODY_IOU = 0.35          # 몸 추적: 이웃 프레임 사람 상자 IoU 최소
BODY_GAP = 0.45          # 몸 추적: 이보다 오래 끊기면 다른 트랙(초)
BODY_VOTES = 2           # 몸 트랙을 그 사람으로 볼 얼굴 확인 횟수 최소
MODEL_FILES = {
    "face": "face_detection_yunet_2023mar.onnx",
    "sface": "face_recognition_sface_2021dec.onnx",
    "seg": "yolo11n-seg.onnx",
}


# ───────────────────────────── 자료 구조 ─────────────────────────────

@dataclass
class Det:
    t: float
    box: tuple[float, float, float, float]   # x, y, w, h (분석 프레임 픽셀)
    lm: np.ndarray                           # (5, 2) 오른눈·왼눈·코·입 오른쪽·입 왼쪽
    score: float
    act: float = 0.0                         # 입 움직임(머리 흔들림 보정)
    emb: np.ndarray | None = None            # SFace 특징(일부 프레임만)


@dataclass
class Track:
    id: int
    dets: list[Det] = field(default_factory=list)
    emb: np.ndarray | None = None
    person: str | None = None

    @property
    def start(self) -> float:
        return self.dets[0].t

    @property
    def end(self) -> float:
        return self.dets[-1].t


def models_ready(model_dir: Path) -> bool:
    return all((model_dir / f).exists() for f in MODEL_FILES.values())


# ───────────────────────────── 프레임 읽기 ─────────────────────────────

def frame_size(width: int, height: int, short: int = FRAME_SHORT) -> tuple[int, int]:
    s = short / min(width, height)
    if s >= 1:
        return width - width % 2, height - height % 2
    w, h = int(round(width * s / 2) * 2), int(round(height * s / 2) * 2)
    return w, h


def read_frames(video: Path, fps: float, size: tuple[int, int]):
    """(t, BGR 프레임)을 차례로 낸다."""
    w, h = size
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    i = 0
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield i / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()


# ───────────────────────────── 얼굴 트랙 ─────────────────────────────

def iou(a, b) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    u = a[2] * a[3] + b[2] * b[3] - inter
    return inter / u if u > 0 else 0.0


def link_tracks(frames: list[tuple[float, list[Det]]], cuts: set[float] | None = None,
                gap: float = TRACK_GAP, min_iou: float = 0.3) -> list[Track]:
    """프레임별 얼굴을 IoU로 이어 트랙을 만든다. cuts(장면 전환 시각)에서는 잇지 않는다."""
    cuts = cuts or set()
    tracks: list[Track] = []
    live: list[Track] = []
    for t, dets in frames:
        if t in cuts:
            live = []
        live = [tr for tr in live if t - tr.end <= gap + 1e-6]
        pairs = sorted(((iou(tr.dets[-1].box, d.box), i, j) for i, tr in enumerate(live) for j, d in enumerate(dets)),
                       reverse=True)
        used_t, used_d = set(), set()
        for v, i, j in pairs:
            if v < min_iou or i in used_t or j in used_d:
                continue
            live[i].dets.append(dets[j])
            used_t.add(i)
            used_d.add(j)
        for j, d in enumerate(dets):
            if j not in used_d:
                tr = Track(id=len(tracks), dets=[d])
                tracks.append(tr)
                live.append(tr)
    return tracks


def _crop(gray: np.ndarray, cx: float, cy: float, w: float, h: float, out=(32, 20)) -> np.ndarray | None:
    import cv2
    x0, y0, x1, y1 = int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)
    H, W = gray.shape
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 - x0 < 6 or y1 - y0 < 4:
        return None
    c = cv2.resize(gray[y0:y1, x0:x1], out, interpolation=cv2.INTER_AREA).astype(np.float32)
    return (c - c.mean()) / (c.std() + 6.0)


def mouth_and_eye_crops(gray: np.ndarray, d: Det):
    """입 조각(입꼬리 사이 + 아래)과 눈 조각(머리 흔들림 기준)."""
    re, le, nose, rm, lm = d.lm
    mw = max(np.linalg.norm(lm - rm), d.box[2] * 0.25)
    mc = (rm + lm) / 2
    mouth = _crop(gray, mc[0], mc[1] + mw * 0.15, mw * 1.6, mw * 1.1)
    ec = (re + le) / 2
    ew = max(np.linalg.norm(le - re), d.box[2] * 0.3)
    eye = _crop(gray, ec[0], ec[1], ew * 1.6, ew * 0.7)
    return mouth, eye


def set_activity(track: Track, crops: list[tuple]) -> None:
    """crops[k] = (mouth, eye) for track.dets[k]. act = 입 변화 - 0.6 × 눈 변화 (연속 프레임만)."""
    prev = None
    for d, (m, e) in zip(track.dets, crops):
        d.act = 0.0
        if prev is not None and m is not None and prev[1] is not None and d.t - prev[0] <= 1.5 / FACE_FPS:
            dm = float(np.abs(m - prev[1]).mean())
            de = float(np.abs(e - prev[2]).mean()) if e is not None and prev[2] is not None else 0.0
            d.act = max(0.0, dm - 0.6 * de)
        prev = (d.t, m, e)


# ───────────────────────────── 같은 사람 묶기 ─────────────────────────────

def cluster(embs: list[np.ndarray], thr: float = SAME_PERSON) -> list[int]:
    """평균 연결 군집. 같은 사람이면 같은 번호."""
    n = len(embs)
    if n == 0:
        return []
    X = np.stack([e / (np.linalg.norm(e) + 1e-9) for e in embs])
    S = X @ X.T
    groups = [[i] for i in range(n)]
    while len(groups) > 1:
        best, bi, bj = -1.0, -1, -1
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                v = float(S[np.ix_(groups[i], groups[j])].mean())
                if v > best:
                    best, bi, bj = v, i, j
        if best < thr:
            break
        groups[bi] += groups.pop(bj)
    lab = [0] * n
    for k, g in enumerate(groups):
        for i in g:
            lab[i] = k
    return lab


# ───────────────────────────── 얼굴–목소리 연결 ─────────────────────────────

def _speaking(segments: list[dict], t: float) -> set[str]:
    """t에 말하고 있는 화자들."""
    return {s["speaker"] for s in segments if s["start"] <= t < s["end"]}


def associate(person_obs: dict[str, list[tuple[float, float]]], exclusive: list[dict],
              min_support: float = MIN_SUPPORT, dt: float = 1 / FACE_FPS) -> tuple[dict[str, str], dict]:
    """person_obs[P] = [(t, 입 움직임)] (그 사람 얼굴이 보인 프레임). exclusive: 한 사람만 말하는 구간.
    돌려줌: ({화자: 사람}, {(사람, 화자): 근거}).

    편집된 영상은 대개 말하는 사람을 비춘다는 점(동시 출현)과, 입 움직임(같은 사람 안에서 그 화자가 말할 때 더
    움직이는지, 여러 얼굴이 함께 보일 때 다른 얼굴보다 더 움직이는지)을 함께 본다.
      score = cooc + 0.3·within + 0.3·multi
      cooc   = 그 사람이 보이며 누군가 말한 시간 중 화자 S가 말한 비율
      within = (S가 말할 때 − 아닐 때) 입 움직임 차이 / 전체 표준편차
      multi  = 여러 얼굴이 보이며 S가 말할 때, 이 얼굴 − 다른 얼굴 평균 입 움직임 (표준편차 단위)
    근거 시간 ≥ min_support, cooc ≥ 0.5, score ≥ 0.6 이고 입 움직임이 반대로 나오지 않는(within ≥ −0.3,
    multi ≥ −0.5) 쌍만, 점수 큰 순서로 1:1 연결한다. 확신이 없으면 연결하지 않는다(화면 밖처럼 표시).
    """
    seg = sorted(exclusive, key=lambda x: x["start"])
    starts = [x["start"] for x in seg]

    def who(t: float) -> str | None:
        import bisect
        i = bisect.bisect_right(starts, t) - 1
        if i >= 0 and seg[i]["start"] <= t < seg[i]["end"]:
            return seg[i]["speaker"]
        return None

    allact = np.array([a for o in person_obs.values() for _, a in o], dtype=np.float64)
    g = float(allact.std()) + 1e-6 if len(allact) else 1.0
    at_time: dict[float, dict[str, float]] = {}
    for p, o in person_obs.items():
        for t, a in o:
            at_time.setdefault(round(t, 2), {})[p] = a / g
    spk_ids = sorted({x["speaker"] for x in seg})
    table: dict[tuple[str, str], dict] = {}
    for p, o in person_obs.items():
        if not o:
            continue
        w = [who(t) for t, _ in o]
        a = np.array([x for _, x in o], dtype=np.float64) / g
        talk_total = sum(1 for x in w if x)
        for s in spk_ids:
            on = np.array([x == s for x in w])
            support = float(on.sum()) * dt
            if support < min_support or talk_total == 0:
                continue
            cooc = float(on.sum()) / talk_total
            within = float(a[on].mean() - a[~on].mean()) if (~on).sum() >= 5 else 0.0
            mf = []
            for (t, _), is_on in zip(o, on):
                others = at_time.get(round(t, 2), {})
                if is_on and len(others) >= 2:
                    mf.append(others[p] - np.mean([v for q, v in others.items() if q != p]))
            multi = float(np.mean(mf)) if len(mf) >= 5 else 0.0
            score = cooc + 0.3 * float(np.clip(within, -2, 2)) + 0.3 * float(np.clip(multi, -2, 2))
            table[(p, s)] = {"score": round(score, 3), "cooc": round(cooc, 3), "within": round(within, 3),
                             "multi": round(multi, 3), "support": round(support, 1)}
    mapping: dict[str, str] = {}
    used_p: set[str] = set()
    for (p, s), v in sorted(table.items(), key=lambda kv: -kv[1]["score"]):
        if p in used_p or s in mapping:
            continue
        if v["cooc"] < 0.5 or v["score"] < 0.6 or v["within"] < -0.3 or v["multi"] < -0.5:
            continue
        mapping[s] = p
        used_p.add(p)
    return mapping, table


def intervals(times: list[float], step: float, gap: float | None = None) -> list[list[float]]:
    """샘플 시각들 → 이어진 구간 [[시작, 끝]]."""
    gap = gap if gap is not None else step * 1.6
    out: list[list[float]] = []
    for t in sorted(times):
        if out and t - out[-1][1] <= gap:
            out[-1][1] = t + step
        else:
            out.append([t, t + step])
    return [[round(a, 2), round(b, 2)] for a, b in out]


def offscreen_flags(events: list[dict], visible: dict[str, list[list[float]]], mapped: set[str],
                    any_face: bool, min_frac: float = 0.3) -> None:
    """자막마다 'offscreen' 표시. 얼굴이 하나도 없는 영상(음성 파일·그림 영상)은 표시하지 않는다."""
    for e in events:
        e["offscreen"] = False
        if not any_face or e["speaker"] in ("_sfx",):
            continue
        s = e["speaker"]
        if s not in mapped:
            e["offscreen"] = True
            continue
        dur = max(e["end"] - e["start"], 1e-3)
        seen = sum(max(0.0, min(e["end"], b) - max(e["start"], a)) for a, b in visible.get(s, []))
        e["offscreen"] = seen / dur < min_frac


# ───────────────────────────── 사람 윤곽(YOLO 분할) ─────────────────────────────

class PersonSeg:
    """YOLO11n-seg ONNX(80클래스, 사람=0) → 사람 인스턴스 마스크."""

    def __init__(self, path: Path, threads: int = 4):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.size = 640

    def __call__(self, img: np.ndarray, conf: float = 0.35) -> list[tuple[np.ndarray, np.ndarray]]:
        """[(box xyxy, mask HxW bool)] — img 좌표."""
        import cv2
        H, W = img.shape[:2]
        r = self.size / max(H, W)
        nw, nh = int(round(W * r)), int(round(H * r))
        pad = np.full((self.size, self.size, 3), 114, np.uint8)
        top, left = (self.size - nh) // 2, (self.size - nw) // 2
        pad[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh))
        x = pad[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out0, protos = self.sess.run(None, {"images": x})
        p = out0[0].T                      # (8400, 4+80+32)
        sc = p[:, 4]                        # 사람 점수
        keep = sc > conf
        if not keep.any():
            return []
        p, sc = p[keep], sc[keep]
        cx, cy, w, h = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
        boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
        xywh = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes]
        idx = cv2.dnn.NMSBoxes(xywh, sc.astype(float).tolist(), conf, 0.5)
        idx = np.array(idx).reshape(-1)
        if not len(idx):
            return []
        coef = p[idx, 84:]
        pr = protos[0].reshape(32, -1)
        masks = 1 / (1 + np.exp(-(coef @ pr)))
        masks = masks.reshape(-1, 160, 160)
        res = []
        for k, i in enumerate(idx):
            m = cv2.resize(masks[k], (self.size, self.size), interpolation=cv2.INTER_LINEAR)
            m = m[top:top + nh, left:left + nw]
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) > 0.5
            b = boxes[i].copy()
            b[[0, 2]] = (b[[0, 2]] - left) / r
            b[[1, 3]] = (b[[1, 3]] - top) / r
            bx = np.clip(b, 0, [W, H, W, H])
            crop = np.zeros_like(m)
            x0, y0, x1, y1 = [int(v) for v in bx]
            crop[y0:y1 + 1, x0:x1 + 1] = m[y0:y1 + 1, x0:x1 + 1]
            res.append((bx, crop))
        return res


def outline(mask: np.ndarray, W: int, H: int, max_pts: int = 64) -> list[list[float]] | None:
    """가장 큰 윤곽을 단순화해 0~1 좌표로."""
    import cv2
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.002 * W * H:
        return None
    eps = 0.003 * cv2.arcLength(c, True)
    a = cv2.approxPolyDP(c, eps, True)
    while len(a) > max_pts:
        eps *= 1.5
        a = cv2.approxPolyDP(c, eps, True)
    return [[round(float(x) / W, 4), round(float(y) / H, 4)] for [[x, y]] in a]


def face_outline(box, W: int, H: int) -> list[list[float]]:
    """분할이 없을 때: 얼굴 상자를 조금 키운 타원."""
    x, y, w, h = box
    cx, cy, rx, ry = x + w / 2, y + h / 2, w * 0.75, h * 0.85
    return [[round((cx + rx * np.cos(a)) / W, 4), round((cy + ry * np.sin(a)) / H, 4)]
            for a in np.linspace(0, 2 * np.pi, 24, endpoint=False)]


def pick_person(face_box, persons: list[tuple[np.ndarray, np.ndarray]]):
    """얼굴 가운데를 품고, 얼굴이 몸 위쪽에 있는 사람 마스크."""
    k = pick_person_index(face_box, persons)
    return persons[k] if k is not None else None


def pick_person_index(face_box, persons) -> int | None:
    fx, fy, fw, fh = face_box
    cx, cy = int(fx + fw / 2), int(fy + fh / 2)
    best, bv = None, 0.0
    for k, (b, m) in enumerate(persons):
        if not (b[0] <= cx <= b[2] and b[1] <= cy <= b[3]):
            continue
        if cy < m.shape[0] and cx < m.shape[1] and not m[cy, cx]:
            # 얼굴 가운데가 마스크 밖이면 감점
            v = 0.3
        else:
            v = 1.0
        top_bias = 1.0 - min(1.0, (cy - b[1]) / max(1.0, b[3] - b[1]))
        v *= 0.5 + 0.5 * top_bias
        if v > bv:
            best, bv = k, v
    return best


def label_bodies(frames: list[tuple[float, list, dict]], cuts: set[float] | None = None,
                 min_iou: float = BODY_IOU, gap: float = BODY_GAP, min_votes: int = BODY_VOTES) -> list[dict[int, str]]:
    """몸 추적으로 '얼굴이 안 보이는 순간'에도 사람을 알아본다 (SPEC-009 FR-VIS-07).

    frames[i] = (t, 사람 상자 목록[xyxy], {사람 P: 그 프레임에서 P 얼굴이 속한 상자 번호}).
    이웃 프레임 상자를 IoU로 이어 몸 트랙을 만들고(장면 전환·공백에서 끊음), 트랙 안에서 얼굴로 확인된 사람을
    투표해 min_votes 이상이고 60% 이상이면 트랙 전체를 그 사람으로 본다.
    돌려줌: 프레임마다 {상자 번호: 사람}.
    """
    cuts = sorted(cuts or [])
    track_of: list[list[int]] = []
    n_tracks = 0
    prev_t, prev_boxes, prev_ids = None, [], []
    for t, boxes, _ in frames:
        ids = [-1] * len(boxes)
        cut = prev_t is not None and any(prev_t < c <= t for c in cuts)
        if prev_t is not None and not cut and t - prev_t <= gap + 1e-6:
            pairs = sorted(((_iou_xyxy(pb, b), i, j) for i, pb in enumerate(prev_boxes) for j, b in enumerate(boxes)),
                           reverse=True)
            used_i, used_j = set(), set()
            for v, i, j in pairs:
                if v < min_iou or i in used_i or j in used_j:
                    continue
                ids[j] = prev_ids[i]
                used_i.add(i)
                used_j.add(j)
        for j in range(len(ids)):
            if ids[j] < 0:
                ids[j] = n_tracks
                n_tracks += 1
        track_of.append(ids)
        prev_t, prev_boxes, prev_ids = t, boxes, ids
    votes: dict[int, dict[str, int]] = {}
    for (t, boxes, links), ids in zip(frames, track_of):
        for person, k in links.items():
            if k is not None and 0 <= k < len(ids):
                v = votes.setdefault(ids[k], {})
                v[person] = v.get(person, 0) + 1
    label: dict[int, str] = {}
    for tid, v in votes.items():
        person, c = max(v.items(), key=lambda kv: kv[1])
        if c >= min_votes and c / sum(v.values()) >= 0.6:
            label[tid] = person
    return [{j: label[tid] for j, tid in enumerate(ids) if tid in label} for ids in track_of]


def _iou_xyxy(a, b) -> float:
    return iou((a[0], a[1], a[2] - a[0], a[3] - a[1]), (b[0], b[1], b[2] - b[0], b[3] - b[1]))


# ───────────────────────────── 전체 실행 ─────────────────────────────

def analyze(video: Path, size: tuple[int, int], turns: list[dict], exclusive: list[dict], out_dir: Path,
            model_dir: Path, progress=None, threads: int = 4) -> dict:
    """visual.json 내용을 만든다(화자 id는 화자 분리 원래 이름)."""
    import cv2
    prog = progress or (lambda f, m="": None)
    W, H = frame_size(*size)
    det = cv2.FaceDetectorYN.create(str(model_dir / MODEL_FILES["face"]), "", (W, H), 0.75, 0.3, 50)
    rec = cv2.FaceRecognizerSF.create(str(model_dir / MODEL_FILES["sface"]), "")
    duration = max([t["end"] for t in turns] + [0.0])

    # 1) 얼굴·랜드마크, 장면 전환, 입 조각
    frames: list[tuple[float, list[Det]]] = []
    crops: dict[int, tuple] = {}
    cuts: set[float] = set()
    prev_hist = None
    k_emb = int(round(FACE_FPS / 2))  # 얼굴 특징은 초당 2번만
    for fi, (t, img) in enumerate(read_frames(video, FACE_FPS, (W, H))):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([cv2.resize(gray, (64, 36))], [0], None, [32], [0, 256]).ravel()
        hist /= hist.sum() + 1e-9
        if prev_hist is not None and 0.5 * np.abs(hist - prev_hist).sum() > 0.35:
            cuts.add(t)
        prev_hist = hist
        _, faces = det.detect(img)
        dets: list[Det] = []
        for f in (faces if faces is not None else []):
            d = Det(t=t, box=(float(f[0]), float(f[1]), float(f[2]), float(f[3])),
                    lm=np.array(f[4:14], dtype=np.float32).reshape(5, 2), score=float(f[14]))
            if d.box[2] < MIN_FACE * 0.6:
                continue
            dets.append(d)
            crops[id(d)] = mouth_and_eye_crops(gray, d)
            if d.box[2] >= MIN_FACE * 1.5 and fi % k_emb == 0:
                d.emb = rec.feature(rec.alignCrop(img, f)).ravel().copy()
        frames.append((t, dets))
        if duration:
            prog(min(0.55, 0.55 * t / duration), "화면 속 얼굴을 찾고 있어요")
    tracks = [tr for tr in link_tracks(frames, cuts) if len(tr.dets) >= 3]
    for tr in tracks:
        set_activity(tr, [crops.get(id(d), (None, None)) for d in tr.dets])

    # 2) 트랙 특징값: 트랙에서 가장 큰 얼굴 5장의 평균
    for tr in tracks:
        fs = [d.emb / (np.linalg.norm(d.emb) + 1e-9)
              for d in sorted((d for d in tr.dets if d.emb is not None), key=lambda d: -d.box[2])[:5]]
        if fs:
            tr.emb = np.mean(fs, 0)
    prog(0.6, "같은 사람의 얼굴을 묶고 있어요")

    # 3) 사람 묶기
    named = [tr for tr in tracks if tr.emb is not None]
    labels = cluster([tr.emb for tr in named])
    for tr, k in zip(named, labels):
        tr.person = f"P{k + 1}"
    person_obs: dict[str, list[tuple[float, float]]] = {}
    for tr in named:
        big = np.median([d.box[2] for d in tr.dets]) >= MIN_FACE
        if big:
            person_obs.setdefault(tr.person, []).extend((d.t, d.act) for d in tr.dets[1:])

    # 4) 얼굴–목소리 연결
    mapping, table = associate(person_obs, exclusive)
    face_of = {p: s for s, p in mapping.items()}

    # 5) 화자별 '화면에 보이는' 구간
    visible: dict[str, list[list[float]]] = {}
    for s, p in mapping.items():
        ts = sorted(d.t for tr in named if tr.person == p for d in tr.dets)
        visible[s] = intervals(ts, 1 / FACE_FPS)

    # 6) 강조 윤곽: 누군가 말하는 SEG_FPS 프레임마다 사람 분할 → 얼굴로 확인된 사람의 몸을 추적해서
    #    얼굴이 안 보이는 순간(뒤돌기·옆모습·가림)에도 같은 사람의 몸에 윤곽을 그린다 (FR-VIS-07)
    seg = PersonSeg(model_dir / MODEL_FILES["seg"], threads=threads)
    by_time: dict[float, list[Det]] = {}
    for tr in named:
        if tr.person in face_of:
            for d in tr.dets:
                by_time.setdefault(round(d.t, 2), []).append(d)
    det_person = {id(d): tr.person for tr in named for d in tr.dets}
    seg_frames: list[tuple[float, list, dict]] = []
    polys: list[list] = []
    faces_seen: list[dict[str, Det]] = []
    for t, img in read_frames(video, SEG_FPS, (W, H)) if face_of else []:
        if duration:
            prog(0.6 + 0.36 * min(1.0, t / duration), "말하는 사람의 윤곽을 그리고 있어요")
        if not _speaking(turns, t):
            continue
        persons = seg(img)
        links: dict[str, int | None] = {}
        seen: dict[str, Det] = {}
        for d in by_time.get(round(t, 2), []):
            p = det_person.get(id(d))
            links[p] = pick_person_index(d.box, persons)
            seen[p] = d
        seg_frames.append((round(t, 2), [b for b, _ in persons], links))
        polys.append([outline(m, W, H) for _, m in persons])
        faces_seen.append(seen)
    body_label = label_bodies(seg_frames, cuts)
    out_frames = []
    body_times: dict[str, list[float]] = {}
    for (t, boxes, links), pl, seen, bl in zip(seg_frames, polys, faces_seen, body_label):
        talking = _speaking(turns, t)
        hl = []
        for s in sorted(talking):
            p = mapping.get(s)
            if p is None:
                continue
            k = links.get(p)
            if k is None:
                k = next((j for j, q in bl.items() if q == p), None)
            d = seen.get(p)
            poly = pl[k] if k is not None else None
            if poly is None and d is not None:
                poly = face_outline(d.box, W, H)
            if poly is None:
                continue
            item = {"spk": s, "poly": poly}
            if d is not None:
                item["face"] = [round(d.box[0] / W, 4), round(d.box[1] / H, 4), round(d.box[2] / W, 4),
                                round(d.box[3] / H, 4)]
            else:
                item["body"] = True  # 얼굴 없이 몸 추적으로 찾음
            hl.append(item)
        for q in set(bl.values()):
            body_times.setdefault(q, []).append(t)
        if hl:
            out_frames.append({"t": t, "hl": hl})
    # 몸으로 보인 시간도 '화면에 보임'에 더한다
    for s, p in mapping.items():
        if body_times.get(p):
            ts = sorted({round(a, 2) for iv in visible.get(s, []) for a in np.arange(iv[0], iv[1], 1 / FACE_FPS)}
                        | {round(x + k / FACE_FPS, 2) for x in body_times[p] for k in range(2)})
            visible[s] = intervals(ts, 1 / FACE_FPS)

    # 사람 대표 얼굴(화자 카드용)
    out_dir.mkdir(parents=True, exist_ok=True)
    people = []
    for p in sorted({tr.person for tr in named}, key=lambda x: int(x[1:])):
        trs = [tr for tr in named if tr.person == p]
        secs = sum(tr.end - tr.start + 1 / FACE_FPS for tr in trs)
        people.append({"id": p, "speaker": face_of.get(p), "seconds": round(secs, 1), "tracks": len(trs)})
    return {
        "version": 1, "fps": SEG_FPS, "size": [W, H],
        "people": people, "speaker_face": mapping,
        "scores": [{"person": p, "speaker": s, **v} for (p, s), v in sorted(table.items())],
        "visible": visible, "any_face": bool(named), "frames": out_frames,
        "_face_pick": {p: _best_face(named, p) for p in face_of},
    }


def _best_face(tracks: list[Track], person: str) -> dict | None:
    best = None
    for tr in tracks:
        if tr.person != person:
            continue
        for d in tr.dets:
            if best is None or d.box[2] > best["w"]:
                best = {"t": d.t, "x": d.box[0], "y": d.box[1], "w": d.box[2], "h": d.box[3]}
    return best


def save_faces(video: Path, size: tuple[int, int], picks: dict[str, dict | None], out_dir: Path) -> dict[str, str]:
    """사람마다 얼굴 사진 1장(화자 카드용). 돌려줌: {사람: 상대 경로}."""
    import cv2
    W, H = frame_size(*size)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    for p, f in picks.items():
        if not f:
            continue
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{f['t']:.2f}", "-i", str(video), "-frames:v", "1",
               "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        buf = subprocess.run(cmd, capture_output=True).stdout
        if len(buf) < W * H * 3:
            continue
        img = np.frombuffer(buf[: W * H * 3], np.uint8).reshape(H, W, 3)
        m = 0.35 * f["w"]
        x0, y0 = int(max(0, f["x"] - m)), int(max(0, f["y"] - m))
        x1, y1 = int(min(W, f["x"] + f["w"] + m)), int(min(H, f["y"] + f["h"] + m))
        crop = cv2.resize(img[y0:y1, x0:x1], (160, int(160 * (y1 - y0) / max(1, x1 - x0))))
        path = out_dir / f"{p}.jpg"
        cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        res[p] = f"faces/{p}.jpg"
    return res
