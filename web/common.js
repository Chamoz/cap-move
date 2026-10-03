// Shared helpers (no external libraries).
const CLASS_COLORS = {
  sit_down: "#0550ae", stand_up: "#54aeff",
  pick_up_object: "#116329", put_down_object: "#4ac26b",
  open: "#8a4600", close: "#d4a72c",
  put_on_wearable: "#8250df", take_off_wearable: "#c297ff",
};
const PAIR_OF = { sit_down: "posture", stand_up: "posture", pick_up_object: "pick_vs_put", put_down_object: "pick_vs_put",
  open: "open_vs_close", close: "open_vs_close", put_on_wearable: "don_vs_doff", take_off_wearable: "don_vs_doff" };

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(`${r.status}: ${msg}`);
  }
  return r.json();
}

// Build DOM nodes without innerHTML for any data-derived text.
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined) n.append(c instanceof Node ? c : String(c));
  return n;
}

function fmtPct(x) { return x === null || x === undefined ? "—" : (100 * x).toFixed(1) + "%"; }
function fmt(x, d = 3) { return x === null || x === undefined ? "—" : Number(x).toFixed(d); }

async function loadFooter() {
  try {
    const info = await api("api/info");
    const f = document.getElementById("attr");
    if (f) f.textContent = `Data: ${info.attribution}. Subjects referred to by collector id only. Local prototype — not for clinical use.`;
    const ri = document.getElementById("runinfo");
    if (ri && info.run && info.run.run_id) ri.textContent = `run ${info.run.run_id} (Stage ${info.run.stage}, out-of-fold)`;
    return info;
  } catch (e) { return null; }
}
