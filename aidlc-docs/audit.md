# AI-DLC Audit Log

## 2026-10-03T06:40:44Z — Initial user request
**User input (verbatim summary of key directives)**: "Using AI-DLC, start a new project. Begin with the Inception phase." Intent: prototype review tool for human-activity recognition (bbox + track id, timeline, calibrated confidence, abstention, failure gallery). Frozen contract: `docs/shared-contract.md`, `configs/predictions.schema.json`, `manifests/val_segments.csv`. Data: CAP val file at <DATA_PATH>, data rules. Deliverables: tool, OOF predictions.json, weights list, `docs/effort-log.md`. Stage A required first; Stage B optional, cost estimate + approval first, dedicated bucket not CDK bootstrap. Deadline 2026-10-04. Ask clarifying questions; wait for approval before Construction.

**Findings**: workspace empty; contract files absent system-wide; CAP val data found at `/Workshop/3dgame/data/real/` (prior AI-DLC attempt in `/Workshop/3dgame` hit the same blocker). 208 raw labels, not 8; `ref.csv` lacks collector_id/segment_id/fold; MP4s not extracted. Raised Q1–Q5.

## 2026-10-03T06:53:04Z — User
**Input**: "There're no file in s3 bucket "cdk-hnb659fds-assets-877736402856-us-east-1" right? Could you get data form https://registry.opendata.aws/visym-cap/ to use in the project"
**Action**: `list-objects-v2` → KeyCount 0 (empty). Registry → `s3://consented-activities-of-people/train/` (us-west-2, public): `cap_classification_clip.tar.gz` 308.7 GB, `cap_classification_pad.tar.gz` 414.9 GB. Explained these are Stage B sources only; Stage A uses local val file. No download started.

## 2026-10-03T06:55:36Z — User
**Input**: "What is q1 to q5?"
**Action**: Restated Q1–Q5.

## 2026-10-03T07:01:10Z — User
**Input**: "What is  frozen contract? confirm as you recommend."
**Decision recorded**: Q1=c (draft proposed contract), Q2=propose 8 classes around confusable pairs, Q3=extract MP4s locally, Q4=a (fresh in /Workshop/cap-position), Q5=Python/FastAPI + pretrained detector/tracker + calibrated head.
**Actions**: extracted val tar (680 MB videos + 185 MB visualize) to `data/`; profiled JSON; found `ref.csv` deviates ±1 frame from JSON → JSON adopted as GT; drafted contract v0.1, schema, manifest generator, validator; validator tested with valid/invalid files.

## 2026-10-03T07:12:25Z — Inception artifacts presented for approval
Requirements, units of work, open questions, effort log written. ⛔ Awaiting user approval.

## 2026-10-03T07:20:58Z — User
**Input**: "please create hand-off note I will continue in new session"
**Action**: Wrote `docs/handoff.md`. Session ends at the Inception approval gate; Q6–Q12 still open.

## 2026-10-03T07:22:12Z — User (new session)
**Input**: "Please continue /Workshop/cap-position/docs/handoff.md"
**Action**: Resumed from hand-off. Verified state: manifest regenerates with sha256 66181cb2…f321, 47 videos present, no `src/`/`artifacts/`. Q6–Q12 still unanswered → gate held; re-presented Q6–Q12 to user.

## 2026-10-03T07:26:03Z — User
**Input**: "approve all"
**Decision recorded**: Q6–Q12 = A (all recommended). Contract v0.1 FROZEN (manifest sha256 66181cb2…f321). Inception gate passed → Construction starts with U2.

## 2026-10-03T08:25Z — Construction Stage A complete (no user input since 07:26Z)
**Actions**:
- U2: pinned deps (`requirements.lock.txt`); rescaled the vipy boxes; built the pose, R(2+1)D and CLIP feature caches.
- U3: nested OOF selecting feature set, C, time-reversal augmentation, temperature and τ → `predictions.json` VALID (167 segments); `score.py` report written.
- U4: FastAPI tool on 127.0.0.1 with val mode and upload mode.
- U5: gallery and report pages.
- U6: README, `weights.md`, effort log.

