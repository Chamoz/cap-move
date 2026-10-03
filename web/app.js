// Review page: val-video mode (GT vs out-of-fold prediction) and upload mode (open-world, experimental).
const S = { mode: "val", data: null, segs: [], sel: null, classes: [], reviews: {}, ref: null, poll: null,
  deferred: new Set(), prevF: -1, rv: null,
  cam: { stream: null, rec: null, chunks: [], timer: null, maxSeconds: 90 } };
const $ = (id) => document.getElementById(id);
const video = $("video"), canvas = $("overlay"), ctx = canvas.getContext("2d");

// ------------------------------------------------------------------ boot
(async function init() {
  const info = await loadFooter();
  S.classes = info ? info.classes : Object.keys(CLASS_COLORS);
  if (info) { $("maxs").textContent = info.max_upload_seconds; $("maxmb").textContent = info.max_upload_mb;
    S.cam.maxSeconds = info.max_upload_seconds; }
  $("tab-val").onclick = () => setMode("val");
  $("tab-up").onclick = () => setMode("upload");
  $("vfilter").oninput = renderVideoList;
  $("upform").onsubmit = onUpload;
  $("camstart").onclick = startCam;
  $("camrec").onclick = startRec;
  $("camstop").onclick = () => stopRec(false);
  $("camoff").onclick = stopCam;
  $("camdevice").onchange = switchCam;
  if (navigator.mediaDevices) {
    populateCameras();
    if (navigator.mediaDevices.addEventListener)
      navigator.mediaDevices.addEventListener("devicechange", populateCameras);
  }
  $("play").onclick = togglePlay;
  $("prev").onclick = () => stepSeg(-1, false);
  $("next").onclick = () => stepSeg(1, false);
  $("nextflag").onclick = () => stepSeg(1, true);
  $("speed").onchange = () => { video.playbackRate = Number($("speed").value); };
  video.addEventListener("loadedmetadata", layout);
  video.addEventListener("play", () => { $("play").textContent = "⏸ Pause"; tick(); });
  video.addEventListener("pause", () => { $("play").textContent = "▶ Play"; });
  video.addEventListener("seeked", () => { S.prevF = curFrame(); draw(); });
  initReviewModal();
  window.addEventListener("resize", () => { layout(); renderTimeline(); });
  document.addEventListener("keydown", onKey);
  S.videos = await api("api/val/videos");
  renderVideoList();
  const want = new URLSearchParams(location.search);
  if (want.get("video")) openVal(want.get("video"), want.get("segment"));
  else if (want.get("job")) { setMode("upload"); openJob(want.get("job")); }
})();

function setMode(m) {
  S.mode = m;
  $("tab-val").setAttribute("aria-selected", m === "val"); $("tab-val").setAttribute("aria-pressed", m === "val");
  $("tab-up").setAttribute("aria-selected", m === "upload"); $("tab-up").setAttribute("aria-pressed", m === "upload");
  $("pane-val").hidden = m !== "val"; $("pane-up").hidden = m !== "upload";
}

function renderVideoList() {
  const q = $("vfilter").value.toLowerCase();
  const ul = $("vlist"); ul.replaceChildren();
  for (const v of S.videos) {
    if (q && !(`${v.collection_name} ${v.collector}`.toLowerCase().includes(q))) continue;
    if (!v.n_segments) continue;
    ul.append(el("li", {}, el("button", { "aria-current": S.ref === v.video_id ? "true" : null, onclick: () => openVal(v.video_id) },
      el("div", {}, v.collection_name),
      el("div", { class: "small" }, `collector ${v.collector} · fold ${v.fold} · ${v.n_segments} seg `,
        v.n_flagged ? el("span", { class: "badge flag" }, `⚑ ${v.n_flagged}`) : null, " ",
        v.n_wrong ? el("span", { class: "badge bad" }, `✗ ${v.n_wrong}`) : null))));
  }
}

// ------------------------------------------------------------------ loading sources
async function openVal(videoId, segId) {
  const d = await api(`api/val/videos/${encodeURIComponent(videoId)}`);
  S.ref = d.video_id; S.mode = "val"; renderVideoList();
  S.data = { kind: "val", fps: d.fps, n_frames: d.n_frames, w: d.width, h: d.height, tracks: d.tracks };
  S.segs = d.segments.map((s) => ({ ...s, id: s.segment_id }));
  S.reviews = d.reviews || {};
  $("ptitle").textContent = `— ${d.collection_name} · collector ${d.collector}`;
  loadMedia(d.media_url);
  select(segId ? S.segs.find((s) => s.id === segId) : S.segs[0], !!segId);
}

