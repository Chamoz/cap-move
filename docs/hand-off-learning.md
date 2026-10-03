# Hand-off Note — 2026-10-03T11:10Z

Project: CAP Activity Review Tool · Workspace: `/Workshop/cap-position` · Method: AI-DLC
Deadline: review tool demo-ready on **2026-10-04** (event Day 2).
Contract: **v0.2** (`docs/shared-contract.md`). Full history: `aidlc-docs/audit.md`.

## Start here: Stage B is CLOSED — not pursued (user decision 2026-10-03T12:20Z)
**Do not restart Stage B on the clip archive.** The user chose to abandon it and keep Stage A (v1) as the demo, because `cap_classification_clip.tar.gz` has **no recoverable per-clip `collector_id`**, so the mandatory val-collector exclusion (contract §7) can't be guaranteed. The ~6–9 h download was never started; `data/stageB_v2/` is empty; investigation artifacts (`artifacts/v2/`) were removed. Evidence of the metadata finding: `aidlc-docs/audit.md` 11:16Z; decision: 12:20Z.

**The demo is v1** (`predictions.json`, run `stageA-20261003T081316Z`), with its documented limitation (OOF selective risk 0.53 vs the 20% target). Remaining open items are unchanged (see "Other open items"): the user's browser webcam check, live-stream Phase 2 (gated), and rotating the share password after the event. If the user ever revisits more data, the only untested lead is `cap_classification_pad.tar.gz` — but it needs the same `collector_id` metadata peek first, and the same §7 hard-stop applies.

### (Superseded) metadata investigation that led here
A bounded, read-only metadata investigation (chosen over an immediate full pass) proved there is **no recoverable per-clip `collector_id`** in `cap_classification_clip.tar.gz`. Evidence in `aidlc-docs/audit.md` (2026-10-03T11:16Z):
- Bucket has only `train/` (the two archives); no sidecar manifest. Root/`annotations`/`meta` listings are AccessDenied.
- Archive members (2 GB head, 6,101) are mp4 + directories only — no JSON/CSV. tar owner is a constant uid, not per-clip.
- mp4 metadata (171 clips scanned then deleted) carries only `©too=Lavf58.29.100`; ffmpeg re-encode stripped device/collector info. No collector/subject/device strings.
- Clip filenames are UUIDv4 (random): nothing derivable, zero overlap with val `video_id`/`collector_id`, absent from val JSON.

**Resolved 2026-10-03T12:20Z**: the user chose **(a)** — abandon Stage B, keep v1 as the demo. (Alternatives were (b) peek `cap_classification_pad.tar.gz`; (c) amend §7 to accept leakage risk.) Investigation artifacts (incl. `artifacts/v2/peek_members.txt`) have since been removed; `data/stageB_v2/` is empty.

### (Superseded) original approval, for reference
Approved by the user 2026-10-03T11:09Z (contract §7 cost gate passed):
| Decision | Value |
|---|---|
| Archive | `s3://consented-activities-of-people/train/cap_classification_clip.tar.gz` (308,736,485,473 B, us-west-2, `--no-sign-request`) |
| Full streaming pass | Approved. Estimate ~6–9 h total, a few USD |
| Subsample | **500 clips per class** (≤ 4,000) |
| Storage | **Host only**: `data/stageB_v2/` (git-ignored under `data/`). No S3 bucket. Never `cdk-hnb659fds-assets-*` |
| Output | Separate run `v2`, `run.stage="B"`. **v1 (Stage A) stays untouched and stays the demo.** |

### Archive facts (from a 200 MB peek, already deleted)
- Layout: `cap_classification_clip/videos/<raw_label>/<UUID>_0.mp4`, ~315 KB per clip → ~0.96M clips.
  Clips are ~2.3 s at 512×910. Label folders are **not** in alphabetical order, so the whole archive must be streamed.
