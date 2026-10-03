# Hand-off — Teammate (team dev on CAP Activity Review Tool) — 2026-10-03T13:51Z

You are a developer on the CAP Activity Review Tool. The code lives on a self-hosted Gitea server
(set up in Arm 1). This file gets you from zero to a working clone and your first PR. Read it top
to bottom; pause at each ⛔ for the user.

Throughout, replace **`<me>`** with your own Gitea username — one of `ice`, `pok`, `donut`.

- Project context: `docs/hand-off-arm2-team-dev.md` (team workflow + the metadata-analysis feature).
- Contract (binding): `docs/shared-contract.md` v0.2. **Never** read `subject_ids`, `ipAddress`,
  `device_identifier`; never commit media, weights, `deploy.pkl`, tokens or passwords.

## Your account
- Gitea user: **`<me>`** (`ice` / `pok` / `donut`), a Write collaborator on `gr11/cap-position`.
- Changing your first-login password is optional (not forced). You were given it separately.
- Git authenticates with a **personal access token**, not your password. SSH is disabled.

## Will Kiro log in to git automatically?
**No — not on its own.** Kiro has no auto-connect to Gitea. A credential must be supplied **once**;
after that, every `git clone/fetch/push` Kiro runs is non-interactive (feels automatic).
- Getting a token is a **one-time** step: web UI once, OR the API with your password, OR the admin
  generates it. There is no way to mint a token with neither a password nor admin rights.
- After the token exists and is stored (below), **no web login** — Kiro uses it for all git.
Pick ONE option:

### Option B (default, most secure): you create your own token
1. Open the Gitea tunnel URL in a browser (ask the user for the current URL — it changes if the
   tunnel restarts) and sign in as `<me>`.
2. **Settings → Applications → Generate New Token**, name it e.g. `<me>-dev`, scope **`repo`**
   (read/write). Copy it (shown once).
3. `export GIT_TOKEN='<token>'`. **Do not paste it into any file in the repo.**

### Option A (optional, admin pre-generates — zero web login for you)
Admin `gr11` runs on the host and hands you the token out-of-band:
```bash
~/gitea/gitea admin user generate-access-token --config ~/gitea/app.ini \
  --username <me> --token-name <me>-dev --scopes write:repository
```
Treat it as a live secret: keep it only in `GIT_TOKEN`, never in a repo file, revoke when done.

## Clone (token = password; inline-URL creds are NOT used — the admin password has an `@`)
On the host:
```bash
export GIT_TOKEN='<your token>'
git -c credential.helper= \
  -c credential.helper='!f() { echo username=<me>; echo "password=$GIT_TOKEN"; }; f' \
  clone http://127.0.0.1:3000/gr11/cap-position.git
cd cap-position
```
Remote (replace `<tunnel-host>` with the current tunnel URL):
```bash
git -c credential.helper= \
  -c credential.helper='!f() { echo username=<me>; echo "password=$GIT_TOKEN"; }; f' \
  clone https://<tunnel-host>/gr11/cap-position.git
```
To make later git hands-free this session: `git config credential.helper 'cache --timeout=36000'`
(or `store` to persist to `~/.git-credentials` — plaintext, your call).

Before touching real work, run the login smoke test: `docs/handoff-smoke-test-git.md`.

## Set up (Python 3.9) — ⛔ confirm the dev environment with the user first
Contract §2.3: CAP media stays in the approved environment. Don't download data to a new machine
until the user confirms where the team develops (Arm 2, question 1).
```bash
uv venv --python 3.9 .venv && . .venv/bin/activate
pip install -r requirements.lock.txt        # CPU torch; do NOT install GUI opencv-python
# data: download cap_detection_handheld_val into data/ (README step 3), approved env only
# weights: yolo11n*.pt are in the clone; CLIP + R(2+1)D auto-download
# rebuild artifacts (~20 min): extract_features -> extract_clip -> train_oof -> validate -> score -> build_gallery
.venv/bin/python -m pytest -q                # expect 27 passed
```

## Your first task
See `docs/hand-off-arm2-team-dev.md` → "metadata analysis". ⛔ The user must first pick option
A/B/C there. Don't guess the scope.

## Workflow (hard rules)
- `main` is protected: **branch + PR only**, no direct push, no force-push.
  ```bash
  git checkout -b feat/<short-name>
  # ...changes...
  git add -p && git commit -m "..."
  git push -u origin feat/<short-name>      # uses the same credential helper
  # open a PR to main in the web UI (push prints a create-PR link)
  ```
- Before every PR: `pytest`, `scripts/validate_predictions.py predictions.json`,
  `scripts/score.py predictions.json`. Any PR touching data access adds a data-rule test.
- Contract changes (new fields/breakdowns) need a §version bump + an `aidlc-docs/audit.md` entry in
  the **same PR**. For multi-person logging, prefer `aidlc-docs/audit/<date>-<me>-<topic>.md` and
  update the index on merge (confirm the layout with the user).
- Never touch the running demo server (:8000) or its tunnel, the Gitea server/tunnel, or the
  Stage B v2 run, unless the user asks. Live-stream Phase 2 is gated.