async function onUpload(ev) {
  ev.preventDefault();
  const f = $("upfile").files[0];
  if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  $("upstatus").textContent = "Uploading…";
  try {
    const r = await api("api/upload", { method: "POST", body: fd });
    history.replaceState(null, "", `./?job=${r.job_id}`);
    openJob(r.job_id);
  } catch (e) { $("upstatus").replaceChildren(el("div", { class: "notice error" }, e.message)); }
}

// ------------------------------------------------------------------ live webcam capture
// Pixels stay on this host (contract §2.3): getUserMedia runs in the browser, the clip is encoded
// locally with MediaRecorder and POSTed to this server's existing /api/upload endpoint only.
// Feeds the same experimental, unscored open-world pipeline as a file upload.
function camStatus(msg, isError) {
  $("camstatus").replaceChildren(isError ? el("div", { class: "notice error" }, msg) : msg);
}

function camButtons({ start, rec, stop, off }) {
  const set = (id, enabled, hidden) => {
    const b = $(id); b.disabled = !enabled; b.setAttribute("aria-disabled", String(!enabled));
    if (hidden !== undefined) b.hidden = hidden;
  };
  set("camstart", start); set("camrec", rec, false); set("camstop", stop, !stop); set("camoff", off);
}

function camSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
}

// Map getUserMedia DOMException names to actionable messages.
function camErrorMessage(e) {
  switch (e && e.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera permission was denied. Allow camera access for this site in your browser, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera matching the selection was found on this device.";
    case "NotReadableError":
      return "The camera is in use by another app (close other apps/tabs using it) or a hardware error occurred.";
    case "AbortError":
      return "Camera start was aborted. Try again.";
    default:
      return `Camera unavailable: ${(e && e.message) || e}`;
  }
}

// Populate the camera <select> from enumerateDevices. Labels are only visible after permission is
// granted once; before that we still list devices by index so the user can pick.
async function populateCameras() {
  const sel = $("camdevice");
  if (!sel || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
  let devices = [];
  try { devices = await navigator.mediaDevices.enumerateDevices(); } catch (e) { return; }
  const cams = devices.filter((d) => d.kind === "videoinput");
  const prev = sel.value;
  sel.replaceChildren(el("option", { value: "" }, "Default camera"));
  cams.forEach((d, i) => sel.append(el("option", { value: d.deviceId }, d.label || `Camera ${i + 1}`)));
  if (prev && cams.some((d) => d.deviceId === prev)) sel.value = prev;
  $("camstatus").dataset.ncams = String(cams.length);
}

function pickMime() {
  // Prefer webm (server allows .webm); fall back to whatever the browser offers.
  const prefs = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"];
  for (const m of prefs) if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
  return "";
}

async function startCam() {
  if (!window.isSecureContext) {
    camStatus("Camera needs a secure context (HTTPS). Open this site over https:// and try again.", true); return;
  }
  if (!camSupported()) { camStatus("This browser has no getUserMedia/MediaRecorder support.", true); return; }
  camStatus("Requesting camera…");
  // Build constraints from the chosen device, falling back to the front ("user") camera.
  const chosen = $("camdevice") ? $("camdevice").value : "";
  const video = chosen ? { deviceId: { exact: chosen } } : { facingMode: "user" };
  try {
    S.cam.stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });
  } catch (e) { camStatus(camErrorMessage(e), true); return; }
  $("cam").srcObject = S.cam.stream;
  // Device labels become available only after permission is granted — refresh the picker now.
  await populateCameras();
  const track = S.cam.stream.getVideoTracks()[0];
  const name = track ? track.label || "camera" : "camera";
  camButtons({ start: false, rec: true, stop: false, off: true });
  camStatus(`Camera on (${name}). Press Record, perform the activity, then Stop & analyse.`);
}

// Switch to a different camera while live (called when the picker changes with the camera on).
async function switchCam() {
  if (!S.cam.stream) return;  // not live yet; selection applies on next Enable
  if (S.cam.rec && S.cam.rec.state !== "inactive") { camStatus("Stop recording before switching camera.", true); return; }
  S.cam.stream.getTracks().forEach((t) => t.stop());
  S.cam.stream = null;
  await startCam();
}

