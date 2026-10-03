# CAP Activity Review Tool (prototype)

This is a review tool for activity-recognition output on the confusable CAP activities: sit/stand, pick/put, open/close and don/doff. It shows the person track and box, a GT-vs-model timeline, calibrated class probabilities and abstention flags ("needs review"). Reviewers can Confirm, Correct or Reject each segment. A failure gallery and a calibration report are included.

Data: Consented Activities of People (CAP), Visym Labs, CC BY 4.0, https://registry.opendata.aws/visym-cap/.
This is a local prototype and is not for clinical use.

## Getting started from git

The project lives on a self-hosted Gitea server, reachable over HTTPS through a Cloudflare
tunnel. The clone contains the code, docs, the frozen contract and manifest, `predictions.json`,
the two YOLO weights (AGPL-3.0), the deploy head and the scoring report. It does **not** contain
the CAP media, the feature cache, the gallery thumbnails or the large auto-downloading backbones
(contract §2.3 — pixels never leave the host).

### 1. Access and clone
Each teammate has their own Gitea account (`ice`, `pok`, `donut`). Git over HTTPS uses a
**personal access token** as the password — that token is your identity, so there is no
interactive login for day-to-day git. Get your token once:

1. Open the Gitea web UI (the tunnel URL you were given) and sign in with your username and
   first-login password. **Changing that password is recommended but not required** — do it under
   *Settings → Account* if you want to.
2. Go to *Settings → Applications → Generate New Token*, scope `repo` (read/write), and copy it.
3. Clone with your username and the token as the password:

```bash
git clone https://<tunnel-host>/gr11/cap-position.git
# username: your Gitea user (e.g. ice);  password: your personal access token
cd cap-position
# optional: cache the token for this repo
git config credential.helper store   # stores in ~/.git-credentials (plaintext) — your call
```

`main` is protected: no direct pushes and no force-push. Work on a branch and open a pull request.

### 2. Environment (Python 3.9)
```bash
# uv is recommended; python -m venv also works
uv venv --python 3.9 .venv
. .venv/bin/activate
pip install -r requirements.lock.txt     # CPU torch wheels; do NOT install GUI opencv-python
```

### 3. Get the data (not in git)
The CAP validation set is required — `src/app/server.py` loads it on import, so even the tests
need it. Download `cap_detection_handheld_val` from https://visym.github.io/cap (verify the MD5)
into `data/cap_detection_handheld_val/`. Only use it inside an approved environment (contract §2.3).

### 4. Weights
`weights/yolo11n.pt` and `weights/yolo11n-pose.pt` ship in the clone (AGPL-3.0; see `docs/weights.md`).
CLIP ViT-B/32 and R(2+1)D-18 are **not** in git — they auto-download on first use; check the
sha256s in `docs/weights.md`.

### 5. Rebuild the excluded artifacts (in order)
The feature cache, gallery thumbnails and (optionally) a fresh `predictions.json` are rebuilt from
the data:
```bash
.venv/bin/python scripts/extract_features.py       # ~11 min
.venv/bin/python scripts/extract_clip.py           # ~3 min
.venv/bin/python scripts/train_oof.py              # ~4 min -> predictions.json
.venv/bin/python scripts/validate_predictions.py predictions.json
.venv/bin/python scripts/score.py predictions.json
.venv/bin/python scripts/build_gallery.py          # ~1.5 min (thumbnails stay local, git-ignored)
```

### 6. Run the server
Without auth (local only):
```bash
.venv/bin/python -m src.app.server      # http://127.0.0.1:8000
```
With HTTP Basic auth (contract v0.2, for an authenticated tunnel) — credentials come from env vars
and are never committed or logged:
```bash
CAP_AUTH_USER='<user>' CAP_AUTH_PASS='<pass>' .venv/bin/python -m src.app.server
```

## Run

```bash
cd /Workshop/cap-position
# one-time: pinned deps are in requirements.lock.txt (CPU torch from https://download.pytorch.org/whl/cpu)
.venv/bin/python scripts/build_manifest.py              # frozen manifest; prints sha256 66181cb2…f321
.venv/bin/python scripts/extract_features.py            # U2: pose + R(2+1)D on GT crops   (~11 min, 4 vCPU)
.venv/bin/python scripts/extract_clip.py                # U2b: CLIP state features          (~3 min)
.venv/bin/python scripts/train_oof.py                   # U3: nested OOF -> predictions.json (~4 min)
.venv/bin/python scripts/validate_predictions.py predictions.json
.venv/bin/python scripts/score.py predictions.json      # -> artifacts/report/report.{json,md}
.venv/bin/python scripts/build_gallery.py               # -> artifacts/gallery/ (thumbnails stay local)
.venv/bin/python -m src.app.server                      # http://127.0.0.1:8000 (open via port-forward / code-server proxy)
.venv/bin/python -m pytest -q tests                     # 24 tests
```