- Speed: 29 MB/s single stream. Decompression runs at 160 MB/s, so the network is the bottleneck. Inbound transfer should cost ~$0 (public open-data bucket, not requester-pays).
- **Risk: no annotation JSON was found in the first 200 MB.** File names are clip UUIDs only.
  Excluding the 32 val collectors is mandatory (§7). **If no per-clip `collector_id` turns up, STOP before training and report to the user.** Don't fall back to anything weaker.

### Plan for the next session
1. Re-check the live state (commands in "Server & tunnel"). Then append the user's first message to `audit.md`.
2. Write `scripts/stageB_stream.py`, which streams `curl … | tar -xz` style, without staging the archive:
   - Keep only raw labels that map to the 8 classes. Reuse `map_label()` from `scripts/build_manifest.py`.
   - Also keep **every non-mp4 member** (JSON/CSV), since that's where collector metadata would be. Log member names as they arrive.
   - Disk guard: abort if free space drops below ~10 GB. 8-class clips are estimated at 15–45 GB (unverified), and 68 GB is free now.
   - Run detached: `setsid nohup … > artifacts/v2/stream.log 2>&1 &`, with the pid in `artifacts/v2/stream.pid`. **Never use `pkill -f`.**
   - Make it resumable, or at least idempotent on re-run.
3. Collector gate: join clips to `collector_id`. Drop every clip from the 32 val collectors (list from `manifests/val_segments.csv` plus the val JSONs). Never read `subject_ids`, `ipAddress` or `device_identifier`.
4. Subsample up to 500 per class, balanced across collectors. Use a fixed seed (20261003) and write `manifests/stageB_v2_clips.csv`.
5. Features in `scripts/extract_features_v2.py`, writing to `artifacts/v2/features/`. These clips have no GT boxes, so use the YOLO person box (largest, highest-confidence). Compute pose and CLIP state with the same code as Stage A. R(2+1)D can be skipped (the deploy head uses `state+pose`), but keep the `FEATURE_SETS` contract.
   - **Time the first ~50 clips and send the user a revised ETA.** The estimate assumed ~4–5 s per clip.
6. Train the v2 head on the trainval features. Anything fitted on val (temperature, τ, hyperparameter selection) must stay **out-of-fold over the val folds**, with the same rule and leakage test as Stage A. Outputs:
   - `predictions_v2.json` (`run.stage="B"`, all weights listed)
   - `artifacts/v2/model/deploy_v2.pkl`
   - `artifacts/v2/report/`

   Then run `validate_predictions.py` and `score.py`, and compare against Stage A.
7. Keep the server on v1. Only show v2 if the user asks (`CAP_PREDICTIONS=predictions_v2.json`, plus a separate deploy path).
8. Delete `data/stageB_v2/` raw clips only when the user says so.

## Other open items
1. **Live-stream Phase 2 (near-live rolling inference): GATED.** Don't start it without the user's go-ahead. The host runs ~3× slower than real time (~5–6 s per 2.4 s window), so expect ~5 s latency.
2. **Browser check by the user**: webcam device picker, then record → stop → analyse. A Stop-button bug (the click event was passed in as `silent`) was fixed at 09:18Z. The user hasn't confirmed it works yet.
3. **Rotate the share password** after the event. It was sent in plaintext in chat.
4. Optional: the user may want CLIP and R(2+1)D removed (see the deviation in `audit.md`).

## Server & tunnel (live at 11:10Z)
- Server: `127.0.0.1:8000`, pid in `artifacts/server.pid` (231331), log `artifacts/server.log`.
  Running **with** HTTP Basic auth: user `gr11`, password from the user. **Never write the password to a file.**
