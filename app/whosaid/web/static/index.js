(() => {
  const file = $("#file"), drop = $("#drop"), go = $("#go");
  let picked = null;

  function pick(f) {
    if (!f) return;
    picked = f;
    drop.classList.add("has-file");
    $("#drop-big").textContent = f.name;
    $("#drop-small").textContent = `${(f.size / 1024 / 1024).toFixed(1)} MB · 다른 파일을 고르려면 다시 누르세요`;
    if (!$("#title").value) $("#title").value = f.name.replace(/\.[^.]+$/, "").slice(0, 80);
    go.disabled = false;
  }
  file.addEventListener("change", () => pick(file.files[0]));
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => pick(e.dataTransfer.files[0]));

  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!picked) return;
    const fd = new FormData();
    fd.append("file", picked);
    fd.append("title", $("#title").value);
    fd.append("num_speakers", $("#nspk").value);
    fd.append("engine", $("#engine").value);
    fd.append("recover_overlap", $("#recover").checked);
    fd.append("sound_events", $("#sfx").checked);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    $("#upwrap").hidden = false;
    go.disabled = true;
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const p = (ev.loaded / ev.total) * 100;
      $("#upbar").style.width = `${p}%`;
      $("#uptext").textContent = p < 100 ? `업로드 중… ${p.toFixed(0)}%` : "서버에 저장하는 중…";
    };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (_) { /* 무시 */ }
      if (xhr.status >= 200 && xhr.status < 300 && body.id) {
        location.href = `/jobs/${body.id}`;
      } else {
        $("#uptext").textContent = `업로드 실패: ${body.detail || xhr.status}`;
        go.disabled = false;
      }
    };
    xhr.onerror = () => { $("#uptext").textContent = "네트워크 오류로 업로드하지 못했습니다."; go.disabled = false; };
    xhr.send(fd);
  });

  async function loadJobs() {
    const ul = $("#jobs");
    try {
      const { jobs } = await api("/api/jobs");
      if (!jobs.length) { ul.innerHTML = '<li class="muted">아직 작업이 없어요. 첫 영상을 올려 보세요.</li>'; return; }
      ul.innerHTML = jobs.map((j) => `
        <li>
          <span class="badge ${esc(j.state)}">${esc(STATE_KO[j.state] || j.state)}${j.state === "running" ? ` ${Math.round(j.progress || 0)}%` : ""}</span>
          <a class="t" href="/jobs/${esc(j.id)}">${esc(j.title)}</a>
          <span class="muted" style="font-size:13px">${j.speakers ? `화자 ${j.speakers}명 · ` : ""}${j.duration ? fmtDur(j.duration) + " · " : ""}${fmtDate(j.created_at)}</span>
        </li>`).join("");
    } catch (e) { ul.innerHTML = `<li class="muted">목록을 불러오지 못했어요: ${esc(e.message)}</li>`; }
  }
  $("#refresh").addEventListener("click", loadJobs);
  loadHealth().then((h) => {
    if (h) $("#limits").textContent = `영상 길이 최대 ${h.max_minutes}분 · 파일 최대 ${h.max_upload_mb}MB. 처리에는 영상 길이의 1.2배쯤 걸려요(5분 영상이면 약 6분).`;
  });
  loadJobs();
  setInterval(loadJobs, 8000);
})();
