# Requirement Verification Questions (round 2)

Round 1 (Q1–Q5) answered 2026-10-03T07:01Z: "confirm as you recommend". Fill in each `[Answer]:` line, or reply in chat. The recommended option is marked ★.

## Q6 — Approve contract v0.1 as FROZEN?
The 8 classes and 4 confusable pairs (`docs/shared-contract.md` §3) and the collector-grouped,
class-stratified folds (167 segments; every class appears in every fold).
A) ★ Approve as is · B) Approve with changes (list them) · C) Different class set
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q7 — Detector / pose weights license
A) ★ Ultralytics YOLO11n + YOLO11n-pose (COCO, AGPL-3.0; fine for an internal prototype, fastest on CPU)
B) torchvision Keypoint R-CNN (BSD; ~5–10× slower on CPU)
C) Other (specify)
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q8 — Abstention operating point
A) ★ Target selective risk ≤ 20% (error on accepted segments); coverage is whatever that yields
B) Fixed coverage (e.g. accept 70%, flag 30%)
C) Other target
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q9 — Upload scope for the demo
A) ★ Any short video (open-world path, marked "experimental, unscored") plus val-video mode with GT comparison as the main demo
B) Val videos only
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q10 — Hosting
A) ★ Local only on 127.0.0.1, no auth (port-forward / code-server proxy for the demo)
B) Needs auth or network exposure (specify)
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q11 — AI-DLC extensions
A) ★ Security baseline (lite) on; resiliency and property-based testing off
B) Enable all · C) Disable all
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")

## Q12 — Stage B
A) ★ Decide after Stage A is demo-ready; I then come back with a cost and time estimate (clip archive 308.7 GB)
B) Rule out Stage B now
[Answer]: A (user, 2026-10-03T07:26Z: "approve all")
