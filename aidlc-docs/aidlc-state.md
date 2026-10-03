# AI-DLC State Tracking

## Project Information
- **Project Name**: CAP Activity Review Tool (cap-position)
- **Project Type**: Greenfield
- **Workspace Root**: /Workshop/cap-position
- **Start Date**: 2026-10-03T06:40:44Z
- **Deadline**: Review tool demo-ready 2026-10-04 (event Day 2)
- **Problem**: Activity recognisers confuse look-alike motions (sit/stand, pick/put, open/close, don/doff) yet report high confidence, so wrong records go unnoticed in patient/elderly monitoring. The tool must show tracks, a segment timeline, calibrated confidence, and must abstain when unsure, plus provide a failure gallery.

## Workspace State
- **Existing Code**: No (Inception artifacts only)
- **Languages / Build**: Python 3.9 (system), uv venv `.venv`
- **Hardware**: 4 vCPU, 15 GB RAM, no GPU, 71 GB free disk; no system ffmpeg
- **Data**: `data/cap_detection_handheld_val/` (extracted 2026-10-03; 47 videos + 47 visualize MP4s, 47 vipy JSON)
- **Reverse Engineering Needed**: No

## Contract Status
- The user-referenced frozen contract was absent on disk. With user approval (2026-10-03T07:01Z, "confirm as you recommend") a **proposed** contract v0.1 was drafted:
  `docs/shared-contract.md`, `configs/predictions.schema.json`, `manifests/val_segments.csv` (sha256 66181cb2…f321).
- Status: **AMENDED v0.2** (2026-10-03T09:05Z) — Q10 (no auth, loopback) amended to allow access-controlled external exposure: HTTP Basic auth (env-var creds) + authenticated tunnel; §2 data rules unchanged. v0.1 was FROZEN 2026-10-03T07:26Z ("approve all"). Changes require a version bump + audit entry.

## Extension Configuration
| Extension | Enabled | Note |
|---|---|---|
| security/baseline | Yes (lite) | local-only bind, no media egress, input validation on upload |
| resiliency/baseline | No | prototype, single host |
| testing/property-based | No | unit + contract tests only |

## Approved decisions (Q6–Q12, 2026-10-03T07:26Z)
Q6 contract v0.1 frozen · Q7 YOLO11n + YOLO11n-pose (AGPL-3.0) · Q8 target selective risk ≤ 20% · Q9 val-video mode (main) + open-world upload (experimental, unscored) · Q10 127.0.0.1, no auth · Q11 security-lite on, resiliency/PBT off · Q12 Stage B decided after Stage A demo-ready, cost estimate first.

## Code Location Rules
- Application code: workspace root (`src/`, `scripts/`, `web/`), never in `aidlc-docs/`
- AI-DLC documentation: `aidlc-docs/` only; project docs required by brief: `docs/`

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Requirements Analysis — approved
- [x] Workflow Planning (in units-of-work.md)
- [x] Units Generation — approved
- [x] User approval gate — passed 2026-10-03T07:26Z

### 🟢 CONSTRUCTION PHASE
- [x] U2 Perception (pose, R(2+1)D, CLIP caches) · [x] U3 nested OOF → predictions.json VALID · [x] U4 Review tool · [x] U5 Gallery & report · [x] U6 Docs (README, weights.md, effort log)
- [x] Build and Test: 24 pytest pass; data-rule grep clean; browser E2E not possible on host (no Chromium deps)

### 🟡 OPTIONAL
- [x] U7 Stage B → **CLOSED, not pursued (user decision 2026-10-03T12:20Z)**. Cost gate passed 11:09Z, but the 11:16Z bounded metadata peek found **no recoverable per-clip `collector_id`** in `cap_classification_clip.tar.gz` (no sidecar manifest; mp4 metadata stripped to `©too`; filenames UUIDv4; zero val overlap), so §7 val-collector exclusion can't be guaranteed. User chose to abandon Stage B and keep Stage A (v1) as the demo. Full download never started; `data/stageB_v2/` empty; investigation artifacts removed. Evidence: `aidlc-docs/audit.md` 11:16Z + 12:20Z.

## Current Stage
CONSTRUCTION — Stage A complete (2026-10-03T08:25Z) and is the final demo. Stage B (optional U7) **closed, not pursued** (2026-10-03T12:20Z, §7 collector_id hard-stop). Remaining open item: user browser demo check (webcam record→stop→analyse); live-stream Phase 2 stays gated.

### Post-Stage-A increments (within approved scope)
- 2026-10-03T08:49Z: Added **live webcam capture** as a new source for the Q9 open-world upload path (experimental, unscored). In-browser `getUserMedia` + `MediaRecorder`; the clip is POSTed to the existing `/api/upload` only — pixels stay on host (contract §2.3), no new endpoint. Files: `web/index.html`, `web/app.js`. Verified: 24 pytest pass, JS syntax OK, all pages/APIs 200. Browser camera flow needs user verification (headless host, secure-context requirement).
- 2026-10-03T09:05Z: Added **HTTP Basic auth** (`CAP_AUTH_USER`/`CAP_AUTH_PASS` env, constant-time compare) and exposed the tool via a **cloudflared quick tunnel** for access-controlled sharing (contract v0.2, Q10 amendment). File: `src/app/server.py`; tests in `tests/test_app.py` (27 pass). Public URL `https://prep-karma-raleigh-created.trycloudflare.com` — ephemeral, tied to this host session. §2 data rules intact (gated behind the credential). Password was shared in chat → rotate after the event.
- 2026-10-03T09:13Z: **Live-stream feature split into 2 phases** (user). **Phase 1 DONE** — camera access on the running device on the deployed site: added camera device picker (`enumerateDevices`), secure-context guard, better error messages, live camera switch (`web/index.html`, `web/app.js`); record→`/api/upload` path unchanged (Q9 experimental). Verified: 27 pytest pass, JS syntax OK, device picker + functions served via the public URL. **Phase 2 (near-live rolling stream inference) is GATED — do not start without the user's go-ahead.** Feasibility: host is ~3× slower than real time (~5–6 s/window), so Phase 2 can only be near-live (~5 s latency), not true real-time.
