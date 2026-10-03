#!/usr/bin/env python3
"""U3: nested out-of-fold head + temperature + abstention -> predictions.json (Stage A).

Also writes artifacts/model/oof_detail.json (per-fold C/T/tau, uncalibrated logits for the
T=1 baseline) and artifacts/model/deploy.pkl (all-val model used by the review tool; NOT scored).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.model import head as H  # noqa: E402
from src.model.features import FEATURE_SETS, REVERSIBLE, all_blocks, reversed_blocks, stack  # noqa: E402

MANIFEST = "manifests/val_segments.csv"


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="artifacts/features/segments.npz")
    ap.add_argument("--clip", default="artifacts/features/clip.npz")
    ap.add_argument("--sets", default=",".join(FEATURE_SETS), help="candidate feature sets (chosen in inner CV)")
    ap.add_argument("--target-risk", type=float, default=0.20)
    ap.add_argument("--out", default="predictions.json")
    ap.add_argument("--model-dir", default="artifacts/model")
    ap.add_argument("--no-deploy", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(MANIFEST)))
    z = np.load(args.features)
    zc = np.load(args.clip)
    ids = [r["segment_id"] for r in rows]
    assert list(z["segment_id"]) == ids and list(zc["segment_id"]) == ids, "feature cache out of manifest order"
    blocks = all_blocks(z, zc)
    set_names = args.sets.split(",")
    rblocks = reversed_blocks(z, zc)
    X = {n: (stack(blocks, FEATURE_SETS[n]),
             stack(rblocks, FEATURE_SETS[n]) if set(FEATURE_SETS[n]) <= REVERSIBLE else None) for n in set_names}
    y = np.array([H.CLASSES.index(r["class"]) for r in rows])
    folds = np.array([int(r["fold"]) for r in rows])
    has_track = z["has_track"]

    results = H.run_oof(X, y, folds, args.target_risk)
    probs = np.zeros((len(y), H.K))
    logits = np.zeros((len(y), H.K))
    for fr in results:
        probs[fr.test_idx] = fr.probs
        logits[fr.test_idx] = fr.logits

    preds = []
    for i, r in enumerate(rows):
        p = probs[i] / probs[i].sum()
        tau = results[folds[i]].threshold
        ab, reason, second = H.abstain_decision(p, tau)
        if not has_track[i]:
            ab, reason = True, "no_person_track"
        e = {"segment_id": r["segment_id"], "fold": int(folds[i]), "pred_class": H.CLASSES[int(p.argmax())],
             "probs": [round(float(v), 6) for v in p], "confidence": round(float(p.max()), 6),
             "abstain": bool(ab), "second_class": H.CLASSES[second]}
        # re-normalise after rounding so the sum stays within 1e-4
        s = sum(e["probs"])
        e["probs"][int(p.argmax())] = round(e["probs"][int(p.argmax())] + (1 - s), 6)
        e["confidence"] = max(e["probs"])
        if ab:
            e["abstain_reason"] = reason
        preds.append(e)

    os.makedirs(args.model_dir, exist_ok=True)
    detail = {"candidate_sets": {n: FEATURE_SETS[n] for n in set_names}, "target_risk": args.target_risk,
              "folds": [{"fold": fr.fold, "feature_set": fr.feature_set, "aug_weight": fr.aug_weight, "C": fr.C, "temperature": fr.temperature,
                         "threshold": fr.threshold}
                        for fr in results],
              "uncalibrated_logits": {r["segment_id"]: [round(float(v), 5) for v in logits[i]]
                                      for i, r in enumerate(rows)}}
    json.dump(detail, open(os.path.join(args.model_dir, "oof_detail.json"), "w"))

    meta = json.load(open(os.path.join(os.path.dirname(args.features), "meta.json")))
    from src.perception.models import weights_manifest
    weights = weights_manifest()
    head_files = []
    if not args.no_deploy:
        model, fs, C, w, T, tau = H.fit_deploy(X, y, folds, args.target_risk)
        dp = os.path.join(args.model_dir, "deploy.pkl")
        pickle.dump({"model": model, "feature_set": fs, "blocks": FEATURE_SETS[fs], "C": C, "aug_weight": w, "temperature": T,
                     "threshold": tau, "classes": H.CLASSES}, open(dp, "wb"))
        head_files.append(dp)
        print(f"deploy model: set={fs} aug={w} C={C} T={T:.3f} tau={tau:.3f}")
    # The scored heads are refit deterministically inside run_oof; record the code+feature hash as identity.
    head_id = hashlib.sha256((sha256(args.features) + sha256(args.clip) + sha256(H.__file__) + args.sets).encode()).hexdigest()
    weights.append({"name": "oof_logreg_heads_x5", "source": "trained in-repo by scripts/train_oof.py (nested OOF)",
                    "sha256": head_id, "role": "classifier_head", "license": "project-internal"})

    out = {"contract_version": "0.1", "classes": H.CLASSES, "run": {
        "run_id": "stageA-" + dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"), "stage": "A",
        "created_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "manifest_sha256": sha256(MANIFEST), "out_of_fold": True, "weights": weights,
        "abstention": {"method": f"max-prob threshold on temperature-scaled probs; per outer fold, chosen on "
                                 f"inner leave-one-fold-out OOF for selective risk <= {args.target_risk}",
                       "per_fold_threshold": [round(fr.threshold, 6) for fr in results],
                       "per_fold_temperature": [round(fr.temperature, 6) for fr in results]},
        "notes": f"frozen features on GT track crops: CLIP ViT-B/32 start/end state embeddings + prompt sims, "
                 f"YOLO11n-pose keypoint stats, R(2+1)D-18 clip embeddings; L2 logistic regression; feature set "
                 f"{set_names}, C {list(H.C_GRID)} and time-reversal augmentation weight {list(H.AUG_WEIGHTS)} "
                 f"(reversed segment labelled as pair partner) chosen per outer fold by inner-OOF NLL; per-fold: "
                 f"{[(fr.feature_set, fr.aug_weight, fr.C) for fr in results]}"},
        "predictions": preds}
    json.dump(out, open(args.out, "w"), indent=1)
    acc = (probs.argmax(1) == y).mean()
    cov = np.mean([not p["abstain"] for p in preds])
    sel = np.mean([p["pred_class"] == rows[i]["class"] for i, p in enumerate(preds) if not p["abstain"]] or [0])
    print(f"OOF acc={acc:.3f} coverage={cov:.3f} selective_acc={sel:.3f} -> {args.out}")
    for fr in results:
        print(f"  fold {fr.fold}: set={fr.feature_set} aug={fr.aug_weight} C={fr.C} T={fr.temperature:.3f} tau={fr.threshold:.3f}")


if __name__ == "__main__":
    main()