**Deviation to flag**: added the CLIP ViT-B/32 (MIT) and R(2+1)D-18 (BSD) frozen backbones beyond the Q7 detector/pose choice. Both are permitted by contract §5 and listed in `run.weights` / `docs/weights.md`.

**Result**: OOF acc 0.437, ECE 0.096, AURC 0.467, coverage 0.102 at selective acc 0.471. The 20% risk target is not met (documented).

## 2026-10-03T08:24Z — User
**Input**: "So it was done and runable right?"
**Action**: Re-checked: server alive, all pages/APIs 200, 24 tests pass. Answered yes, with the caveats (no browser check, risk target missed, Stage B pending).

## 2026-10-03T08:26Z — User
**Input**: "please create summarized note in md file. How can I run the page in my pc?"
**Action**: Found the code-server proxy (`/proxy/8000/`). Made all web URLs relative so they work behind the proxy prefix; tests still pass; server restarted. Wrote `docs/summary.md` with access options A (proxy), B (Ports panel) and C (SSH tunnel).

## 2026-10-03T08:44Z — User
**Input**: "please create hand-off to continue in another session"
**Action**: Rewrote `docs/handoff.md`. Session ends at Stage A complete; open items are the browser check by the user and the Stage B decision.

## 2026-10-03T08:49Z — User (new session)
**Input**: "continue /Workshop/cap-position/docs/handoff.md and add function to process form live webcam"
**Scope assessment**: Live webcam is a new *source* for the already-approved open-world upload path (Q9: "open-world upload (experimental, unscored)"), not a contract change — so no v0.1 bump. Honored contract §2.3 (pixels stay on host): capture is done in-browser with `getUserMedia` + `MediaRecorder`, and the recorded clip is POSTed only to the existing local `/api/upload` endpoint. No new server endpoint, no new processing path, no media egress.
**Action**:
- `web/index.html`: added a webcam block to the Upload pane (`#cam` live preview; Enable camera / Record / Stop & analyse / Turn off buttons; `#camstatus`), framed as experimental and local-only.
- `web/app.js`: added `startCam`/`stopCam`/`startRec`/`stopRec`/`submitRecording` plus helpers (`camStatus`, `camButtons`, `camSupported`, `pickMime`); recording is hard-capped at `max_upload_seconds` from `/api/info`; the Blob is submitted as `webcam.webm` (`.webm` already in `ALLOWED_EXT`) through the shared `api('api/upload')` → `openJob` flow, so it reuses the server size/duration/extension limits and the Stage-A deploy head.
**Verification**: 24 pytest pass; `node --check web/app.js` OK; server restarted (PID alive); `/`, `/gallery`, `/report`, `/static/app.js`, `/api/info` all 200; served HTML/JS contain the new webcam markup and `submitRecording`. Browser camera flow itself is not testable on this headless host (no camera, no Chromium deps) — the user must verify capture in a real browser.
**Note / limitation to flag**: `MediaRecorder` + `getUserMedia` require a secure context (HTTPS or localhost). The CloudFront proxy URL is HTTPS, so it works there; a plain-`http://` LAN IP would block camera access.

