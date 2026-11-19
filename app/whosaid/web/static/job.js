(() => {
  const jobId = location.pathname.split("/").filter(Boolean).pop();
  const STAGES = [["prepare", "준비"], ["asr", "음성 인식"], ["diarize", "화자 구분"], ["overlap", "겹친 말 복원"], ["captions", "자막 생성"]];
  const video = $("#video"), capTop = $("#cap-top"), capBottom = $("#cap-bottom"), rail = $("#rail"), links = $("#links");
  let job = null, events = [], disp = {}, speakers = [], pollTimer = null, renderTimer = null;
  let scale = 1, showTags = true, showSfx = true, showRail = true, lastKey = "", lastActiveIds = "";
  let laneOf = {}, laneEls = [];

  const who = (sid) => disp[sid] || { id: sid, name: "?", color: "#fff" };

  async function load() {
    try {
      job = await api(`/api/jobs/${jobId}`);
    } catch (e) {
      $("#title").textContent = "작업을 찾을 수 없어요";
      $("#subtitle").textContent = e.message;
      return;
    }
    document.title = `VoxPrism · ${job.title || jobId}`;
    $("#title").textContent = job.title || jobId;
    const st = job.status || {};
    if (st.state === "queued" || st.state === "running") {
      showProgress(st);
      clearTimeout(pollTimer);
      pollTimer = setTimeout(load, 1500);
    } else if (st.state === "error") {
      $("#progress").hidden = true;
      const box = $("#error");
      box.hidden = false;
      box.innerHTML = `<b>처리하지 못했어요.</b> ${esc(st.message || "")}${st.detail ? `<br><span class="muted" style="font-size:13px">${esc(st.detail)}</span>` : ""}`;
    } else if (st.state === "done") {
      $("#progress").hidden = true;
      showResult();
    }
  }

  function showProgress(st) {
    $("#progress").hidden = false;
    $("#subtitle").textContent = st.state === "queued" ? "차례를 기다리는 중이에요" : "처리 중이에요";
    $("#pbar").style.width = `${st.progress || 0}%`;
    $("#pmsg").textContent = `${Math.round(st.progress || 0)}% · ${st.message || ""}`;
    const idx = STAGES.findIndex(([k]) => k === st.stage);
    $("#stages").innerHTML = STAGES.map(([k, ko], i) =>
      `<span class="stage ${i < idx ? "ok" : i === idx ? "now" : ""}">${i < idx ? "✓ " : ""}${ko}</span>`).join("");
  }

  function showResult() {
    const r = job.result;
    events = r.events || [];
    disp = r.display || {};
    speakers = r.speakers || [];
    const s = r.stats || {}, t = r.timings || {};
    $("#result").hidden = false;
    $("#subtitle").textContent = `${fmtDur(s.duration)} · 화자 ${s.speakers}명 · 인식: ${r.engine === "clova" ? "CLOVA Speech" : "Whisper"} · 화자 분리: ${r.diarization_model || "-"}`;
    if (!video.src) {
      video.src = `/media/${jobId}/preview.mp4`;
    }
    const warns = (job.status && job.status.warnings) || [];
    $("#warns").innerHTML = warns.map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join("");
    $("#stats").innerHTML = [
      [s.speakers, "화자"], [s.lines, "자막 줄"], [s.overlap_regions, "겹친 말 구간"],
      [s.overlap_lines, "동시 표시 줄"], [s.recovered_lines, "복원한 줄"], [s.sound_lines, "소리 자막"],
      [t.total ? `${Math.round(t.total)}초` : "-", "처리 시간"],
    ].map(([n, k]) => `<div class="stat"><div class="n">${esc(n ?? 0)}</div><div class="k">${k}</div></div>`).join("");
    for (const k of ["srt", "vtt", "ass", "json"]) $(`#dl-${k}`).href = `/api/jobs/${jobId}/download/${k}`;
    renderLegend();
    renderStage();
    renderSpeakers();
    renderScript();
    renderRender(job.render);
  }

  function renderLegend() {
    const seen = new Set();
    $("#legend").innerHTML = speakers.map((sp) => who(sp.id)).filter((d) => !seen.has(d.id) && seen.add(d.id))
      .map((d) => `<span style="--c:${esc(d.color)}">● ${esc(d.name)}</span>`).join("");
  }

  function renderSpeakers() {
    $("#speakers").innerHTML = speakers.map((sp) => {
      const opts = speakers.filter((o) => o.id !== sp.id)
        .map((o) => `<option value="${esc(o.id)}" ${sp.merge_into === o.id ? "selected" : ""}>${esc(who(o.id).name)} (${esc(o.id)})와 합치기</option>`).join("");
      return `
      <div class="spk" style="--c:${esc(sp.color)}" data-id="${esc(sp.id)}">
        <div class="head">
          <span class="badge" style="color:${esc(sp.color)}">${esc(sp.id)}</span>
          <input type="text" maxlength="30" value="${esc(sp.display && sp.display.id === sp.id ? sp.display.name : sp.name)}" aria-label="${esc(sp.id)} 이름">
        </div>
        <div class="meta">말한 시간 ${fmtDur(sp.talk_time)} · 자막 ${sp.lines}줄${sp.recovered_lines ? ` · 복원 ${sp.recovered_lines}줄` : ""}</div>
        <div class="thumbs">${(sp.thumbs || []).map((th) =>
          `<img src="/media/${jobId}/${esc(th.file)}" data-t="${th.t}" alt="${esc(sp.id)} ${fmtTime(th.t)} 장면" loading="lazy">`).join("")}</div>
        ${(sp.samples || []).map((x) => `<div class="sample">“${esc(x)}”</div>`).join("")}
        <select aria-label="${esc(sp.id)} 합치기"><option value="">합치지 않음</option>${opts}</select>
      </div>`;
    }).join("") || '<p class="muted">화자가 없어요.</p>';
    $$("#speakers img").forEach((img) => img.addEventListener("click", () => { video.currentTime = +img.dataset.t; video.play(); }));
  }

  function lineFlags(e) {
    let f = "";
    if (e.recovered) f += '<span class="flag rec" title="겹친 구간에서 분리해 복원한 말">복원</span>';
    else if (e.overlap) f += '<span class="flag" title="다른 사람과 동시에 한 말">동시</span>';
    return f;
  }

  function renderScript() {
    $("#script").innerHTML = events.map((e) => {
      const d = who(e.speaker), sfx = e.speaker === "_sfx";
      return `<div class="line ${sfx ? "sfx" : ""}" data-id="${e.id}" data-t="${e.start}" style="--c:${esc(d.color)}">
        <span class="tm">${fmtTime(e.start)}</span>
        <span>${sfx ? "" : `<span class="who">${esc(d.name)}</span>`}${esc(e.text)}${lineFlags(e)}</span></div>`;
    }).join("");
    $$("#script .line").forEach((el) => el.addEventListener("click", () => { video.currentTime = +el.dataset.t + 0.01; video.play(); }));
  }

  // ───── 자막 오버레이 (SPEC-008: 고정 줄 말풍선 + 말하는 사람 표시줄) ─────
  // 줄 배정: 시작 순서대로 비어 있는 가장 아래 줄에 넣고, 끝날 때까지 그 줄에서 움직이지 않는다.
  // 같은 규칙을 MP4용 captions.assign_lanes 가 쓴다.
  function assignLanes(evs) {
    const ends = [], lane = {};
    const dialog = evs.filter((e) => e.speaker !== "_sfx").slice().sort((a, b) => a.start - b.start || a.id - b.id);
    for (const e of dialog) {
      let i = ends.findIndex((t) => t <= e.start + 1e-6);
      if (i < 0) { i = ends.length; ends.push(0); }
      ends[i] = e.end;
      lane[e.id] = i;
    }
    return { lane, n: Math.max(1, ends.length) };
  }

  function railIds() {
    const seen = new Set();
    return speakers.map((sp) => who(sp.id).id).filter((id) => !seen.has(id) && seen.add(id));
  }

  function renderStage() {
    const { lane, n } = assignLanes(events);
    laneOf = lane;
    capBottom.innerHTML = Array.from({ length: n }, (_, i) => `<div class="lane" data-lane="${i}"></div>`).join("");
    laneEls = $$(".lane", capBottom);
    rail.innerHTML = railIds().map((id) => {
      const d = who(id);
      return `<span class="chip" data-id="${esc(id)}" style="--c:${esc(d.color)}"><span class="dot"></span><span class="nm">${esc(d.name)}</span></span>`;
    }).join("");
    lastKey = "";
  }

  function capHTML(e) {
    const d = who(e.speaker);
    if (e.speaker === "_sfx") return `<div class="cap sfx"><span class="txt">${esc(e.text)}</span></div>`;
    const chip = rail.querySelector(`.chip[data-id="${CSS.escape(d.id)}"]`);
    return `<div class="cap ${e.overlap ? "ov" : ""} ${e.uncertain ? "uncertain" : ""} ${chip ? "" : "nochip"}" data-spk="${esc(d.id)}" style="--c:${esc(d.color)}">
      <span class="tag">${esc(d.name)}</span><span class="txt">${esc(e.text)}</span></div>`;
  }

  // 말풍선 꼬리를 그 사람 칩 쪽으로 옮기고, 칩까지 같은 색 선으로 잇는다.
  function fitStage() {
    const player = $("#player"), stage = $("#capstage");
    player.classList.remove("compact");
    const pr = player.getBoundingClientRect(), sr = stage.getBoundingClientRect();
    if (sr.top < pr.top + 4 || sr.bottom > pr.bottom - 4) player.classList.add("compact");
  }

  function layoutLinks() {
    fitStage();
    const stage = $("#capstage"), sr = stage.getBoundingClientRect();
    const flip = $("#player").classList.contains("flip");
    let paths = "";
    for (const cap of $$(".cap[data-spk]", capBottom)) {
      const chip = rail.querySelector(`.chip[data-id="${CSS.escape(cap.dataset.spk)}"]`);
      if (!chip) continue;
      const cr = cap.getBoundingClientRect(), hr = chip.getBoundingClientRect();
      const em = parseFloat(getComputedStyle(cap).fontSize) || 16;
      const cx = hr.left + hr.width / 2;
      const r = Math.min(em * 0.9, cr.width / 2);
      const tx = Math.max(r, Math.min(cr.width - r, cx - cr.left));
      cap.style.setProperty("--tx", `${tx}px`);
      const x0 = cr.left + tx - sr.left, x1 = cx - sr.left;
      const y0 = (flip ? cr.top - em * 0.5 : cr.bottom + em * 0.5) - sr.top;
      const y1 = (flip ? hr.bottom : hr.top) - sr.top;
      if (Math.abs(y1 - y0) > 1) {
        const d = `M${x0.toFixed(1)} ${y0.toFixed(1)} L${x1.toFixed(1)} ${y1.toFixed(1)}`;
        paths += `<path d="${d}" stroke="rgba(0,0,0,.65)" stroke-width="${(em * 0.26).toFixed(1)}" stroke-linecap="round"/>`
          + `<path d="${d}" stroke="${esc(cap.style.getPropertyValue("--c"))}" stroke-width="${(em * 0.12).toFixed(1)}" stroke-linecap="round"/>`;
      }
    }
    links.innerHTML = paths;
  }

  function tick() {
    const t = video.currentTime || 0;
    const active = [];
    for (const e of events) {
      if (e.start > t) break;
      if (t < e.end) active.push(e);
    }
    const dialog = active.filter((e) => e.speaker !== "_sfx");
    const sfx = showSfx ? active.filter((e) => e.speaker === "_sfx") : [];
    const key = active.map((e) => e.id).join(",") + `|${showSfx}|${showTags}`;
    if (key !== lastKey) {
      lastKey = key;
      laneEls.forEach((el) => { el.innerHTML = ""; });
      for (const e of dialog) {
        const el = laneEls[laneOf[e.id] ?? 0] || laneEls[0];
        if (el) el.insertAdjacentHTML("beforeend", capHTML(e));
      }
      capTop.innerHTML = sfx.map(capHTML).join("");
      const talking = new Set(dialog.map((e) => who(e.speaker).id));
      $$(".chip", rail).forEach((c) => c.classList.toggle("on", talking.has(c.dataset.id)));
      layoutLinks();
      // 화면 읽기 프로그램용: 새로 나타난 자막만 읽도록
      capBottom.setAttribute("aria-label", dialog.map((e) => `${who(e.speaker).name}: ${e.text}`).join(" / "));
    }
    const ids = dialog.map((e) => e.id).join(",");
    if (ids !== lastActiveIds) {
      lastActiveIds = ids;
      $$("#script .line.active").forEach((el) => el.classList.remove("active"));
      dialog.forEach((e) => {
        const el = $(`#script .line[data-id="${e.id}"]`);
        if (el) {
          el.classList.add("active");
          if ($("#follow").checked && !video.paused) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      });
    }
    requestAnimationFrame(tick);
  }

  function resizeCaps() {
    const w = $("#player").clientWidth || 640;
    const px = Math.max(15, Math.min(64, w * 0.03 * scale));
    $("#capstage").style.fontSize = capTop.style.fontSize = `${px}px`;
    layoutLinks();
  }
  new ResizeObserver(resizeCaps).observe($("#player"));
  document.addEventListener("fullscreenchange", resizeCaps);

  function segment(id, cb) {
    $$(`#${id} button`).forEach((b) => b.addEventListener("click", () => {
      $$(`#${id} button`).forEach((x) => x.classList.toggle("on", x === b));
      cb(b.dataset.v);
    }));
  }
  segment("seg-size", (v) => { scale = +v; resizeCaps(); });
  segment("seg-pos", (v) => { $("#player").classList.toggle("flip", v === "top"); layoutLinks(); });
  $("#opt-tag").addEventListener("change", (e) => { showTags = e.target.checked; $("#player").classList.toggle("notags", !showTags); lastKey = ""; });
  $("#opt-rail").addEventListener("change", (e) => { showRail = e.target.checked; $("#player").classList.toggle("norail", !showRail); lastKey = ""; });
  $("#opt-sfx").addEventListener("change", (e) => { showSfx = e.target.checked; lastKey = ""; });
  $("#fs").addEventListener("click", () => {
    const p = $("#player");
    if (document.fullscreenElement) document.exitFullscreen(); else p.requestFullscreen?.();
  });

  // ───── 화자 이름 저장 ─────
  $("#save-spk").addEventListener("click", async () => {
    const body = { speakers: $$("#speakers .spk").map((el) => ({
      id: el.dataset.id, name: $("input", el).value.trim(), merge_into: $("select", el).value || null,
    })) };
    try {
      job = await api(`/api/jobs/${jobId}/speakers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      lastKey = "";
      showResult();
      toast("이름을 저장했어요. 자막 파일에도 반영됐어요.");
    } catch (e) { toast(`저장 실패: ${e.message}`); }
  });

  // ───── 자막 입힌 MP4 ─────
  function renderRender(rd) {
    const btn = $("#render"), dl = $("#dl-mp4"), msg = $("#render-msg");
    dl.hidden = true; btn.disabled = false; msg.textContent = "";
    if (!rd) return;
    if (rd.state === "queued" || rd.state === "running") {
      btn.disabled = true; msg.textContent = "영상에 자막을 입히는 중… (영상 길이의 절반 정도 걸려요)";
      clearTimeout(renderTimer);
      renderTimer = setTimeout(async () => { const j = await api(`/api/jobs/${jobId}`); job.render = j.render; renderRender(j.render); }, 2500);
    } else if (rd.state === "done") {
      dl.hidden = false; dl.href = `/api/jobs/${jobId}/download/mp4`; msg.textContent = "준비됐어요.";
    } else if (rd.state === "error") {
      msg.textContent = `실패: ${rd.message || ""}`;
    }
  }
  $("#render").addEventListener("click", async () => {
    try { const r = await api(`/api/jobs/${jobId}/render`, { method: "POST" }); renderRender(r.render); }
    catch (e) { toast(e.message); }
  });

  $("#del").addEventListener("click", async () => {
    if (!confirm("이 작업과 결과 파일을 모두 지울까요?")) return;
    try { await api(`/api/jobs/${jobId}`, { method: "DELETE" }); location.href = "/"; } catch (e) { toast(e.message); }
  });

  load();
  requestAnimationFrame(tick);
})();
