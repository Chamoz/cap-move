# Hand-off — Arm 2: team development from git and metadata analysis — updated 2026-10-03T13:45Z

Project: CAP Activity Review Tool · Method: AI-DLC · Contract v0.2
**Arm 1 is DONE** (`docs/hand-off-arm1-git-deploy.md`, completed 2026-10-03T13:31Z): the code is pushed, a fresh clone was verified (identical, no media), the README has a "Getting started from git" section, and the PR workflow was proven (PR #1 merged). Arm 2 can start.

## Arm 1 result — the live git setup (facts, not plans)
- **Server**: self-hosted **Gitea 1.27.3** on the project host, bound `127.0.0.1:3000`, exposed via a **cloudflared quick tunnel** (**Option 2**). Hardened: sign-in required, registration off, SSH disabled, repos private, branch protection on `main`.
- **Repo**: `gr11/cap-position` (private). Initial commit `9a1dcf78`, tag `v1-stageA`; `main` now at `cb7d9f6` after PR #1.
- **Clone URLs**:
  - On the host: `http://127.0.0.1:3000/gr11/cap-position.git`
  - Remote (tunnel, **ephemeral** — changes if cloudflared restarts): `https://platforms-texas-spoke-europe.trycloudflare.com/gr11/cap-position.git`
- **Accounts**: admin `gr11`; teammates **`ice`, `pok`, `donut`** (Write collaborators). Per the user, the forced first-login password change was **removed** — changing it is optional. First-login passwords were handed over separately (rotate recommended).
- **Auth model**: **per-user personal access tokens over HTTPS** (SSH is disabled; no SSH keys on `participant`). `main` is protected → branch + PR, no direct push, no force-push.

## Authentication: can Kiro log in, or is the web UI needed?
- **Creating a token** needs either (a) a one-time **web login** (Settings → Applications → Generate New Token, scope `repo`), or (b) the account **password via the API** (`POST /api/v1/users/{user}/tokens` with Basic auth), or (c) the **admin** generating it on the host (`gitea admin user generate-access-token --username <u> ...`). There is no way to mint a token with neither a password nor admin rights.
- **Using git afterwards** needs **no web login**: the token is the git password, used non-interactively via a credential helper. Kiro can fully drive clone/branch/commit/push once a token exists.
- **Conclusion**: web auth is a **one-time** step to obtain each token. Everything after is terminal + token, which Kiro handles — but Kiro does **not** auto-login; a token must be supplied once (then stored via a credential helper). See `docs/handoff-teammate.md` and the login check `docs/handoff-smoke-test-git.md`.

## Goal
Teammates clone the repo, set it up, and keep developing the app in their own sessions. The first feature is **metadata analysis**.

## First action in a new session: confirm three things with the user
1. **Where the team develops.** Contract §2.3 says media stays inside "this environment". The options:
   - (a) everyone works on this host, or another single shared environment, over SSH or code-server;
   - (b) amend the contract to v0.3 and list the allowed machines.

   Don't download CAP media to a new machine until this is settled. (Note: Option 2 gives teammates a *git* URL for the code; it does **not** authorize moving CAP media off-host — that's still question 1.)
2. **What "metadata analysis" means.** Ask the user which of these, and don't guess:
   - **(A) Dataset metadata → performance breakdowns.** Show how accuracy, calibration and abstention change with recording conditions. This is the safest and most useful option for the demo.
   - **(B) Metadata of uploaded or webcam video.** Read container tags (fps, resolution, codec, duration) and show them in the UI.
     - Privacy: phone videos can carry **GPS location, creation time and device make/model**. Show and keep only technical fields (whitelist). Never store or display location, and remove these tags from the proxy.
   - **(C) Review-activity metadata.** Analytics over `artifacts/reviews.jsonl`: confirm/correct/reject rates per class and per pair, and which classes reviewers correct most often.
3. **Team workflow**: who reviews PRs, and how AI-DLC logging works with several people (see "Workflow"). Arm 1 enables branch protection on `main` in Gitea (PR required, no force-push).

## Metadata available today (CAP vipy JSON, key names checked 12:58Z)
- **Already read** (whitelist `_SAFE_ATTRS` in `src/perception/annotations.py`): `video_id`, `collector_id`, `collection_name`, `frame_width`, `frame_height`, `device_type`.
- **Present but not read yet**, candidates for option A:
  - device and app: `os_version`, `app_version`;
  - orientation: `orientation`, `deviceOrientation`, `sensorOrientation`, `rotate`;
  - video: `frame_rate`, `duration`, `blurred_faces`, `variant`;
  - collection: `collected_date`, `app_collected_date`, `collection_id`, `project_id`, `project_name`, `program_name`, `shortname`, `category`.

  Scene-level: `framerate`, `startframe`/`endframe`, `ffmpeg`.