## 2026-10-03T09:00Z — User: make it publicly accessible
**Input (sequence)**: "Could you deploy to https://d2wxa2we707rwy.cloudfront.net/proxy/8000/" → clarified that URL is code-server's auth-gated proxy to the local server (nothing to deploy). → "could you deploy this to accessible in public? that other people can access" → I laid out options A (auth + tunnel, data protected), B (fully public), C (AWS). → User: "b". **I declined B**: serving the CAP subject videos to the open internet breaches *mandatory* contract §2.3 and reverses Q10; a one-letter reply is not sufficient authorization for a human-subjects-data decision. Offered a public-but-data-stripped variant. → User: "then a and use username: gr11 pass: <provided in chat>".
**Decision recorded**: Option A — access-controlled sharing. Contract amended **v0.1 → v0.2** (Q10 deviation): HTTP Basic auth in front of the app, bind stays loopback, exposed via an authenticated tunnel. §2 data rules unchanged and still enforced (media reachable only by credential holders, not the public).
**Action**:
- `src/app/server.py`: added a `basic_auth` middleware. Credentials come from `CAP_AUTH_USER` / `CAP_AUTH_PASS` env vars (never hardcoded, never written to disk, never logged); auth is enabled only when both are set, so the default local mode is unchanged. Constant-time compare (`secrets.compare_digest`); 401 + `WWW-Authenticate: Basic` challenge on every route.
- `tests/test_app.py`: added `test_basic_auth_helper`, `test_basic_auth_gate`, `test_no_auth_when_disabled`.
- Downloaded `cloudflared` to `/tmp/cloudflared`; started a quick tunnel (`setsid`, pid in `artifacts/tunnel.pid`, log `artifacts/tunnel.log`) to `http://127.0.0.1:8000`.
- Restarted the server with the auth env vars set (passed inline, not persisted).
**Verification**: 27 pytest pass. Local curl: 401 no creds, 401 wrong creds, 200 correct creds, static assets gated, no secret in `server.log`. Through the public URL `https://prep-karma-raleigh-created.trycloudflare.com`: 401 unauthenticated (incl. `/gallery`), 200 with the credential, webcam build served, HTTPS (secure context for the camera).
**Security notes flagged to the user**: the password was shared in plaintext in chat → recommend rotating after the event. The `trycloudflare` URL and the whole setup are **ephemeral** — they die when this host session / processes stop, and the URL changes if cloudflared restarts. HTTP Basic over a public URL is adequate for a short-lived demo among a few people, not a durable public service.

## 2026-10-03T09:13Z — User: live-stream processing, split into 2 phases
**Input**: "let devide in 2 phase 1. let it able to access camera on running device 2. process the live steam. after deploy phase one please notify me before proceed to phase 2"
**Feasibility measured before committing**: past upload jobs show ~46 s to process a 15 s clip (8 windows) → ~5–6 s compute per 2.4 s window on this GPU-less host, i.e. ~3× slower than real time. Told the user true real-time isn't achievable here; Phase 2 can only be *near-live* rolling inference (~5 s latency). The deploy head uses the `state+pose` feature set, so R(2+1)D is already skipped; per-frame YOLO + per-window CLIP/pose dominate cost.
**Plan recorded**:
- **Phase 1 (done this session)** — camera access on the running device, on the deployed site. The record→`/api/upload` capture already existed; added a **camera device picker** (`enumerateDevices`), a secure-context (HTTPS) guard, friendlier permission/not-found/in-use error messages, and live camera switching. No new server endpoint; same experimental/unscored path (Q9). Files: `web/index.html` (`#camdevice`), `web/app.js` (`populateCameras`, `camErrorMessage`, `switchCam`, reworked `startCam`).
- **Phase 2 (GATED — not started)** — near-live rolling stream processing: a new chunk endpoint + a "Live" UI mode sending ~2.5 s chunks, one window inferred per chunk. **Explicitly STOP and notify the user before starting Phase 2** (user instruction).
**Verification (Phase 1)**: `node --check web/app.js` OK; 27 pytest pass; server restarted with auth (pid 231331); tunnel alive; public URL serves `id="camdevice"` and functions `populateCameras`/`camErrorMessage`/`switchCam`. Browser camera selection still needs the user to click through on a real device (headless host).
**Status**: Phase 1 deployed. Awaiting user go-ahead for Phase 2.

## 2026-10-03T09:18Z — User: bug report, Stop button does nothing
**Input**: "After push stop button timer was stop but then nothing happen could you check?"
**Root cause**: the Stop button was wired `$("camstop").onclick = stopRec;`, so the DOM passed the click **event** as `stopRec`'s `silent` argument. The event object is truthy → `stopRec` took the "discard" branch (`S.cam.rec.onstop = null`), so `submitRecording` never ran after the recorder stopped. The timer cleared and nothing else happened — exactly the reported symptom. The internal callers (`stopCam`→`stopRec(true)`, timer-cap→`stopRec()`) were correct; only the button was broken.
**Fix** (`web/app.js`): button now calls `() => stopRec(false)`; `stopRec` hardened to discard only when `silent === true` (ignores a stray event arg). Comments clarify `rec.stop()` fires `onstop`→`submitRecording`.
**Verification**: `node --check` OK; 27 pytest pass; fixed code (`stopRec(false)` and `silent === true`) served through the public URL. Full browser click-through of record→stop→analyse still needs a real camera device (headless host).