function stopCam() {
  stopRec(true);
  if (S.cam.stream) { S.cam.stream.getTracks().forEach((t) => t.stop()); S.cam.stream = null; }
  $("cam").srcObject = null;
  camButtons({ start: true, rec: false, stop: false, off: false });
  camStatus("Camera off.");
}

function startRec() {
  if (!S.cam.stream) return;
  const mime = pickMime();
  const ext = mime.startsWith("video/mp4") ? ".mp4" : ".webm";
  let rec;
  try { rec = new MediaRecorder(S.cam.stream, mime ? { mimeType: mime } : undefined); }
  catch (e) { camStatus(`Cannot start recorder: ${e.message}`, true); return; }
  S.cam.rec = rec; S.cam.chunks = []; S.cam.ext = ext;
  rec.ondataavailable = (ev) => { if (ev.data && ev.data.size) S.cam.chunks.push(ev.data); };
  rec.onstop = () => submitRecording(rec.mimeType || mime, ext);
  rec.start();
  camButtons({ start: false, rec: false, stop: true, off: true });
  // Hard cap recording at the server's max upload duration.
  const started = Date.now();
  S.cam.timer = setInterval(() => {
    const s = (Date.now() - started) / 1000;
    camStatus(`Recording… ${s.toFixed(1)}s / ${S.cam.maxSeconds}s`);
    if (s >= S.cam.maxSeconds) stopRec();
  }, 200);
}

function stopRec(silent) {
  const discard = silent === true;  // only an explicit true discards; guards against an event arg
  if (S.cam.timer) { clearInterval(S.cam.timer); S.cam.timer = null; }
  if (S.cam.rec && S.cam.rec.state !== "inactive") {
    if (discard) S.cam.rec.onstop = null;  // turning the camera off mid-record: discard, don't submit
    S.cam.rec.stop();  // fires rec.onstop -> submitRecording (unless discarded)
  }
  if (!discard) camButtons({ start: false, rec: false, stop: false, off: true });
}

// The "process live webcam" step: package the recorded frames and send them to the host.
async function submitRecording(mimeType, ext) {
  const blob = new Blob(S.cam.chunks, { type: mimeType });
  S.cam.chunks = [];
  if (!blob.size) { camStatus("Nothing was recorded.", true); camButtons({ start: false, rec: true, stop: false, off: true }); return; }
  camStatus(`Captured ${(blob.size / 1048576).toFixed(1)} MB; uploading to this host…`);
  const fd = new FormData();
  fd.append("file", blob, `webcam${ext}`);  // filename ext drives the server's ALLOWED_EXT check
  try {
    const r = await api("api/upload", { method: "POST", body: fd });
    camStatus("Analysing… see the Player panel.");
    history.replaceState(null, "", `./?job=${r.job_id}`);
    openJob(r.job_id);
  } catch (e) {
    camStatus(e.message, true);
  } finally {
    camButtons({ start: false, rec: true, stop: false, off: true });
  }
}

async function openJob(jobId) {
  clearInterval(S.poll);
  const prog = $("upprog"); prog.hidden = false;
  const step = async () => {
    let j;
    try { j = await api(`api/jobs/${jobId}`); } catch (e) { $("upstatus").textContent = e.message; clearInterval(S.poll); return; }
    prog.value = j.progress; $("upstatus").textContent = `${j.status}: ${j.message}`;
    if (j.status === "error") { clearInterval(S.poll); $("upstatus").replaceChildren(el("div", { class: "notice error" }, j.message)); }
    if (j.status === "done") { clearInterval(S.poll); prog.hidden = true; showJob(jobId, j); }
  };
  S.poll = setInterval(step, 1500); step();
}

function showJob(jobId, j) {
  const r = j.result, m = r.meta;
  S.ref = jobId;
  S.data = { kind: "upload", fps: m.proc_fps, n_frames: m.n_frames, w: m.proxy_size[0], h: m.proxy_size[1],
    tracks: r.tracks, windows: r.windows };
  S.segs = r.segments.map((s) => ({ ...s, id: s.segment_id, pred: s }));
  S.reviews = j.reviews || {};
  $("ptitle").textContent = `— upload ${jobId.slice(0, 8)} · ${r.tracks.length} track(s) · ${r.segments.length} segment(s) · EXPERIMENTAL, unscored`;
  $("upstatus").replaceChildren(el("div", { class: "small" },
    `Processed in ${m.elapsed_s}s at ${fmt(m.proc_fps, 1)} fps; window ${m.window_s}s / stride ${m.stride_s}s; ` +
    `static windows (motion < ${m.motion_gate}) are labelled no-activity.`));
  loadMedia(j.media_url);
  select(S.segs[0], false);
}