- **FORBIDDEN, never read** (§2.2): `subject_ids`, `ipAddress`, `device_identifier`. They are in the JSON. Keep reading attributes **by explicit key only**, and never copy or iterate the whole attributes dict into an artifact.
- Some fields can narrow down who a person is when combined (dates + device + OS version). Report them only as **aggregates**: year-month, version major, bucketed. Never show them per video next to `collector_id`.
- `scripts/score.py` already breaks results down by device family (iOS/Android), resolution, fps bucket and person-box scale (§6). Option A extends that and doesn't replace it.

## Suggested design for option A (adapt after the user's answer)
1. Extend `_SAFE_ATTRS` explicitly with the agreed fields.
   - Add a test: the forbidden names never show up in any artifact or API response. Extend `test_val_video_payload_has_no_personal_fields`.
   - Update `docs/shared-contract.md` §6 breakdowns (version bump plus an audit entry).
2. `scripts/build_manifest.py`: add the new columns only if needed.
   - The frozen manifest sha256 `66181cb2…f321` is cited in contract §4, so prefer a **side table** (`manifests/val_metadata.csv`, keyed by `video_id`) and keep the manifest unchanged.
3. `scripts/score.py`: compute breakdowns per metadata bucket (acc, ECE, coverage, selective acc, AURC, pair-swap rate), with **n per bucket**. Mark buckets with n < 10 as unreliable. There are only 167 segments and 28 collectors.
4. Server and UI:
   - `GET /api/metadata/breakdown` reads from the report JSON.
   - A "Metadata" panel on the report page, and a metadata filter in the val list.
   - Keep the existing patterns: vanilla JS, `el()` instead of innerHTML, **relative URLs**, CSP-safe, accessible tables and text labels as well as colour.
5. Optional: add the metadata buckets to the failure gallery facets.

## Onboarding for each teammate (Arm 1 is live)
Each teammate uses the shared **`docs/handoff-teammate.md`** (substitute your own username `ice`/`pok`/`donut`), and verifies access with **`docs/handoff-smoke-test-git.md`** before real work. In short:
1. The repo is on the self-hosted **Gitea 1.27.3** on the project host (Arm 1). Accounts `ice`/`pok`/`donut` already exist as Write collaborators.
   - Clone on the host: `http://127.0.0.1:3000/gr11/cap-position.git`; remote: the tunnel URL (ephemeral).
   - Authenticate with a **personal access token** (the git password), never with the account password. Get a token by logging into the web UI once (Settings → Applications), or have the admin pre-generate one. SSH is disabled.
2. Clone only into the approved environment (question 1). Python 3.9 + `uv venv` + `pip install -r requirements.lock.txt`. Download data + weights per the README. Rebuild artifacts (~20 min).
3. Run `pytest` (27 pass). Run the server locally (`127.0.0.1`, auth optional).

## Workflow (propose to the user, then record)
- One feature branch per task (e.g. `feat/metadata-breakdown`). Open PRs to `main`, never push directly, and never force-push.
- Before every PR: `pytest`, `scripts/validate_predictions.py`, `scripts/score.py`. A PR that touches data access must include a data-rule test.
- Contract changes (new fields, new breakdowns) need a version bump in `docs/shared-contract.md` and an `aidlc-docs/audit.md` entry **in the same PR**.
- AI-DLC logging with several people: `audit.md` is append-only, so concurrent PRs will conflict. Suggestion: each session writes `aidlc-docs/audit/<date>-<handle>-<topic>.md`, and the index in `audit.md` is updated on merge. Ask the user to approve this layout before changing it.
- Never commit media, weights, `deploy.pkl` (unless Arm 1 decided otherwise), tokens or the share password.

## Rules to keep
- Contract §2:
  - Never identify people.
  - Refer to subjects only by `collector_id[:8]` in the UI.
  - Never read the three forbidden fields.
  - Media stays in the approved environment.
- Out-of-fold: nothing fitted for fold k may use fold k. `test_oof_never_uses_test_fold` enforces this.
- Arm 2 doesn't touch the running demo server or tunnel on this host, or the Stage B v2 run (`docs/hand-off-learning.md`), unless the user asks.
- Live-stream Phase 2 is still **gated** on the user.