## 2026-10-03T09:46Z — User: Stage B go, archive choice
**Input**: "ok go for clip and create in v2"
**Decision recorded**: Stage B approved in principle (Q12) using `cap_classification_clip.tar.gz`; results as a separate **v2** run (`run.stage="B"`). v1 (Stage A) stays as the demo and is not modified.
**Facts gathered (read-only)**: host EC2 t3.xlarge us-east-1b, 4 vCPU, no GPU, 68 GB free, public IPv4. Archive 308,736,485,473 B in us-west-2 (cross-region), single tar.gz, no index or side files (`train/` lists only the 2 archives). 200 MB ranged peek (deleted afterwards): 29 MB/s single stream, decompress 160 MB/s (network-bound); layout `videos/<raw_label>/<UUID>_0.mp4`, ~315 KB/clip → ~0.96M clips; clips 2.3 s at 512×910; **no annotation JSON in the first 200 MB**, so `collector_id` availability is unconfirmed. Stage A cost ~4–5 s CPU per segment.
**Estimate presented** (see chat): stream 1–3 h; feature extraction must be subsampled (~2–4k clips, 2–5 h); incremental AWS cost a few USD. ⛔ Awaiting explicit approval before the full pass (contract §7).

## 2026-10-03T10:59–11:09Z — User: Stage B approvals
**Inputs**: "What time differnet between sub sample size between 250 and 500?" → answered: +~2.5 h extraction (~4–6.5 h vs ~6–9 h total), <$1 extra; streaming time is the same. → "ok use 500 and create hand-off-note I will continue in new session" → "for #1 approve, for 3 storage which one is faster and which one is more cost?" → answered: host-only is faster and ~$0; S3 adds minutes + setup and cents to ~$1/month, benefit is durability only. → "ok then for host only please record and proceed to create hand-off note"
**Decisions recorded (contract §7 approval gate PASSED)**:
1. Full streaming pass of `cap_classification_clip.tar.gz` — **APPROVED** (estimate ~6–9 h, a few USD).
2. Subsample — **500 clips per class** (≤ 4,000 clips).
3. Storage — **host only**, dedicated git-ignored folder `data/stageB_v2/` (no S3 bucket; never the CDK bootstrap bucket). Interpreted as the §7 "dedicated prefix"; media never leaves the host (§2.3).
**Hard stop condition kept**: if no per-clip `collector_id` is found in the archive, stop before training and report (val-collector exclusion is mandatory).
**Action**: no transfer started in this session (user continues in a new session). Hand-off rewritten.

## 2026-10-03T11:12Z — User
**Input**: "please change the name of hand-off note to hand-off-learning.md"
**Action**: Renamed `docs/handoff.md` → `docs/hand-off-learning.md`. Earlier audit entries keep the old name as historical record. The next session should continue from `docs/hand-off-learning.md`.

## 2026-10-03T11:14Z — User: Stage B v2 start, metadata-first
**Input**: continue `docs/hand-off-learning.md` → when offered (1) start the full streaming pass now vs (2) investigate collector metadata first, chose **"2"**.
**Decision**: Before committing to the ~6–9 h full streaming pass, run a targeted read-only investigation to confirm whether a per-clip `collector_id` source exists anywhere in `cap_classification_clip.tar.gz`. This directly de-risks the §7 hard-stop (val-collector exclusion). No full download, no training started.
**Rationale**: tar is sequential (labels not alphabetical), so a members-only index still streams the whole archive — but we can bound the cost: list the archive's non-mp4 members and peek the archive head/early members for any JSON/CSV/manifest carrying `collector_id`, with a disk guard and a hard byte/time cap, aborting early. If no metadata is found in the bounded peek, report back before any full pass.