function loadMedia(url) {
  closeReview(false); S.deferred.clear(); S.prevF = -1;
  video.pause(); video.src = url; video.playbackRate = Number($("speed").value); video.load();
  renderTimeline();
}

// ------------------------------------------------------------------ geometry
function trackBox(tr, f) {
  if (S.data.kind === "val") {
    const k = tr.keyframes;
    if (f < k[0] || f > k[k.length - 1]) return null;
    let lo = 0, hi = k.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (k[mid] <= f) lo = mid; else hi = mid; }
    const a = tr.boxes[lo], b = tr.boxes[hi], t = k[hi] === k[lo] ? 0 : (f - k[lo]) / (k[hi] - k[lo]);
    return a.map((v, i) => v + t * (b[i] - v));
  }
  const i = f - tr.frames[0];
  return i >= 0 && i < tr.boxes.length ? tr.boxes[i] : null;
}

function curFrame() { return S.data ? Math.min(S.data.n_frames - 1, Math.floor(video.currentTime * S.data.fps + 1e-3)) : 0; }

function layout() {
  const r = video.getBoundingClientRect(), p = $("stage").getBoundingClientRect();
  canvas.style.left = (r.left - p.left) + "px"; canvas.style.top = (r.top - p.top) + "px";
  canvas.width = Math.round(r.width); canvas.height = Math.round(r.height);
  if (S.data && video.videoWidth && Math.abs(video.videoWidth / video.videoHeight - S.data.w / S.data.h) > 0.02)
    console.warn("video aspect differs from annotation space", video.videoWidth, video.videoHeight, S.data.w, S.data.h);
  draw();
}

// ------------------------------------------------------------------ drawing
function activeSegs(f, trackId) {
  return S.segs.filter((s) => s.start_frame <= f && f <= s.end_frame && (!trackId || s.track_id === trackId));
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!S.data) return;
  const f = curFrame(), sx = canvas.width / S.data.w, sy = canvas.height / S.data.h;
  $("tc").textContent = `frame ${f} · ${video.currentTime.toFixed(2)}s`;
  ctx.lineWidth = 3; ctx.font = "bold 13px system-ui"; ctx.textBaseline = "top";
  for (const tr of S.data.tracks) {
    const b = trackBox(tr, f);
    if (!b) continue;
    const segs = activeSegs(f, tr.track_id);
    const s = segs.find((x) => S.sel && x.id === S.sel.id) || segs[0];
    const p = s && s.pred;
    const col = p ? (p.abstain ? "#bf8700" : CLASS_COLORS[p.pred_class]) : "#ffffff";
    const x = b[0] * sx, y = b[1] * sy, w = (b[2] - b[0]) * sx, h = (b[3] - b[1]) * sy;
    ctx.strokeStyle = col; ctx.setLineDash(p && p.abstain ? [8, 5] : []); ctx.strokeRect(x, y, w, h); ctx.setLineDash([]);
    const lines = [`track ${tr.track_id.slice(0, 8)}`];
    if (p) lines.push(`${p.abstain ? "⚑ REVIEW " : ""}${p.pred_class} ${fmtPct(p.confidence)}`);
    if (s && s.gt_class) lines.push(`GT ${s.gt_class}`);
    const tw = Math.max(...lines.map((t) => ctx.measureText(t).width)) + 8;
    const ty = Math.max(0, y - 17 * lines.length - 4);
    ctx.fillStyle = "rgba(0,0,0,.72)"; ctx.fillRect(x, ty, tw, 17 * lines.length + 4);
    lines.forEach((t, i) => { ctx.fillStyle = i === 1 && p ? (p.abstain ? "#ffd33d" : "#fff") : "#fff"; ctx.fillText(t, x + 4, ty + 2 + 17 * i); });
  }
  const ph = document.querySelector(".playhead");
  if (ph) {
    const lane = document.querySelector(".lane");
    ph.style.left = (lane.clientWidth * f / Math.max(1, S.data.n_frames - 1)) + "px";
  }
  if ($("loopseg").checked && S.sel && !video.paused && f > S.sel.end_frame) seekFrame(S.sel.start_frame);
  else if (!video.paused) autoPause(f);
}