Pages:
- `/` review player, with Val videos and Upload tabs. Keys: space play/pause, n/p next/previous segment, f next flagged, c confirm, r reject.
- `/gallery` failure gallery. Filter by outcome, pair, class, collector, fold, device, resolution, fps and person scale.
- `/report` metrics table, reliability diagram, risk–coverage curve, per-pair errors and breakdowns.

Review actions are appended to `artifacts/reviews.jsonl` and exported at `/api/reviews/export`.

## Method (Stage A, val file only)
- The frozen contract is `docs/shared-contract.md` v0.1: 8 classes, 4 confusable pairs, 167 GT segments, and 5 folds grouped by collector.
- Features come from frozen pretrained models on the GT person track (`docs/weights.md`):
  - CLIP ViT-B/32 embeddings and state-prompt similarities at the segment start and end, plus their change. The pairs are time reversals of each other, so the before/after state is what separates them.
  - YOLO11n-pose keypoint statistics, normalised to the box.
  - R(2+1)D-18 clip embeddings, offered as a candidate feature set.
- The head is L2 logistic regression. Per outer fold k, an inner leave-one-fold-out over the other 4 folds selects:
  - the feature set, C, and the time-reversal augmentation weight (a reversed segment is labelled as its pair partner), all by NLL;
  - the temperature;
  - the abstention threshold τ, chosen as the maximum coverage at which inner selective risk is ≤ 20%.

  Fold k is never used for its own predictions, and `tests/test_model.py::test_oof_never_uses_test_fold` checks this.
- Abstain reasons are `confusable_pair_margin` (the top two classes are a pair), `low_confidence` and `no_person_track`.

## Results — `predictions.json` (out-of-fold, 167 segments)

| run | Acc | Macro-F1 | ECE ↓ | NLL ↓ | AURC ↓ | Coverage | Sel. acc |
|---|---|---|---|---|---|---|---|
| model (calibrated + abstention) | 0.437 | 0.433 | 0.096 | 1.552 | 0.467 | 0.102 | 0.471 |
| uncalibrated (T = 1) | 0.437 | 0.433 | 0.110 | 1.546 | 0.466 | — | — |
| uniform prior | 0.078 | 0.018 | 0.047 | 2.079 | 0.919 | — | — |

Error rate per pair: posture 0.18, pick/put 0.52, open/close 0.59, don/doff 0.88. The full report is in `artifacts/report/report.md`.

Limitations:
- **The 20% selective-risk target is not met out of fold.** Thresholds chosen on inner folds accept 10% of segments, and those still carry 53% error. With 167 segments (9–42 per class) the head is data-starved, so the honest operating mode is "flag almost everything". Of the 94 OOF errors, 9 are silent: wrong and not flagged.
- Temperature scaling barely moves anything (T ≈ 0.86–0.98), so the regularised head was already close to calibrated.
- Upload mode is open-world and experimental: windows of 2.4 s with a 1.2 s stride, plus a pose-motion gate. The head never saw "no activity" and never saw predicted boundaries, so expect false segments. This path is not scored.
- More training data (Stage B) is the main lever. Stage B needs a cost estimate and approval (contract §7).

## Data rules (contract §2)
- Subjects appear only as `collector_id[:8]`.
- `subject_ids`, `ipAddress` and `device_identifier` are never read. A grep over `artifacts/`, `predictions.json`, `web/` and `manifests/` finds none of them, and `tests/test_app.py` checks the API payloads.
- Media and thumbnails stay on this host and are git-ignored.
- Uploads are deleted after processing; only a 480 px playback proxy and the numeric results are kept.

## Security (security-baseline lite)
- The server binds to 127.0.0.1 only and has **no authentication**. Don't expose it beyond a local port-forward.
- Videos and jobs are looked up by ID; the client never supplies a filesystem path.
- Other protections:
  - strict ID regexes;
  - uploads limited to 200 MB, 90 s and a video-extension allow-list;
  - CSP, `nosniff` and `no-referrer` headers;
  - review payloads validated against enums;
  - Ultralytics telemetry sync disabled.
