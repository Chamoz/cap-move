// Failure gallery: filter OOF predictions by outcome, confusable pair, class, collector and viewpoint proxy.
const FILTERS = [
  ["category", "Outcome"], ["confusable_pair", "Confusable pair"], ["gt_class", "True class"], ["pred_class", "Predicted"],
  ["abstain_reason", "Abstain reason"], ["collector", "Collector"], ["fold", "Fold"], ["device_family", "Device"],
  ["resolution", "Resolution"], ["fps_bucket", "FPS"], ["box_scale", "Person scale"],
];
const CAT_LABEL = { silent_error: "✗ silent error", caught_error: "⚑ caught error", over_cautious: "⚑ over-cautious", correct: "✓ correct" };
const CAT_BADGE = { silent_error: "bad", caught_error: "flag", over_cautious: "flag", correct: "ok" };
let ITEMS = [];

(async function init() {
  loadFooter();
  try { ITEMS = (await api("api/gallery")).items; } catch (e) {
    document.getElementById("grid").replaceChildren(el("div", { class: "notice error" }, e.message)); return;
  }
  const box = document.getElementById("filters");
  const params = new URLSearchParams(location.search);
  for (const [key, label] of FILTERS) {
    const vals = [...new Set(ITEMS.map((it) => String(it[key])))].sort();
    const sel = el("select", { id: "f-" + key, onchange: render },
      el("option", { value: "" }, "all"), ...vals.map((v) => el("option", { value: v, selected: params.get(key) === v || null },
        `${key === "category" ? CAT_LABEL[v] || v : v} (${ITEMS.filter((it) => String(it[key]) === v).length})`)));
    box.append(el("label", { for: "f-" + key }, label, sel));
  }
  const sort = el("select", { id: "sort", onchange: render },
    el("option", { value: "conf_desc" }, "confidence ↓ (confident mistakes first)"),
    el("option", { value: "conf_asc" }, "confidence ↑"), el("option", { value: "gtprob_asc" }, "P(true class) ↑"));
  box.append(el("label", { for: "sort" }, "Sort", sort));
  const wrongOnly = el("input", { type: "checkbox", id: "wrongonly", onchange: render, checked: !params.has("all") || null });
  box.append(el("label", { for: "wrongonly" }, "Errors only", wrongOnly));
  render();
})();

function render() {
  let xs = ITEMS.filter((it) => FILTERS.every(([k]) => {
    const v = document.getElementById("f-" + k).value; return !v || String(it[k]) === v;
  }));
  if (document.getElementById("wrongonly").checked) xs = xs.filter((it) => it.wrong);
  const s = document.getElementById("sort").value;
  xs.sort((a, b) => s === "conf_desc" ? b.confidence - a.confidence : s === "conf_asc" ? a.confidence - b.confidence : a.gt_prob - b.gt_prob);
  const n = xs.length, nw = xs.filter((x) => x.wrong).length, nab = xs.filter((x) => x.abstain).length;
  document.getElementById("count").textContent = `${n} segment(s) · ${nw} wrong · ${nab} flagged`;
  const grid = document.getElementById("grid");
  grid.replaceChildren(...xs.map((it) => el("article", { class: "card" },
    el("a", { href: `./?video=${encodeURIComponent(it.video_id)}&segment=${encodeURIComponent(it.segment_id)}`,
      "aria-label": `Open segment: true ${it.gt_class}, predicted ${it.pred_class}` },
      el("img", { src: `thumbs/${encodeURIComponent(it.segment_id)}.jpg`, alt: `4 frames of the ${it.gt_class} segment`, loading: "lazy" })),
    el("div", {}, el("span", { class: "badge " + CAT_BADGE[it.category] }, CAT_LABEL[it.category]),
      it.pair_swap ? el("span", { class: "badge bad", style: "margin-left:4px" }, "pair swap") : null),
    el("div", {}, el("b", {}, "GT "), it.gt_class, " ", el("span", { class: "small" }, `(${it.raw_label.replace("person_", "")})`)),
    el("div", {}, el("b", {}, "Pred "), `${it.pred_class} ${fmtPct(it.confidence)}`, el("span", { class: "small" }, ` · P(GT) ${fmtPct(it.gt_prob)}`)),
    el("div", { class: "small" }, it.abstain ? `flag: ${it.abstain_reason}` : "accepted", ` · 2nd ${it.second_class}`),
    el("div", { class: "small" }, `${it.collection_name} · collector ${it.collector} · fold ${it.fold}`),
    el("div", { class: "small" }, `${it.device_family} · ${it.resolution} · ${it.fps_bucket} fps · ${it.box_scale} person · ${it.duration_s}s`))));
}