// ------------------------------------------------------------------ pause-on-review
const needsReview = (s) => !!(s.pred && s.pred.abstain && !S.reviews[s.id] && !S.deferred.has(s.id));

// Pause only when normal playback crosses a flagged segment's start (prev < start <= f); seeks and
// jumps larger than ~0.5 s never trigger, so scrubbing past a segment doesn't pop the drawer.
function autoPause(f) {
  const prev = S.prevF; S.prevF = f;
  if (!$("pausereview").checked || $("rvmodal").open || f <= prev || f - prev > Math.max(2, Math.round(S.data.fps / 2))) return;
  const s = S.segs.find((x) => prev < x.start_frame && x.start_frame <= f && needsReview(x));
  if (s) { video.pause(); openReview(s, true); }
}

function tick() { draw(); if (!video.paused) requestAnimationFrame(tick); }
function togglePlay() { if (video.paused) video.play(); else video.pause(); }
function seekFrame(f) { video.currentTime = (f + 0.5) / S.data.fps; }

// ------------------------------------------------------------------ timeline
function renderTimeline() {
  const tl = $("timeline"); tl.replaceChildren();
  if (!S.data) return;
  const N = Math.max(1, S.data.n_frames - 1);
  const mk = (s, label, colorClass, isPred) => {
    const left = 100 * s.start_frame / N, width = Math.max(0.6, 100 * (s.end_frame - s.start_frame + 1) / N);
    const p = s.pred, rv = S.reviews[s.id];
    const cls = ["seg"]; if (isPred && p && p.abstain) cls.push("abstain"); if (S.sel && S.sel.id === s.id) cls.push("selected");
    const text = `${isPred && p && p.abstain ? "⚑ " : ""}${rv ? "✓ " : ""}${label}`;
    return el("div", { class: cls.join(" "), role: "button", tabindex: "0",
      style: `left:${left}%;width:${width}%;background:${CLASS_COLORS[colorClass] || "#57606a"}`,
      title: `${label} · frames ${s.start_frame}-${s.end_frame}${p ? ` · conf ${fmtPct(p.confidence)}` : ""}`,
      "aria-label": `${isPred ? "Prediction" : "Ground truth"} ${label}, frames ${s.start_frame} to ${s.end_frame}` +
        `${isPred && p && p.abstain ? ", flagged for review" : ""}`,
      onclick: () => select(s, true), onkeydown: (e) => { if (e.key === "Enter") select(s, true); } }, text);
  };
  const lanes = [];
  if (S.data.kind === "val") lanes.push(["GT", S.segs.map((s) => mk(s, s.gt_class, s.gt_class, false))]);
  lanes.push(["Model", S.segs.filter((s) => s.pred).map((s) => mk(s, s.pred.pred_class, s.pred.abstain ? "" : s.pred.pred_class, true))]);
  if (S.data.kind === "upload" && S.data.windows) {
    lanes.push(["Windows", S.data.windows.map((w) => el("div", { class: "seg" + (w.abstain ? " abstain" : ""),
      style: `left:${100 * w.start_frame / N}%;width:${Math.max(.4, 100 * (w.end_frame - w.start_frame + 1) / N)}%;` +
        `height:12px;top:8px;opacity:${w.static ? .25 : .8};background:${w.static ? "#8c959f" : CLASS_COLORS[w.pred_class]}`,
      title: `${w.static ? "static (no activity)" : w.pred_class} ${fmtPct(w.confidence)} motion ${w.motion}` }))]);
  }
  for (const [name, nodes] of lanes) tl.append(el("div", { class: "lane" }, el("span", { class: "lane-label" }, name), ...nodes));
  tl.append(el("div", { class: "playhead" }));
  tl.onclick = (e) => {
    if (e.target.classList.contains("seg")) return;
    const lane = tl.querySelector(".lane").getBoundingClientRect();
    const x = (e.clientX - lane.left) / lane.width;
    if (x >= 0 && x <= 1) seekFrame(Math.round(x * N));
  };
}

function stepSeg(dir, flaggedOnly) {
  const list = S.segs.filter((s) => !flaggedOnly || (s.pred && s.pred.abstain));
  if (!list.length) return;
  const i = S.sel ? list.findIndex((s) => s.id === S.sel.id) : -1;
  let j = i + dir;
  if (i === -1 && flaggedOnly) j = list.findIndex((s) => s.start_frame >= (S.sel ? S.sel.start_frame : 0));
  select(list[(j + list.length) % list.length], true);
}