### 2026-10-03T11:16Z — Finding: no `collector_id` source in `cap_classification_clip` → §7 hard-stop HIT
Bounded, read-only investigation (no full download, no training). Evidence:
1. **Bucket**: only listable prefix is `train/`, holding exactly the two archives (`cap_classification_clip.tar.gz` 308.7 GB, `cap_classification_pad.tar.gz` 414.9 GB). Root and `annotations`/`meta` listings are AccessDenied. **No sidecar index/manifest exists.**
2. **Archive members** (streamed ~2 GB head, 6,101 members → `artifacts/v2/peek_members.txt`): all mp4 except directory entries. **No JSON/CSV/manifest member.** tar owner is a constant `jba3139/str.diva` (uid/group), not per-clip. Labels are contiguous per directory (first 2 GB = `person_picks_up_object_from_floor` only), confirming non-alphabetical layout.
3. **mp4 container metadata** (171 complete clips extracted to a temp dir, scanned, then deleted): the only `udta/meta/ilst` tag is `©too = Lavf58.29.100`. **Zero** hits for collector/collection/subject/device/ipAddress/uploader/author/user. Clips were re-encoded through ffmpeg (libavformat), which stripped any original device/collector metadata. No UUID strings embedded in clip bytes.
4. **Filenames**: clip names are **UUIDv4 (random)** — no time, no MAC/node, nothing derivable. **Zero overlap** with val `video_id`/`collector_id`, and they do not appear anywhere in the val vipy JSON, so val clips can't be detected by UUID match either.
**Conclusion**: there is **no way to recover a per-clip `collector_id`** for `cap_classification_clip`, so the mandatory val-collector exclusion (contract §7) **cannot be satisfied** for this archive. Per the hand-off hard-stop, **STOP before any full streaming pass or training** and report to the user. The ~6–9 h download was NOT started.
**Options to put to the user**:
- (a) **Abandon Stage B on the clip archive.** Keep Stage A (v1) as the demo. Honest and contract-clean.
- (b) **Try `cap_classification_pad.tar.gz`** (the other, larger archive) with the same bounded metadata peek first — only worth it if it carries collector metadata; same hard-stop otherwise.
- (c) **Amend the contract** to allow training on data where val-collector exclusion can't be guaranteed, *accepting leakage risk*. This weakens the §7 guarantee and would need an explicit version bump + the user's approval. (Not recommended.)
**Cleanup**: temp clips deleted; only `artifacts/v2/peek_members.txt` kept. Disk back to 68 GB free. Nothing written to `data/stageB_v2/`.

## 2026-10-03T12:20Z — User: abandon Stage B, keep v1 as the demo
**Input**: after the §7 hard-stop options, chose **"a"** (abandon Stage B on the clip archive; Stage A/v1 stays the demo).
**Decision (final for this event)**: U7 Stage B is **CLOSED — not pursued**. Reason: `cap_classification_clip.tar.gz` has no recoverable per-clip `collector_id`, so the mandatory val-collector exclusion (contract §7) can't be guaranteed; training on it would risk val leakage. The contract-clean choice is to keep Stage A (v1, `predictions.json`, run `stageA-20261003T081316Z`) as the demo, with its documented limitation (OOF selective risk 0.53 vs the 20% target), rather than ship a result we can't certify leakage-free.
**Scope impact**: no code changes; no model changes; v1 unchanged and still live. The ~6–9 h download was never started; no S3 egress billed beyond the small bounded peeks. `data/stageB_v2/` is empty.
**Cleanup**: removed `artifacts/v2/peek_members.txt` (investigation artifact no longer needed) and the empty `artifacts/v2/`. Nothing in `data/stageB_v2/`.
**Server/tunnel**: unchanged and still serving v1 (see hand-off "Server & tunnel").

## 2026-10-03T12:30Z — User: two arms
**Input**: "now I want to create another 2 arm first is for deploy the code to git second is for my team to continue modeifying app from git that can implement analyzing metadata in other session. just create the first hand-off and wait for me to let you continue the second hand-off"
**Action**: Read-only fact check (no repo created in the workspace; throwaway `GIT_DIR` in /tmp, deleted). Results: no git repo, gh/glab missing, no SSH key; current `.gitignore` would commit ~50 files / 352 KB with no media, weights or secrets. Wrote `docs/hand-off-arm1-git-deploy.md`, listing the decisions needed (remote, visibility, credentials, first push to main, `deploy.pkl` handling, `gr11` redaction) and the steps.
**Status**: Arm 1 hand-off written; no git actions taken. **Arm 2 hand-off on hold** until the user asks.

