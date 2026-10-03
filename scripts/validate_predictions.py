#!/usr/bin/env python3
"""Validate predictions.json against the frozen contract (schema + manifest-level rules).

Usage: python scripts/validate_predictions.py predictions.json
Exit 0 = valid. Exit 1 = violations (printed).
"""
import csv
import hashlib
import json
import sys

import jsonschema

SCHEMA = "configs/predictions.schema.json"
MANIFEST = "manifests/val_segments.csv"


def main(path):
    pred = json.load(open(path))
    schema = json.load(open(SCHEMA))
    errs = [f"schema: {e.json_path}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            .iter_errors(pred)]
    if errs:
        print("\n".join(errs[:50]))
        return 1

    man = {r["segment_id"]: r for r in csv.DictReader(open(MANIFEST))}
    sha = hashlib.sha256(open(MANIFEST, "rb").read()).hexdigest()
    if pred["run"]["manifest_sha256"] != sha:
        errs.append(f"manifest_sha256 mismatch: {pred['run']['manifest_sha256']} != {sha}")

    seen = {}
    classes = pred["classes"]
    for i, p in enumerate(pred["predictions"]):
        sid = p["segment_id"]
        if sid in seen:
            errs.append(f"duplicate segment_id {sid}")
        seen[sid] = p
        if sid not in man:
            errs.append(f"unknown segment_id {sid}")
            continue
        if p["fold"] != int(man[sid]["fold"]):
            errs.append(f"{sid}: fold {p['fold']} != manifest {man[sid]['fold']}")
        s = sum(p["probs"])
        if abs(s - 1) > 1e-4:
            errs.append(f"{sid}: probs sum {s:.6f}")
        m = max(p["probs"])
        if abs(p["confidence"] - m) > 1e-6:
            errs.append(f"{sid}: confidence {p['confidence']} != max(probs) {m}")
        if p["pred_class"] != classes[p["probs"].index(m)]:
            errs.append(f"{sid}: pred_class is not argmax(probs)")
    missing = set(man) - set(seen)
    if missing:
        errs.append(f"{len(missing)} manifest segments missing, e.g. {sorted(missing)[:3]}")

    if errs:
        print("\n".join(errs[:50]))
        return 1
    n_abs = sum(p["abstain"] for p in pred["predictions"])
    print(f"VALID: {len(seen)} segments, stage {pred['run']['stage']}, abstained {n_abs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "predictions.json"))
