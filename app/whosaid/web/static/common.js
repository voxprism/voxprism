// 공통 도우미
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (t) => {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};
const fmtDur = (t) => {
  if (!t && t !== 0) return "-";
  const m = Math.floor(t / 60), s = Math.round(t % 60);
  return m ? `${m}분 ${s}초` : `${s}초`;
};
const fmtDate = (ts) => {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const STATE_KO = { queued: "대기", running: "처리 중", done: "완료", error: "오류" };
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch (_) { /* 본문 없음 */ }
  if (!r.ok) throw new Error((body && body.detail) || `요청 실패 (${r.status})`);
  return body;
}
function toast(msg) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove("show"), 2600);
}
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const set = (id, on) => { const el = $(id); if (el) el.classList.add(on ? "on" : "off"); };
    set("#pill-clova", h.clova_speech);
    set("#pill-diar", h.pyannote);
    return h;
  } catch (_) { return null; }
}
