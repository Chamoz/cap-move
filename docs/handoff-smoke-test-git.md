# Hand-off — Smoke test: git login to Gitea — 2026-10-03T13:51Z

Purpose: a 2-minute check that a teammate's Gitea **token login works** before they start real
work. Read-only until the last optional step. Run it from the dev environment (host or your
approved machine). Replace **`<me>`** with your Gitea username (`ice` / `pok` / `donut`).

Prereqs: you have a token (see `docs/handoff-teammate.md`, Option A or B) and the current Gitea
URL. The tunnel URL is **ephemeral** — ask the user for the current one; as of 2026-10-03T13:51Z it
was `https://platforms-texas-spoke-europe.trycloudflare.com`.

```bash
export GIT_TOKEN='<your token>'          # never write this into a repo file
export GIT_USER='<me>'                    # ice | pok | donut
# choose ONE base URL:
export GIT_BASE='http://127.0.0.1:3000'                               # on the host
# export GIT_BASE='https://<tunnel-host>'                             # remote (fill in current URL)
HELP='!f() { echo username='"$GIT_USER"'; echo "password=$GIT_TOKEN"; }; f'
```

## Test 1 — token is accepted (authenticated read)
```bash
git -c credential.helper= -c credential.helper="$HELP" \
  ls-remote "$GIT_BASE/gr11/cap-position.git"
```
**PASS**: you see refs, e.g.
```
cb7d9f65...  HEAD
cb7d9f65...  refs/heads/main
78988808...  refs/tags/v1-stageA
```
**FAIL** `401 / Authentication failed` → wrong token or username. `could not resolve host` /
`connection refused` → wrong/stale URL or the server/tunnel is down (ask the user).

## Test 2 — a bad token is rejected (negative check)
```bash
GIT_TOKEN=definitely-not-valid git -c credential.helper= \
  -c credential.helper='!f() { echo username='"$GIT_USER"'; echo "password=$GIT_TOKEN"; }; f' \
  ls-remote "$GIT_BASE/gr11/cap-position.git" ; echo "exit=$?"
```
**PASS**: it fails with 401 and a non-zero exit. (Confirms auth is actually enforced, not open.)

## Test 3 — anonymous access is blocked
```bash
curl -s -o /dev/null -w "%{http_code}\n" "$GIT_BASE/gr11/cap-position.git/info/refs?service=git-upload-pack"
```
**PASS**: `401`. (A `200` would mean the repo is readable without a token — stop and tell the user.)

## Test 4 — a real clone (read) works
```bash
rm -rf /tmp/smoke-cap
git -c credential.helper= -c credential.helper="$HELP" \
  clone "$GIT_BASE/gr11/cap-position.git" /tmp/smoke-cap
ls /tmp/smoke-cap | head
# cleanup
rm -rf /tmp/smoke-cap
```
**PASS**: clone completes and the tree contains `README.md`, `src/`, `scripts/`.

## Test 5 (optional) — push permission via a no-op branch, then clean up
Confirms Write access AND that `main` is protected. Safe: it only touches a throwaway branch,
which is deleted at the end. Needs a token with `write:repository` scope.
```bash
rm -rf /tmp/smoke-cap && git -c credential.helper= -c credential.helper="$HELP" \
  clone "$GIT_BASE/gr11/cap-position.git" /tmp/smoke-cap
cd /tmp/smoke-cap
git checkout -b smoke/$GIT_USER-login
git commit --allow-empty -m "smoke: $GIT_USER login check"
git -c credential.helper= -c credential.helper="$HELP" push -u origin smoke/$GIT_USER-login
# (optional) prove main is protected — this SHOULD be rejected:
git checkout main
git commit --allow-empty -m "should be blocked"
git -c credential.helper= -c credential.helper="$HELP" push origin main ; echo "push-to-main exit=$? (non-zero = protected, good)"
# cleanup: delete the remote smoke branch and the local clone
git -c credential.helper= -c credential.helper="$HELP" push origin --delete smoke/$GIT_USER-login
cd / && rm -rf /tmp/smoke-cap
```
**PASS**: the branch push succeeds; the direct push to `main` is **rejected** (protected);
the smoke branch is deleted afterwards.

## Result
If Tests 1, 3, 4 pass (and 2 fails as expected), git login is working and you can proceed with
`docs/handoff-teammate.md`. If Test 5 was run, Write + branch protection are also confirmed.
Report any FAIL to the user with the exact command output. Never paste your token into chat, a
file, or a commit.
