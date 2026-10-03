# Effort Log

Times are UTC on 2026-10-03 unless stated. "Turns" counts user prompts, and in brackets the assistant tool calls.

| Phase / stage | Start → end | Wall-clock | User prompts (tool calls) | Human interventions | Defects found in review |
|---|---|---|---|---|---|
| Inception — workspace detection & requirements | 06:40 → 07:12 | 32 min | 4 (≈40) | 3: asked about the CDK bucket and the open-data source; asked what Q1–Q5 meant; asked what the frozen contract is and approved the recommendations | 3 (below) |
| Construction — U2 perception, U3 OOF/calibration, U4 tool, U5 gallery/report, U6 docs | 07:26 → 08:25 | ~60 min | 1 ("approve all") (≈75) | 0 | 6 (below) |
| Build & test | 08:05 → 08:25 (overlapping) | — | — | 0 | 24 pytest pass; validator VALID; UI JS syntax-checked only (no browser available on host) |
| Stage B (v2) — archive choice, estimate, approval | 09:41 → 11:09 | ~25 min active | 6 (which archive / go clip v2 / 250 vs 500 / approve + storage? / host only) (≈12) | 3 decisions: clip archive, 500/class, host-only storage | 0 (200 MB peek: no annotation JSON seen yet → collector_id risk flagged) |
| Construction — live webcam capture (open-world source) | 08:49 → 08:53 | ~4 min | 1 ("…add function to process form live webcam") (≈12) | 0 | 0 (24 pytest pass; JS syntax-checked; pages/APIs 200; browser camera flow not testable on headless host) |
| Construction — auth + tunnel (public access, contract v0.2) | 08:57 → 09:06 | ~9 min | 4 (deploy?/public?/"b"/"a + creds") (≈15) | 1 refusal: declined fully-public exposure of CAP subject media (breaches §2.3); redirected to auth + tunnel | 0 (27 pytest pass; local + public-URL curl: 401 unauth / 200 auth; no secret in log) |
| Construction — live-stream Phase 1 (camera access + device picker) | 09:10 → 09:16 | ~6 min | 2 (webcam-live? / split in 2 phases) (≈12) | 0 (plan gated: STOP before Phase 2 per user) | 0 (27 pytest pass; JS syntax OK; device picker + fns served via public URL; browser camera click-through pending on a real device) |
| Stage B (v2) — collector_id metadata investigation → closed | 11:13 → 12:21 | ~8 min active | 3 (continue hand-off / "2" metadata-first / "a" abandon) (≈16) | 2 decisions: investigate metadata before the full pass; then abandon Stage B, keep v1 | 1 finding: **no recoverable per-clip `collector_id`** in the clip archive → §7 hard-stop; full download NOT started; Stage B closed, v1 remains the demo |
| Arm 1 — self-hosted git deploy (Gitea + tunnel) | 13:13 → 13:31 | ~18 min | 5 (continue hand-off / 5 decisions / admin=gr11 / password / live-steer: optional pw change) (≈22) | 5 decisions (Option 2 tunnel, per-user tokens, on-host backups, no feature cache, admin=gr11) + 1 live-steer (make password change optional) | 0 (sha256 verified; 27 pytest pass; secret scan clean; fresh clone identical with no media; anon blocked 303/401/403) |

## Defects found in review (Inception)
1. **Data**: `cap_detection_handheld_val_ref.csv` differs from the vipy JSON by ±1 frame on most of the 395 rows. Resolution: JSON adopted as GT (contract §1).
2. **Self-review, manifest v0**: greedy size-balanced fold split left `open`/`close` with 0 segments in fold 0 and `put_on_wearable` with 0 in fold 2. Resolution: seeded class-stratified group search; all 8 classes now in every fold.
3. **Self-review, validator**: when the schema fails, it stops before the manifest-level checks, so coverage/fold/sum errors are only reported once the schema passes. Accepted (documented behaviour); the manifest checks were tested separately and caught a missing segment, a fold mismatch and a probability sum of 1.375.

## Defects found in review (Construction)
1. **Data**: vipy boxes are stored in the 512×910 frame from the JSON's `ffmpeg scale=` filter, not the native 1080×1920 frame. Fix: rescale in `annotations.py`. After the fix, a sanity check found median IoU 0.94 vs YOLO person boxes.
2. **Env**: `ultralytics` pulled in GUI `opencv-python`, which needs libGL (absent on the host) and broke the import. Fix: kept only `opencv-python-headless`.
3. **Env**: ByteTrack needs `lap`, which wasn't installed, so the first upload job failed. Fix: pinned `lap==0.5.12` and re-ran; the job succeeded.
4. **Model**: a pose + R(2+1)D head scored only 38% OOF accuracy, with direction inside a pair barely above chance. Fix: added CLIP start/end state features and time-reversal augmentation, both selected in the inner CV → 44%; posture error went from 0.36 to 0.18.
5. **Test hygiene**: `pkill -f` patterns matched the invoking shell twice and killed the tool call. Fix: the server PID is now kept in `artifacts/server.pid`.
6. **Finding (not fixed)**: OOF selective risk is 0.53, above the 20% target. Documented in the README; Stage B data is the lever.

## Notes
- The prior attempt in `/Workshop/3dgame` reached the same "contract missing" finding. Its data was reused read-only; nothing else was carried over.
