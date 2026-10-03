# Hand-off — Arm 1: deploy the code to a self-hosted git server — 2026-10-03T13:12Z

Project: CAP Activity Review Tool · Workspace: `/Workshop/cap-position` · Method: AI-DLC · Contract v0.2
Two arms:
- **Arm 1 (this note):** put the code in git.
- **Arm 2:** team development and metadata analysis (`docs/hand-off-arm2-team-dev.md`). Start Arm 2 only after Arm 1 is done.

Not part of this arm: Stage B v2 (`docs/hand-off-learning.md`). Don't start that download here.

## Decided by the user
- 13:04Z: the new session is authorized to deploy the code, including the **initial push to `main`** of the new empty repo. After that, feature branches and PRs.
- 13:05Z: **scope = everything except data** (table below).
- **13:11Z: self-hosted git instead of GitHub.** I had recommended GitHub; the user chose self-hosting.

## Self-hosted design (recommended; confirm with the user first)
**Gitea**: MIT-licensed, a single binary with SQLite. It gives web PRs, code review, issues and branch protection for free.

Host facts (checked 13:11Z):
- Amazon Linux 2023, user `participant`.
- **No sudo**, so no system packages, OS users or firewall changes.
- `sshd` is listening on :22. Docker can be used without sudo. Port 3000 is free. No `crontab`.

| Choice | Value | Why |
|---|---|---|
| Install | Pinned Gitea release binary (linux-amd64) in `~/gitea/`, **sha256 verified** against the release checksum. Run as `participant`. | No sudo needed. Skip Docker: membership of the docker group is root-equivalent, and a container adds nothing here. |
| Data dir | `~/gitea/data` (SQLite + repos), **outside the workspace** | It can never be committed |
| Bind | `HTTP_ADDR=127.0.0.1`, `HTTP_PORT=3000` | Not reachable from the network unless tunnelled |
| SSH | `DISABLE_SSH=true` (HTTPS git only) | **Never** add teammates' keys to `participant`'s `authorized_keys`: that gives a full shell, including the data, the server and the share password environment. |
| Hardening | `INSTALL_LOCK=true`, `DISABLE_REGISTRATION=true`, `REQUIRE_SIGNIN_VIEW=true`, `OFFLINE_MODE=true`, repos private by default | Only accounts the admin creates can see anything |
| Run | `setsid nohup ~/gitea/gitea web --config ~/gitea/app.ini > ~/gitea/gitea.log 2>&1 < /dev/null &`, pid in `~/gitea/gitea.pid` | Same pattern as the app server. **Never use `pkill -f`.** |
| Team access | Option 1: teammates work **on this host** (code-server) and clone from `http://127.0.0.1:3000`, with no exposure at all. Option 2: a cloudflared tunnel to :3000 gives HTTPS for remote clones. | Option 1 also settles the contract §2.3 media question for Arm 2 |

### Risks to tell the user before installing
1. **Durability.** This looks like a workshop instance. If it's stopped or terminated, the repo is lost. Mitigation: after every push, write a `gitea dump` and a `git bundle` to `~/gitea-backups/`.
   - **Ask** whether to also copy the bundle off-host. A dedicated private S3 bucket costs cents (code only, no media); never use the CDK bootstrap bucket. Getting the user's approval first is required.
   - No `crontab`, so backups run at the end of each session or from a small `setsid` loop.
