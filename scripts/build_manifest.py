#!/usr/bin/env python3
"""Build manifests/val_segments.csv from the CAP val vipy JSON annotations.

Deterministic: same input -> byte-identical output. Implements contract §3 (classes),
§4 (segment identity) and §5 (5-fold split grouped by collector_id).
Writes NO personal attributes (subject_ids, ipAddress, device_identifier are dropped).
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

# Contract §3: raw CAP label -> contract class. Order defines class index.
CLASSES = [
    "sit_down", "stand_up",
    "pick_up_object", "put_down_object",
    "open", "close",
    "put_on_wearable", "take_off_wearable",
]
CONFUSABLE_PAIRS = {
    "sit_down": "posture", "stand_up": "posture",
    "pick_up_object": "pick_vs_put", "put_down_object": "pick_vs_put",
    "open": "open_vs_close", "close": "open_vs_close",
    "put_on_wearable": "don_vs_doff", "take_off_wearable": "don_vs_doff",
}


def map_label(raw):
    if raw == "person_sits_down":
        return "sit_down"
    if raw in ("person_stands_up", "person_stands_up_from_floor"):
        return "stand_up"
    if raw.startswith("person_picks_up_object_from_"):
        return "pick_up_object"
    if raw.startswith("person_puts_down_object_on_"):
        return "put_down_object"
    if raw.startswith("person_opens_"):
        return "open"
    if raw.startswith("person_closes_"):
        return "close"
    if raw.startswith("person_puts_on_"):
        return "put_on_wearable"
    if raw.startswith("person_takes_off_"):
        return "take_off_wearable"
    return None


SEED = 20261003
TRIALS = 20000


def assign_folds(class_counts_by_collector, k=5):
    """Stratified GroupKFold by search: every collector is in exactly one fold.
    Tries TRIALS seeded random group orderings, greedily placing each collector in the
    fold that minimises imbalance, and keeps the assignment with the lowest cost
    (sum over class of squared deviation from the per-fold target, plus fold-size term).
    Fully deterministic given SEED and the sorted collector list."""
    import random
    cols = sorted(class_counts_by_collector)
    total = Counter()
    for c in cols:
        total.update(class_counts_by_collector[c])
    n_total = sum(total.values())

    def cost(loads):
        s = 0.0
        for cls in CLASSES:
            t = total[cls] / k
            s += sum((l[cls] - t) ** 2 for l in loads) / max(t, 1e-9)
        sizes = [sum(l.values()) for l in loads]
        s += sum((z - n_total / k) ** 2 for z in sizes) / (n_total / k)
        return s

    rng = random.Random(SEED)
    best, best_cost = None, float("inf")
    for _ in range(TRIALS):
        order = cols[:]
        rng.shuffle(order)
        loads = [Counter() for _ in range(k)]
        fold_of = {}
        for c in order:
            cc = class_counts_by_collector[c]
            def trial(i):
                loads[i].update(cc)
                v = cost(loads)
                loads[i].subtract(cc)
                return (v, i)
            f = min(trial(i) for i in range(k))[1]
            loads[f].update(cc)
            fold_of[c] = f
        v = cost(loads)
        if v < best_cost:
            best, best_cost = dict(fold_of), v
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cap_detection_handheld_val")
    ap.add_argument("--out", default="manifests/val_segments.csv")
    args = ap.parse_args()

    rows = []
    for path in sorted(glob.glob(os.path.join(args.data, "annotations", "*.json"))):
        for scene in json.load(open(path)):
            v = next(iter(scene.values()))
            a = v["attributes"]
            video_rel = os.path.normpath(os.path.join("annotations", v["filename"]))
            for act in v["activities"].values():
                cls = map_label(act["label"])
                if cls is None:
                    continue
                rows.append({
                    "segment_id": f"{a['video_id']}__{act['id']}",
                    "video_id": a["video_id"],
                    "video_path": video_rel,
                    "collector_id": a["collector_id"],
                    "collection_name": a["collection_name"],
                    "raw_label": act["label"],
                    "class": cls,
                    "confusable_pair": CONFUSABLE_PAIRS[cls],
                    "track_id": act["actorid"],
                    "start_frame": act["startframe"],
                    "end_frame": act["endframe"],
                    "fps": round(float(v["framerate"]), 4),
                    "frame_width": a["frame_width"],
                    "frame_height": a["frame_height"],
                    "device_type": a["device_type"],
                })

    ids = Counter(r["segment_id"] for r in rows)
    dup = [s for s, c in ids.items() if c > 1]
    if dup:
        sys.exit(f"duplicate segment_id: {dup[:5]}")

    per_collector = Counter(r["collector_id"] for r in rows)
    cls_by_collector = defaultdict(Counter)
    for r in rows:
        cls_by_collector[r["collector_id"]][r["class"]] += 1
    fold_of = assign_folds(cls_by_collector)
    for r in rows:
        r["fold"] = fold_of[r["collector_id"]]
    rows.sort(key=lambda r: (r["fold"], r["video_id"], r["start_frame"], r["segment_id"]))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    cols = ["segment_id", "fold", "class", "confusable_pair", "raw_label", "video_id", "video_path",
            "collector_id", "collection_name", "track_id", "start_frame", "end_frame", "fps",
            "frame_width", "frame_height", "device_type"]
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    # Summary to stderr (no personal data)
    by_fold = defaultdict(Counter)
    for r in rows:
        by_fold[r["fold"]][r["class"]] += 1
    print(f"segments={len(rows)} videos={len(set(r['video_id'] for r in rows))} "
          f"collectors={len(per_collector)}", file=sys.stderr)
    print("fold " + " ".join(f"{c[:12]:>12}" for c in CLASSES) + "  total collectors", file=sys.stderr)
    for f in range(5):
        n_col = sum(1 for c in fold_of if fold_of[c] == f)
        print(f"{f:>4} " + " ".join(f"{by_fold[f][c]:>12}" for c in CLASSES)
              + f"  {sum(by_fold[f].values()):>5} {n_col:>10}", file=sys.stderr)
    print("sha256=" + hashlib.sha256(open(args.out, "rb").read()).hexdigest(), file=sys.stderr)


if __name__ == "__main__":
    main()