- Public URL: `https://prep-karma-raleigh-created.trycloudflare.com`. It's a cloudflared quick tunnel (`/tmp/cloudflared`, pid in `artifacts/tunnel.pid`, log `artifacts/tunnel.log`). It's ephemeral: the URL changes if cloudflared restarts.
- Code-server proxy (owner only, needs code-server login): `https://d2wxa2we707rwy.cloudfront.net/proxy/8000/`. Keep all web URLs **relative**.
- Check:
  ```
  kill -0 $(cat artifacts/server.pid) && kill -0 $(cat artifacts/tunnel.pid) && echo up
  curl -s -o /dev/null -w "%{http_code}\n" https://prep-karma-raleigh-created.trycloudflare.com/api/info   # expect 401
  ```
- Restart:
  ```
  kill $(cat artifacts/server.pid); CAP_AUTH_USER='gr11' CAP_AUTH_PASS='<password>' \
    nohup .venv/bin/python -m src.app.server > artifacts/server.log 2>&1 & echo $! > artifacts/server.pid
  setsid /tmp/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 \
    > artifacts/tunnel.log 2>&1 < /dev/null & echo $! > artifacts/tunnel.pid
  grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' artifacts/tunnel.log | head -1   # new URL → tell the user
  ```
  Leave out the `CAP_AUTH_*` vars for open local-only mode. `/tmp/cloudflared` disappears on reboot; re-download it from the cloudflared GitHub releases if needed.

## Stage A results (v1, `predictions.json`, run `stageA-20261003T081316Z`)
| | Acc | Macro-F1 | ECE | NLL | AURC | Coverage | Sel. acc |
|---|---|---|---|---|---|---|---|
| model | 0.437 | 0.433 | 0.096 | 1.552 | 0.467 | 0.102 | 0.471 |
| T=1 | 0.437 | 0.433 | 0.110 | 1.546 | 0.466 | — | — |
| uniform | 0.078 | 0.018 | 0.047 | 2.079 | 0.919 | — | — |

- Error rate per pair: posture 0.18, pick/put 0.52, open/close 0.59, don/doff 0.88.
- The 20% selective-risk target is **not met** (OOF 0.53). The cause is the small training set: 167 segments from the 0.9 GB val file. Stage B is the fix being tried.
- The deploy head uses `state+pose` (CLIP + pose) in every fold.

## Architecture
| Path | Role |
|---|---|
| `src/perception/{annotations,models,clip_state,features}.py` | vipy GT (boxes rescaled from 512×910), YOLO11n/-pose, R(2+1)D-18, CLIP ViT-B/32 |
| `src/model/{features,head,metrics}.py` | Feature blocks, nested OOF head + calibration + τ, metrics |
| `src/pipeline/openworld.py` | Upload/webcam path: 10 fps decode, ByteTrack, 2.4 s windows / 1.2 s stride, motion gate |
| `src/app/server.py` | FastAPI; optional Basic auth (`CAP_AUTH_USER`/`CAP_AUTH_PASS`); ID-only lookups, CSP, upload limits 200 MB / 90 s |
| `web/` | `index` (val review, upload, webcam with device picker), `gallery`, `report`. Vanilla JS, relative URLs |
| `scripts/` | `build_manifest`, `extract_features`, `extract_clip`, `train_oof`, `validate_predictions`, `score`, `build_gallery` |
| `tests/` | 27 tests (annotations, OOF leakage spy, app API/security/auth) |

## Environment
- EC2 t3.xlarge, us-east-1b: 4 vCPU, 15 GB RAM, no GPU, 68 GB free. Python 3.9, `.venv` (uv), pins in `requirements.lock.txt`.
- Never install GUI `opencv-python` (no libGL). ByteTrack needs `lap`. No git repo; only create one if asked.

## Rules to keep
- Contract §2:
  - Never identify people.
  - Refer to subjects only by `collector_id[:8]`.
  - Never read `subject_ids`, `ipAddress` or `device_identifier`.
  - Media stays on the host.
- Out-of-fold: nothing fitted for fold k may use fold k.
- After any change: run `pytest`, the validator and `score.py`, then restart the server (with auth).
- AI-DLC: append every user input to `aidlc-docs/audit.md`, and update `aidlc-state.md` and `docs/effort-log.md`.
