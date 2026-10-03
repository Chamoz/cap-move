// Calibration report: metrics table, reliability diagram, risk–coverage curve, per-pair errors, breakdowns.
const SVGNS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  for (const c of kids) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}

function axes(W, H, m, xl, yl) {
  const g = svg("g");
  g.append(svg("rect", { x: m, y: 10, width: W - m - 10, height: H - m - 10, fill: "#fff", stroke: "#d0d7de" }));
  for (let i = 0; i <= 5; i++) {
    const t = i / 5, x = m + t * (W - m - 10), y = H - m - t * (H - m - 10);
    g.append(svg("text", { x, y: H - m + 14, "font-size": 10, "text-anchor": "middle" }, t.toFixed(1)));
    g.append(svg("text", { x: m - 4, y: y + 3, "font-size": 10, "text-anchor": "end" }, t.toFixed(1)));
    g.append(svg("line", { x1: m, x2: W - 10, y1: y, y2: y, stroke: "#eaeef2" }));
  }
  g.append(svg("text", { x: (W + m) / 2, y: H - 4, "font-size": 11, "text-anchor": "middle" }, xl));
  g.append(svg("text", { x: 12, y: (H - m) / 2, "font-size": 11, "text-anchor": "middle", transform: `rotate(-90 12 ${(H - m) / 2})` }, yl));
  return g;
}

function reliabilitySVG(bins) {
  const W = 360, H = 300, m = 40, sx = (v) => m + v * (W - m - 10), sy = (v) => H - m - v * (H - m - 10);
  const s = svg("svg", { width: W, height: H, role: "img", "aria-label": "Reliability diagram: accuracy versus confidence per bin" });
  s.append(axes(W, H, m, "confidence (max calibrated prob)", "accuracy"));
  s.append(svg("line", { x1: sx(0), y1: sy(0), x2: sx(1), y2: sy(1), stroke: "#8c959f", "stroke-dasharray": "4 3" }));
  const maxn = Math.max(...bins.map((b) => b.n));
  for (const b of bins) {
    if (!b.n) continue;
    const x = sx(b.lo) + 2, w = sx(b.hi) - sx(b.lo) - 4;
    s.append(svg("rect", { x, y: sy(b.acc), width: w, height: sy(0) - sy(b.acc), fill: "#0969da", opacity: .75 },
      svg("title", {}, `conf ${b.lo.toFixed(1)}–${b.hi.toFixed(1)}: n=${b.n}, acc=${b.acc.toFixed(2)}, mean conf=${b.conf.toFixed(2)}`)));
    s.append(svg("rect", { x, y: sy(0) - 18 * b.n / maxn, width: w, height: 18 * b.n / maxn, fill: "#bf8700", opacity: .6 }));
    s.append(svg("circle", { cx: sx(b.conf), cy: sy(b.acc), r: 3, fill: "#cf222e" }));
  }
  return s;
}

function riskCoverageSVG(rc, opCov, opRisk) {
  const W = 360, H = 300, m = 40, sx = (v) => m + v * (W - m - 10), sy = (v) => H - m - v * (H - m - 10);
  const s = svg("svg", { width: W, height: H, role: "img", "aria-label": "Risk–coverage curve" });
  s.append(axes(W, H, m, "coverage (fraction accepted)", "selective risk (error rate)"));
  const d = rc.coverage.map((c, i) => `${i ? "L" : "M"}${sx(c).toFixed(1)},${sy(rc.risk[i]).toFixed(1)}`).join("");
  s.append(svg("path", { d, fill: "none", stroke: "#0969da", "stroke-width": 2 }));
  s.append(svg("line", { x1: sx(0), x2: sx(1), y1: sy(0.2), y2: sy(0.2), stroke: "#cf222e", "stroke-dasharray": "5 3" }));
  s.append(svg("text", { x: sx(1) - 4, y: sy(0.2) - 4, "font-size": 10, "text-anchor": "end", fill: "#cf222e" }, "target risk 0.20"));
  if (opCov !== null && opRisk !== null) s.append(svg("circle", { cx: sx(opCov), cy: sy(opRisk), r: 5, fill: "#bf8700", stroke: "#000" },
    svg("title", {}, `operating point: coverage ${opCov.toFixed(3)}, risk ${opRisk.toFixed(3)}`)));
  return s;
}

function table(head, rows) {
  return el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, ...rows.map((r) => el("tr", {}, ...r.map((c, i) => i ? el("td", {}, c) : el("th", { scope: "row" }, c))))));
}

(async function init() {
  loadFooter();
  const root = document.getElementById("report");
  let R;
  try { R = await api("api/report"); } catch (e) { root.replaceChildren(el("div", { class: "notice error" }, e.message)); return; }
  const o = R.overall;
  const mrow = (name, s) => [name, fmt(s.accuracy), fmt(s.macro_f1), fmt(s.ece), fmt(s.nll), fmt(s.brier), fmt(s.aurc),
    s.coverage === undefined ? "—" : fmt(s.coverage), s.selective_accuracy === undefined ? "—" : fmt(s.selective_accuracy)];
  const rows = [mrow("model (calibrated + abstention)", o)];
  if (R.baseline_uncalibrated_T1) rows.push(mrow("uncalibrated (T = 1)", R.baseline_uncalibrated_T1));
  rows.push(mrow("uniform prior", R.baseline_uniform));
  root.replaceChildren(
    el("h2", {}, `Stage ${R.stage} out-of-fold report — ${R.run_id}`),
    el("p", { class: "small" }, "167 GT segments, oracle boundaries, 5 collector-grouped folds. Primary metrics: AURC ↓ and ECE ↓."),
    table(["run", "Acc", "Macro-F1", "ECE ↓", "NLL ↓", "Brier ↓", "AURC ↓", "Coverage", "Sel. acc"], rows),
    el("div", { style: "display:flex;gap:2rem;flex-wrap:wrap;margin-top:1rem" },
      el("figure", {}, reliabilitySVG(R.reliability), el("figcaption", { class: "small" },
        "Reliability: blue bars = accuracy per confidence bin (dashed = perfect calibration); orange = bin size; red dot = mean confidence.")),
      el("figure", {}, riskCoverageSVG(R.risk_coverage, o.coverage ?? null, o.selective_risk ?? null),
        el("figcaption", { class: "small" }, "Risk–coverage: error rate among the most-confident k segments. Orange dot = operating point."))),
    el("h3", {}, "Confusable pairs"),
    table(["pair", "n", "error rate", "swapped with partner"], Object.entries(o.confusable_pair_error).map(([k, v]) =>
      [k, v.n, fmt(v.error_rate), fmt(v.pair_swap_rate)])),
    el("h3", {}, "Confusion matrix (rows = true, cols = predicted)"),
    table(["true \\ pred", ...R.confusion_matrix.classes], R.confusion_matrix.classes.map((c, i) => [c, ...R.confusion_matrix.rows_true_cols_pred[i]])),
    el("h3", {}, "Operating point per outer fold"),
    table(["fold", "temperature", "threshold"], (R.operating_point.per_fold_threshold || []).map((t, i) =>
      [String(i), fmt(R.operating_point.per_fold_temperature[i]), fmt(t)])),
    ...Object.entries(R.breakdowns).flatMap(([g, d]) => [el("h3", {}, `By ${g}`),
      table(["key", "n", "acc", "mean conf", "coverage", "sel. acc"], Object.entries(d).map(([k, v]) =>
        [k, v.n, fmt(v.accuracy), fmt(v.mean_confidence), fmt(v.coverage), fmt(v.selective_accuracy)]))]));
})();