// ------------------------------------------------------------------ detail + review
function select(s, seek) {
  S.sel = s || null;
  renderTimeline(); renderDetail();
  if (s && seek) { video.pause(); seekFrame(s.start_frame); }
  draw();
}

function renderDetail() {
  const box = $("segdetail"); box.replaceChildren();
  const s = S.sel;
  if (!s) { box.textContent = S.segs.length ? "Select a segment." : "No segments."; return; }
  const p = s.pred;
  const kv = el("div", { class: "kv" },
    el("span", {}, "segment"), el("span", {}, s.id.length > 30 ? "…" + s.id.slice(-14) : s.id),
    el("span", {}, "frames"), el("span", {}, `${s.start_frame}–${s.end_frame} (${((s.end_frame - s.start_frame + 1) / S.data.fps).toFixed(1)} s)`),
    el("span", {}, "track"), el("span", {}, s.track_id));
  if (s.gt_class) kv.append(el("span", {}, "ground truth"), el("span", {}, `${s.gt_class} (${s.raw_label})`),
    el("span", {}, "fold"), el("span", {}, String(s.fold)));
  box.append(kv);
  if (!p) { box.append(el("p", {}, "No prediction.")); return; }
  const status = p.abstain
    ? el("div", { class: "notice" }, el("strong", {}, "⚑ Abstained — needs human review. "),
      p.abstain_reason === "confusable_pair_margin"
        ? `Top two classes are a confusable pair (${p.pred_class} vs ${p.second_class}).`
        : p.abstain_reason === "no_person_track" ? "No person track." : "Calibrated confidence below the operating threshold.")
    : el("div", { class: "small" }, el("span", { class: "badge ok" }, "accepted"), " confidence above threshold");
  box.append(el("h3", {}, "Prediction"), el("div", { style: "font-size:1.1rem;font-weight:600" },
    `${p.pred_class} · ${fmtPct(p.confidence)}`), status);
  if (s.gt_class) box.append(el("div", {}, s.gt_class === p.pred_class
    ? el("span", { class: "badge ok" }, "✓ matches GT") : el("span", { class: "badge bad" }, `✗ GT is ${s.gt_class}`)));
  const probs = el("div", { class: "probs", role: "list", "aria-label": "Calibrated class probabilities" });
  S.classes.map((c, i) => [c, p.probs[i]]).sort((a, b) => b[1] - a[1]).forEach(([c, v]) => {
    probs.append(el("div", { class: "row" + (c === s.gt_class ? " gt" : ""), role: "listitem" },
      el("span", {}, c + (c === s.gt_class ? " (GT)" : "")),
      el("div", { class: "bar" }, el("div", { style: `width:${100 * v}%;background:${CLASS_COLORS[c]}` })),
      el("span", {}, fmtPct(v))));
  });
  box.append(el("h3", {}, "Calibrated probabilities"), probs);

  // review actions
  const rv = S.reviews[s.id];
  const sel = el("select", { id: "corr", "aria-label": "Corrected class" }, ...S.classes.map((c) => el("option", { value: c, selected: c === (s.gt_class || p.second_class) || null }, c)));
  const note = el("input", { id: "note", type: "text", maxlength: "500", placeholder: "note (optional)", "aria-label": "Review note" });
  const send = (action) => postReview(s, action, action === "correct" ? sel.value : null, note.value)
    .catch((e) => box.append(el("div", { class: "notice error" }, e.message)));
  box.append(el("h3", {}, "Review"),
    rv ? el("p", { class: "small" }, `Last: ${rv.action}${rv.corrected_class ? " → " + rv.corrected_class : ""} at ${rv.utc}`) : null,
    el("div", { class: "controls" },
      el("button", { onclick: () => send("confirm"), title: "Prediction is right (c)" }, "✓ Confirm"),
      el("button", { onclick: () => send("reject"), title: "No such activity / bad segment (r)" }, "✗ Reject")),
    el("div", { class: "controls" }, sel, el("button", { onclick: () => send("correct") }, "Correct to…")), note,
    el("div", { class: "controls" }, el("button", { class: "primary", onclick: () => { video.pause(); openReview(s, false); } }, "Open review panel")));
  S.sendReview = send;
}