## 2026-10-03T12:42–12:52Z — User: full-analyze cap_classification + plan to implement; checkpointing
**Inputs**: "I want you to full analyze the cap_classification and planning implement to our app." → clarified the §7 implementation blocker; asked whether to stop at the gate or pre-authorize a §7 amendment → user: **"stop at the gate"** → "shall we create check point to prevent data loss if session crashed half way? and How should we manage check point?" → design presented and approved → "yes, please proceed."
**Decisions**:
1. Reopen Stage B **analysis** (not implementation): run a **full** streaming pass of `cap_classification_clip.tar.gz` to produce a definitive per-clip `collector_id` inventory. (Supersedes the 12:20Z "abandon" for the analysis step only.)
2. **Gate behavior = STOP AT THE GATE** (current contract §7). If no recoverable per-clip `collector_id` is found, STOP before training/implementation and report. No §7 amendment authorized.
3. **Checkpointing (approved)** — model (B), member-level idempotency, since tar.gz is non-seekable and we lack 308 GB to stage the object:
   - Atomic clip writes (`*.part` → `os.rename`); `.part` swept on startup.
   - Append-only, fsync'd member ledger `artifacts/v2/members.jsonl` (name, size, is_mp4, class, non-mp4 content hash) = durable metadata inventory + crash record.
   - Atomic progress file `artifacts/v2/stream_state.json` (members_seen, clips_written, bytes_consumed, per_class_counts, last_member, status).
   - Feature stage resumable: one feature file per clip, skip-if-exists.
   - All output under `data/stageB_v2/` + `artifacts/v2/` only; v1 (`predictions.json`, live server) untouched.
   - Disk guard: clean pause (status `paused_disk`) below ~10 GB free. Detached via `setsid nohup`; pid in `artifacts/v2/stream.pid`. **Never `pkill -f`.**