2. **Ephemeral URL** (Option 2). A quick-tunnel URL changes every time it restarts, and then Gitea's `ROOT_URL` and teammates' remotes must be updated. A durable URL needs a named Cloudflare Tunnel (the user's Cloudflare account and domain) or an AWS security-group change. Both need the user's approval.
3. **Another network service** to keep patched (Option 2 only). Check Gitea security releases, and pin and record the version.

## Still needed from the user at the start of the new session
1. Confirm Gitea with Option 1 (on-host only) or Option 2 (tunnel for remote teammates).
2. Owner/org name and repo name (default `cap-position`), and the teammates' usernames and emails for the accounts.
3. Off-host backup: yes (S3 bucket, needs a cost OK) or no.
4. Feature cache: push it or not (see the table; I recommend not).
5. Whether to redact the share username `gr11` from the docs.

## Push scope: everything except data (user, 13:05Z)
| Push | Item | Size |
|---|---|---|
| ✅ | Code, docs, contract, manifest, `predictions.json` | 0.35 MB |
| ✅ | `weights/yolo11n.pt`, `weights/yolo11n-pose.pt`. Add `.gitignore` exceptions. They're AGPL-3.0, so keep the license note in the README and `docs/weights.md`. | 11.4 MB |
| ✅ | `artifacts/model/deploy.pkl` + `oof_detail.json`, so analysis runs right after clone + data download | 0.1 MB |
| ✅ | `artifacts/report/*`, `artifacts/gallery/index.json` (numbers only) | 0.1 MB |
| ❌ | `artifacts/gallery/thumbs/` (crops of people) and `artifacts/uploads/` (uploaded and **webcam** videos). These are pixels, which contract §2.3 forbids. | 1.5 + 32 MB |
| ❌ | CLIP `ViT-B-32.pt` 338 MB and R(2+1)D 120 MB. Large, and they auto-download on first use (sha256s in `docs/weights.md`) | 458 MB |
| ❌ | `.venv/` (1.4 GB, recreate from `requirements.lock.txt`), logs, pids, `tunnel.log`, `reviews.jsonl` | — |
| ❓ ask | `artifacts/features/`: per-frame **pose keypoints and CLIP embeddings of people's crops** (§2.1/§2.3). Recommend **don't push**; it rebuilds in ~15 min. | 6.3 MB |

Before committing, `git diff --cached --stat` must show only the ✅ paths.

## Current state (checked 12:30–13:11Z)
- **No git repo yet.** `git` 2.50.1 is installed. Global `user.name` and `user.email` are set; leave the global git config as it is. No SSH key exists.
- The current `.gitignore` already excludes `data/`, `artifacts/`, `weights/`, `*.pt`, `*.pkl`, `*.mp4`, `*.mov`, `.venv/` and `__pycache__/`. The ✅ weights and artifacts need explicit negation rules.
- Scans of the code that would be committed:
  - no AWS keys, private keys or share password;
  - the forbidden fields appear only as *names* in code that excludes them;
  - the manifest holds pseudonymous `collector_id`s (allowed under CC BY 4.0);
  - `gr11` appears in two docs.

## Steps
1. Re-check the live app server and tunnel (`docs/hand-off-learning.md`). Append the user's message to `aidlc-docs/audit.md`. Confirm the open questions above.
2. **Install Gitea** (design table):
   - Download the pinned release and verify its sha256. Write `~/gitea/app.ini` with the hardening settings, then start it.
   - Check `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/` returns 200 and `/explore/repos` returns 303 to login.
   - Create the admin:
     ```
     ~/gitea/gitea admin user create --config ~/gitea/app.ini --admin \
       --username <owner> --email <email> --random-password --must-change-password
     ```
     **Warn the user before showing the one-time password**: it's exposed once it appears in chat, so they must change it at first login. Logging in needs the tunnel (Option 2), or code-server port forwarding of :3000 (Option 1).
   - Create the empty private repo through the API or `gitea admin`.
3. **Push credential**: `gitea admin user generate-access-token --username <owner> --token-name cap-push --scopes write:repository`. It's generated on the host, so **the user never pastes it**. Keep it only in a shell variable, never in a file, URL, log or chat.
4. Harden `.gitignore`. Add `.pytest_cache/`, `*.log`, `*.pid`, `.env*`, `*.webm`, `*.avi` and `*.m4v`, plus negation rules for the ✅ artifacts.
5. Run `git init -b main` and stage **specific paths only**, never `git add .`.
   Before committing, check:
   - a secret scan (the password, `AKIA`, private-key headers);
   - that `git diff --cached --stat` matches the ✅ list, with no file over 7 MB;
   - `pytest` (27 tests), `scripts/validate_predictions.py`, `scripts/score.py`.
6. Commit `Stage A review tool: OOF predictions, review UI, webcam capture, auth`, tag `v1-stageA`, then push:
   ```
   git remote add origin http://127.0.0.1:3000/<owner>/cap-position.git
   GIT_TOKEN="$TOKEN" git -c credential.helper= \
     -c credential.helper='!f() { echo username=<owner>; echo "password=$GIT_TOKEN"; }; f' \
     push -u origin main --tags
   ```
   **Never force-push.** Afterwards, delete the `cap-push` token in Gitea, or leave it in place only if the user wants it kept.
7. Verify:
   - `git ls-remote origin` shows the commit and the tag;
   - a fresh clone into `/tmp` matches the ✅ list and contains no media; delete it afterwards;
   - an anonymous request to the repo URL returns 404 or a login redirect.
8. Enable **branch protection** on `main` in Gitea (PR required, no force-push). Create the teammates' accounts with `--must-change-password` and add them as collaborators (Write).
9. Option 2 only: start a second cloudflared quick tunnel to :3000 (pid in `~/gitea/tunnel.pid`), set `ROOT_URL` to its URL, restart Gitea, and send the clone URL to the user.
10. Backups: run `gitea dump` and `git bundle create ~/gitea-backups/cap-position-<utc>.bundle --all`. Then do the off-host copy only if the user approved it.
11. Add a README section "Getting started from git" and push it as a second commit through a branch and PR, to test the workflow. It covers:
    - clone URL and access;
    - Python 3.9, `uv venv`, `pip install -r requirements.lock.txt`;
    - the CAP val data download into `data/`;
    - CLIP and R(2+1)D auto-download;
    - the rebuild order for the excluded artifacts;
    - running the server with or without `CAP_AUTH_*`.
12. Log the Gitea version, repo URL (no token), commit SHA, tag and backup location in `audit.md`, `aidlc-state.md` and `effort-log.md`. Then tell the user Arm 1 is done and that `docs/hand-off-arm2-team-dev.md` is next.

## Team readiness: what a clone does NOT contain
| Gap | README must say |
|---|---|
| CAP val data (0.9 GB) | Download from https://visym.github.io/cap (check the MD5) into `data/cap_detection_handheld_val/`. **The tests need it**, because `server.py` loads it on import. Contract §2.3: only into an approved environment (Arm 2, question 1). |
| CLIP and R(2+1)D weights | They auto-download on first use; check the sha256s in `docs/weights.md` |
| Feature cache, gallery thumbnails | Rebuild: `extract_features` (~11 min) → `extract_clip` (~3 min) → `train_oof` (~4 min) → `validate_predictions` → `score` → `build_gallery` (~1.5 min) |
| Environment | Python 3.9, `uv`, `requirements.lock.txt` (all runtime and test packages are pinned and were checked). Never install GUI `opencv-python`. |
| Host-only state | The app server and tunnel, `reviews.jsonl`, and the Stage B v2 run stay on this host |

## Rules to keep
- Contract §2.3: **no media in git**, ever, including history. If media gets committed, stop and ask before rewriting history.
- Credentials: never commit or echo the share password, Gitea passwords or tokens. Don't change the global git config. Don't use `--no-verify`.
- Ask the user before any AWS resource (S3 bucket, security-group change) or a named Cloudflare tunnel.
- Don't change application behaviour in this arm. Docs and `.gitignore` changes only.
- Keep the running app server (:8000) and its tunnel up. Gitea runs alongside them.