async function postReview(s, action, correctedClass, note) {
  const body = { source: S.data.kind, ref: S.ref, segment_id: s.id, action, note: note || null, corrected_class: correctedClass };
  const r = await api("api/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  S.reviews[s.id] = r; renderTimeline(); renderDetail();
}

// ------------------------------------------------------------------ review drawer (right side)
function initReviewModal() {
  const d = $("rvmodal");
  d.addEventListener("cancel", (e) => { e.preventDefault(); closeReview(false); });  // Esc: close, stay paused
  $("rv-later").onclick = () => { S.deferred.add(S.rv.seg.id); closeReview(true); };
  $("rv-reject").onclick = () => submitReview("reject");
  $("rv-save").onclick = () => submitReview(S.rv.choice === S.rv.seg.pred.pred_class ? "confirm" : "correct");
  $("rv-opts").onkeydown = (e) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    const items = [...$("rv-opts").children], i = items.indexOf(document.activeElement);
    const n = items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    n.focus(); n.click();
  };
}

function openReview(s, resume) {
  const p = s.pred;
  if (!p) return;
  S.rv = { seg: s, resume, choice: p.pred_class };
  if (!S.sel || S.sel.id !== s.id) select(s, false);
  const secs = (f) => (f / S.data.fps).toFixed(1);
  $("rv-desc").textContent = `${secs(s.start_frame)}–${secs(s.end_frame + 1)} s · frames ${s.start_frame}–${s.end_frame} · ` +
    `model predicted ${p.pred_class} (${fmtPct(p.confidence)})`;
  $("rv-why").replaceChildren(p.abstain ? el("div", { class: "notice" }, el("strong", {}, "⚑ Needs review. "),
    p.abstain_reason === "confusable_pair_margin" ? `Top two classes are a confusable pair (${p.pred_class} vs ${p.second_class}).`
      : p.abstain_reason === "no_person_track" ? "No person track." : "Calibrated confidence below the operating threshold.") : "");
  $("rv-note").value = ""; $("rv-err").hidden = true;
  renderReviewOpts();
  $("rvmodal").showModal();
  $("rv-opts").querySelector('[aria-checked="true"]').focus();
}

function renderReviewOpts() {
  const { seg, choice } = S.rv;
  const ranked = S.classes.map((c, i) => [c, seg.pred.probs[i]]).sort((a, b) => b[1] - a[1]);
  $("rv-opts").replaceChildren(...ranked.map(([c, v]) => el("button", { type: "button", class: "opt", role: "radio",
    "aria-checked": String(c === choice), tabindex: c === choice ? "0" : "-1",
    onclick: () => { S.rv.choice = c; renderReviewOpts(); $("rv-opts").querySelector('[aria-checked="true"]').focus(); } },
    el("span", { class: "dot", style: `background:${CLASS_COLORS[c]}` }),
    el("span", {}, c + (c === seg.pred.pred_class ? "  · predicted" : "")),
    el("span", { class: "small" }, fmtPct(v)),
    el("span", { class: "meter" }, el("div", { style: `width:${100 * v}%` })))));
  $("rv-save").textContent = choice === seg.pred.pred_class ? "✓ Confirm" : `Correct to ${choice}`;
}

async function submitReview(action) {
  const { seg, choice } = S.rv;
  const btns = $("rvmodal").querySelectorAll(".foot button");
  btns.forEach((b) => { b.disabled = true; });
  try {
    await postReview(seg, action, action === "correct" ? choice : null, $("rv-note").value);
    closeReview(true);
  } catch (e) { $("rv-err").textContent = `Save failed: ${e.message}`; $("rv-err").hidden = false; }
  finally { btns.forEach((b) => { b.disabled = false; }); }
}

function closeReview(resume) {
  const d = $("rvmodal");
  if (!d.open) return;
  d.close();
  if (resume && S.rv && S.rv.resume) { S.prevF = curFrame(); video.play(); }
  S.rv = null;
}

function onKey(e) {
  if ($("rvmodal").open) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (e.key === " ") { e.preventDefault(); togglePlay(); }
  else if (e.key === "n") stepSeg(1, false);
  else if (e.key === "p") stepSeg(-1, false);
  else if (e.key === "f") stepSeg(1, true);
  else if (e.key === "c" && S.sendReview) S.sendReview("confirm");
  else if (e.key === "r" && S.sendReview) S.sendReview("reject");
}