**Honest limitation acknowledged by user**: a mid-stream crash re-pulls network bytes (gzip/tar can't resume); checkpointing preserves extracted clips + metadata + features, not the download position.

## 2026-10-03T12:53–12:55Z — User
**Input**: "so does it need git account or autthenication to git?" → answered: yes for pushing to a remote (an account plus an empty repo, and a token or SSH key); local commits need neither. → "would new session will guide me to login git? if not please add it to the note."
**Action**: Added a "Git login guide" section to `docs/hand-off-arm1-git-deploy.md`: create an empty private repo; Option A SSH deploy key (recommended, no secret in chat); Option B short-lived repo-scoped token with a one-shot credential helper; Option C CodeCommit via the instance role (unverified). The session must pause at each user step.

## 2026-10-03T12:57Z — User
**Input**: "So the deplay plan was include every thing my team to continue dev right? if yes proceed to second hand-off"
**Finding**: Not fully. A clone would lack the CAP data (also needed by the tests), the weights, the rebuilt artifacts (features, `deploy.pkl`, report, gallery) and host-only state. Contract §2.3 ("media stays inside this environment") conflicts with teammates downloading media to their own machines. The lock file was checked: all runtime and test packages are pinned.
**Action**:
- Added a "Team readiness" section to `docs/hand-off-arm1-git-deploy.md`.
- Wrote `docs/hand-off-arm2-team-dev.md`. It covers: confirming the dev environment (§2.3), what "metadata analysis" means (A dataset breakdowns / B upload-container tags with GPS stripped / C review analytics), and the team workflow. It also has the metadata key inventory (names only; three forbidden keys present but never read), a suggested design for option A, onboarding steps, and the PR/contract/audit workflow.
**Status**: both arm hand-offs written. No git actions taken.

## 2026-10-03T13:04Z — User
**Input**: "so for git-deploy everything is ready except data right? moreover could you let new session deply to git hub"
**Answer**: The code is ready (27 tests pass, scans clean), but a clone also lacks the weights and the rebuilt artifacts (including `deploy.pkl`), not only the data. The push itself still needs the repo URL, visibility, login method, the `deploy.pkl` choice and the `gr11` redaction choice.
**Decision recorded**: remote = **GitHub**. The new session is authorized to deploy, including the initial push to `main` of the new empty repo. Updated `docs/hand-off-arm1-git-deploy.md`.

## 2026-10-03T13:05Z — User
**Input**: "could we deply everything exept data?"
**Action**: Sized every non-data item. Recorded the planned push scope in `docs/hand-off-arm1-git-deploy.md` (decision 5).
- **Push**: code and docs, the YOLO weights (11.4 MB, AGPL note kept), `deploy.pkl`, the report, the gallery index.
- **Excluded**:
  - gallery thumbnails and uploads/webcam videos: pixels of people, §2.3;
  - CLIP 338 MB and R(2+1)D 120 MB checkpoints: over GitHub's 100 MB limit, and they auto-download;
  - `.venv`, logs and host state.
- **Open (recommend no)**: feature caches containing pose keypoints and CLIP crop embeddings, i.e. person-derived data.

## 2026-10-03T13:09–13:11Z — User
**Inputs**: "between github and private git create by you which one do you recommend for a small group and small project" → recommended a private GitHub repo. → "then we will create self hose instead please update the hand-off note"
**Decision recorded**: **self-hosted git** replaces GitHub. The 13:04Z authorization for the initial push to `main` and the 13:05Z scope ("everything except data") carry over.
**Facts checked**: Amazon Linux 2023, user `participant`, **no sudo**, sshd on :22, Docker usable without sudo, port 3000 free, no crontab.
**Action**: rewrote `docs/hand-off-arm1-git-deploy.md` for Gitea:
- pinned binary with sha256 check, run as the user, data in `~/gitea/`, bound to 127.0.0.1:3000;
- HTTPS only, registration off, sign-in required, branch protection;
- push token generated on the host, so no secret goes into chat;
- options: on-host only, or a cloudflared tunnel for remote teammates.

Risks flagged: the instance may be temporary (backups; off-host copy needs approval), the tunnel URL is ephemeral, and Gitea is one more service to patch. Never add teammates' SSH keys to `participant`. Updated the Arm 2 onboarding and workflow notes for Gitea.

## 2026-10-03T13:19Z — User: Arm 1 Gitea deploy decisions
**Input**: "1: option 2 2: could we use token? there're 3 in the team (Ice, Pok, Donut) each one will use seperate token 3: on-host only 4: don't push 5: can we use token?"
**Decisions recorded (Arm 1, `docs/hand-off-arm1-git-deploy.md`)**:
1. **Gitea access = Option 2** — on-host Gitea bound to 127.0.0.1:3000 plus a cloudflared quick tunnel for remote clones (ephemeral URL, dies with the host session).
2/5. **Credentials = per-user personal access tokens over HTTPS.** Three teammate accounts — `ice`, `pok`, `donut` — each generates and uses their own token (individually revocable, attributable in the audit log). The initial push to `main` uses a short-lived host-side admin token that is deleted immediately after.
3. **Backups = on-host only** (`gitea dump` + `git bundle --all` to `~/gitea-backups/`). No S3, no off-host copy.
4. **Feature cache = DO NOT push.** `artifacts/features/` (pose keypoints + CLIP crop embeddings of person crops, §2.1/§2.3) stays out of git; it rebuilds in ~15 min.
- `gr11` redaction (hand-off open Q5): not addressed by the user; defaulting to **leave as-is** (shared demo credential, not a token). Will re-confirm if the user wants it redacted.
**Still needed to create accounts**: admin username + email; OK to use placeholder teammate emails `ice@example.local` / `pok@example.local` / `donut@example.local` (changeable at first login).
**Pinned**: Gitea **1.27.3** (latest stable as of this session), linux-amd64, sha256-verified. v1 app server (:8000) + its tunnel and the Stage B v2 inventory run (`artifacts/v2/`) left untouched.
