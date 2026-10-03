#!/usr/bin/env python3
"""Score predictions.json against the frozen manifest (contract §6).

Usage: python scripts/score.py predictions.json [--detail artifacts/model/oof_detail.json] [--out artifacts/report]
Missing segment => hard failure (exit 2). Writes report.json and report.md.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.model import metrics as M  # noqa: E402
from src.perception.annotations import load_all  # noqa: E402

MANIFEST = "manifests/val_segments.csv"


def device_family(dt):
    return "iOS" if dt.startswith(("iPhone", "iPad")) else "Android"


def fps_bucket(f):
    f = float(f)
    return "<=12" if f <= 12 else ("12-20" if f <= 20 else ">20")


def box_scale_bucket(rows):
    """Mean GT person-box height / frame height over the segment -> small/medium/large."""
    gts = load_all()
    out = {}
    for r in rows:
        tr = gts[r["video_id"]].tracks.get(r["track_id"])
        if tr is None:
            out[r["segment_id"]] = "no_track"
            continue
        b = tr.box_at(np.arange(int(r["start_frame"]), int(r["end_frame"]) + 1))
        s = float(np.mean(b[:, 3] - b[:, 1]) / float(r["frame_height"]))
        out[r["segment_id"]] = "small" if s < 0.33 else ("medium" if s < 0.6 else "large")
    return out


def viewpoint_keys(rows):
    scale = box_scale_bucket(rows)
    return {r["segment_id"]: {"device_family": device_family(r["device_type"]),
                              "resolution": f"{r['frame_width']}x{r['frame_height']}",
                              "fps_bucket": fps_bucket(r["fps"]), "box_scale": scale[r["segment_id"]]}
            for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions")
    ap.add_argument("--detail", default="artifacts/model/oof_detail.json")
    ap.add_argument("--out", default="artifacts/report")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(MANIFEST)))
    pred = json.load(open(args.predictions))
    classes = pred["classes"]
    by_id = {p["segment_id"]: p for p in pred["predictions"]}
    missing = [r["segment_id"] for r in rows if r["segment_id"] not in by_id]
    if missing:
        print(f"HARD FAIL: {len(missing)} manifest segments missing, e.g. {missing[:3]}")
        sys.exit(2)

    y = np.array([classes.index(r["class"]) for r in rows])
    P = np.array([by_id[r["segment_id"]]["probs"] for r in rows])
    A = np.array([by_id[r["segment_id"]]["abstain"] for r in rows])
    yhat = P.argmax(1)
    rep = {"run_id": pred["run"]["run_id"], "stage": pred["run"]["stage"], "overall": M.summary(P, y, A)}

    # baselines
    prior = np.full_like(P, 1.0 / P.shape[1])
    rep["baseline_uniform"] = M.summary(prior, y)
    if args.detail and os.path.exists(args.detail):
        d = json.load(open(args.detail))
        L = np.array([d["uncalibrated_logits"][r["segment_id"]] for r in rows])
        L = L - L.max(1, keepdims=True)
        P1 = np.exp(L) / np.exp(L).sum(1, keepdims=True)
        rep["baseline_uncalibrated_T1"] = M.summary(P1, y)

    # operating point per fold
    rep["operating_point"] = {"per_fold_threshold": pred["run"]["abstention"].get("per_fold_threshold"),
                              "per_fold_temperature": pred["run"]["abstention"].get("per_fold_temperature")}

    # breakdowns
    vp = viewpoint_keys(rows)
    groups = {
        "fold": lambda r: r["fold"], "class": lambda r: r["class"], "confusable_pair": lambda r: r["confusable_pair"],
        "collector": lambda r: r["collector_id"][:8],
        **{k: (lambda kk: (lambda r: vp[r["segment_id"]][kk]))(k)
           for k in ("device_family", "resolution", "fps_bucket", "box_scale")},
    }
    rep["breakdowns"] = {}
    for gname, fn in groups.items():
        idx = defaultdict(list)
        for i, r in enumerate(rows):
            idx[fn(r)].append(i)
        rep["breakdowns"][gname] = {}
        for key, ii in sorted(idx.items()):
            ii = np.array(ii)
            c = yhat[ii] == y[ii]
            acc_mask = ~A[ii]
            rep["breakdowns"][gname][str(key)] = {
                "n": int(len(ii)), "accuracy": float(c.mean()), "mean_confidence": float(P[ii].max(1).mean()),
                "coverage": float(acc_mask.mean()),
                "selective_accuracy": float(c[acc_mask].mean()) if acc_mask.any() else None}
    cm = M.confusion(y, yhat, len(classes))
    rep["confusion_matrix"] = {"classes": classes, "rows_true_cols_pred": cm.tolist()}
    rep["reliability"] = M.reliability(P.max(1), yhat == y)
    cov, risk = M.risk_coverage(P.max(1), yhat == y)
    rep["risk_coverage"] = {"coverage": cov.round(4).tolist(), "risk": risk.round(4).tolist()}

    os.makedirs(args.out, exist_ok=True)
    json.dump(rep, open(os.path.join(args.out, "report.json"), "w"), indent=1)
    md = render_md(rep, classes)
    open(os.path.join(args.out, "report.md"), "w").write(md)
    print(md.split("\n## Breakdowns")[0])


def _f(v, p=3):
    return "—" if v is None else f"{v:.{p}f}"


def render_md(rep, classes):
    o = rep["overall"]
    lines = [f"# Score report — {rep['run_id']} (Stage {rep['stage']})", "",
             "| run | Acc | Macro-F1 | ECE ↓ | NLL ↓ | Brier ↓ | AURC ↓ | Coverage | Sel. acc |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s in (("model (calibrated + abstention)", o),
                    ("uncalibrated (T=1)", rep.get("baseline_uncalibrated_T1")),
                    ("uniform prior", rep["baseline_uniform"])):
        if s is None:
            continue
        lines.append(f"| {name} | {_f(s['accuracy'])} | {_f(s['macro_f1'])} | {_f(s['ece'])} | {_f(s['nll'])} | "
                     f"{_f(s['brier'])} | {_f(s['aurc'])} | {_f(s.get('coverage'))} | {_f(s.get('selective_accuracy'))} |")
    lines += ["", "## Confusable pairs", "", "| pair | n | error rate | swapped with partner |", "|---|---|---|---|"]
    for k, v in o["confusable_pair_error"].items():
        lines.append(f"| {k} | {v['n']} | {_f(v['error_rate'])} | {_f(v['pair_swap_rate'])} |")
    lines += ["", "## Confusion matrix (rows = true)", "",
              "| true \\ pred | " + " | ".join(c[:10] for c in classes) + " |",
              "|---" * (len(classes) + 1) + "|"]
    for c, row in zip(classes, rep["confusion_matrix"]["rows_true_cols_pred"]):
        lines.append(f"| {c} | " + " | ".join(str(v) for v in row) + " |")
    lines += ["", "## Breakdowns"]
    for g, d in rep["breakdowns"].items():
        lines += ["", f"### {g}", "", "| key | n | acc | mean conf | coverage | sel. acc |", "|---|---|---|---|---|---|"]
        for k, v in d.items():
            lines.append(f"| {k} | {v['n']} | {_f(v['accuracy'])} | {_f(v['mean_confidence'])} | "
                         f"{_f(v['coverage'])} | {_f(v['selective_accuracy'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
