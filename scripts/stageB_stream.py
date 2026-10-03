#!/usr/bin/env python3
"""Stage B (v2) — FULL streaming analysis + extraction of cap_classification_clip.tar.gz.

Streams the archive once (tar.gz is non-seekable, no S3 index), and for every member:
  * records it in an append-only, fsync'd ledger  -> the durable METADATA INVENTORY;
  * keeps every non-mp4 member verbatim (+ sha256) -> that's where collector metadata
    would live, if anywhere;
  * for mp4 members mapped to one of the 8 contract classes, extracts the clip to
    data/stageB_v2/videos/<class>/<name> (atomic write) and parses the mp4 udta/meta/ilst
    atoms to inventory any embedded metadata keys (the per-clip collector_id search).

CHECKPOINTING (approved model B, member-level idempotency; see audit 2026-10-03T12:52Z):
  * atomic clip writes (*.part -> os.rename); stray *.part swept on startup;
  * append-only members ledger (artifacts/v2/members.jsonl), fsync'd periodically;
  * atomic progress file (artifacts/v2/stream_state.json);
  * resume = re-run: already-finished clips are skipped (network re-pull is unavoidable
    because gzip/tar cannot resume mid-stream, but no clip/metadata is re-processed/lost);
  * disk guard: clean pause (status=paused_disk) below MIN_FREE_GB;
  * SIGTERM/SIGINT -> flush ledger+state, status=stopped, exit (never pkill -f this).

Output lives ONLY under data/stageB_v2/ and artifacts/v2/. v1 is never touched.
Writes NO personal attributes to any manifest; it only *reports whether* a collector_id
field exists, so the §7 gate can be decided.
"""
import json
import os
import signal
import struct
import subprocess
import sys
import tarfile
import time
import hashlib
from collections import Counter

# --- repo imports (reuse the single source of truth for label mapping) ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.build_manifest import map_label, CLASSES  # noqa: E402

URL = ("https://consented-activities-of-people.s3.us-west-2.amazonaws.com/"
       "train/cap_classification_clip.tar.gz")
ARCHIVE_SIZE = 308_736_485_473  # bytes, from s3api head (for % progress)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data", "stageB_v2")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")
NONMP4_DIR = os.path.join(DATA_DIR, "nonmp4")        # verbatim copies of any non-mp4 member
ART_DIR = os.path.join(ROOT, "artifacts", "v2")
LEDGER = os.path.join(ART_DIR, "members.jsonl")
STATE = os.path.join(ART_DIR, "stream_state.json")
PIDFILE = os.path.join(ART_DIR, "stream.pid")
META_KEYS = os.path.join(ART_DIR, "mp4_meta_keys.json")  # histogram of mp4 metadata keys seen

MIN_FREE_GB = 10
STATE_EVERY = 200       # members between state/ledger flushes
MAX_CLIPS_PER_CLASS = None  # None = keep all during analysis; subsample happens later

# keys that would indicate a recoverable collector/subject identity
IDENTITY_HINTS = ("collector", "collection", "subject", "device", "ipaddress",
                  "uploader", "author", "user", "owner", "artist", "comment", "cprt")

_stop = {"flag": False, "reason": None}


def _sig(signum, frame):
    _stop["flag"] = True
    _stop["reason"] = f"signal {signum}"


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


def free_gb(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, path)


def parse_mp4_meta(blob):
    """Return a dict of printable mp4 udta/meta/ilst metadata atoms, best-effort.
    We only surface KEYS and short printable VALUES, never raw pixel/audio data."""
    out = {}
    # Find 'ilst' then walk its child atoms: each is [size(4)][key(4)]...[data box].
    i = blob.find(b"ilst")
    if i < 0:
        return out
    j = i + 4
    end = len(blob)
    for _ in range(64):  # cap
        if j + 8 > end:
            break
        try:
            size = struct.unpack(">I", blob[j:j + 4])[0]
        except struct.error:
            break
        key = blob[j + 4:j + 8]
        if size < 8 or j + size > end:
            break
        payload = blob[j + 8:j + size]
        # the value is inside a 'data' box: [size][b'data'][4 type][4 locale][value]
        d = payload.find(b"data")
        val = b""
        if d >= 0 and d + 12 <= len(payload):
            val = payload[d + 12:]
        text = "".join(chr(c) if 32 <= c < 127 else "." for c in val[:120])
        out[key.decode("latin1", "replace")] = text
        j += size
    return out


def main():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(NONMP4_DIR, exist_ok=True)
    os.makedirs(ART_DIR, exist_ok=True)
    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))

    # --- resume: build skip-set of already-finished clips; sweep stray .part ---
    done = set()
    for base, _dirs, files in os.walk(VIDEO_DIR):
        for f in files:
            if f.endswith(".part"):
                try:
                    os.remove(os.path.join(base, f))
                except OSError:
                    pass
            else:
                done.add(f)

    meta_key_hist = Counter()
    identity_findings = []   # (member_name, key, value) for any identity-looking metadata
    counts = Counter()
    members_seen = 0
    clips_written = len(done)
    nonmp4_seen = 0
    t0 = time.time()
    status = "running"

    # streaming source: curl -> stdout; tarfile in streaming mode (r|gz, no seek)
    curl = subprocess.Popen(
        ["curl", "-sS", "--fail", "--retry", "5", "--retry-delay", "5",
         "--max-time", "86400", URL],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1024 * 1024,
    )

    led = open(LEDGER, "a", buffering=1024 * 1024)

    def flush(st):
        led.flush()
        os.fsync(led.fileno())
        atomic_write_json(STATE, {
            "status": st,
            "members_seen": members_seen,
            "clips_written": clips_written,
            "nonmp4_seen": nonmp4_seen,
            "bytes_estimate_total": ARCHIVE_SIZE,
            "per_class_counts": dict(counts),
            "elapsed_s": round(time.time() - t0, 1),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "identity_metadata_found": bool(identity_findings),
            "identity_findings_sample": identity_findings[:20],
        })
        atomic_write_json(META_KEYS, dict(meta_key_hist))

    try:
        tf = tarfile.open(fileobj=curl.stdout, mode="r|gz")
        for m in tf:
            members_seen += 1
            if _stop["flag"]:
                status = "stopped"
                break
            if free_gb(DATA_DIR) < MIN_FREE_GB:
                status = "paused_disk"
                break

            name = m.name
            is_mp4 = m.isfile() and name.lower().endswith(".mp4")
            rec = {"name": name, "size": m.size, "is_dir": m.isdir(),
                   "is_mp4": is_mp4}

            if m.isfile() and not is_mp4:
                # NON-MP4 member: this is where sidecar collector metadata would be.
                nonmp4_seen += 1
                blob = tf.extractfile(m).read()
                rec["sha256"] = hashlib.sha256(blob).hexdigest()
                safe = name.replace("/", "__")
                with open(os.path.join(NONMP4_DIR, safe), "wb") as fh:
                    fh.write(blob)
                low = blob[:4096].lower()
                rec["identity_hint"] = [h for h in IDENTITY_HINTS if h.encode() in low]
                if rec["identity_hint"]:
                    identity_findings.append({"member": name, "where": "nonmp4",
                                              "hints": rec["identity_hint"]})

            elif is_mp4:
                raw_label = name.split("/")[-2] if "/" in name else ""
                cls = map_label(raw_label)
                rec["raw_label"] = raw_label
                rec["class"] = cls
                if cls is not None:
                    fname = os.path.basename(name)
                    outdir = os.path.join(VIDEO_DIR, cls)
                    final = os.path.join(outdir, fname)
                    if fname in done:
                        rec["skipped_existing"] = True
                    else:
                        os.makedirs(outdir, exist_ok=True)
                        data = tf.extractfile(m).read()
                        part = final + ".part"
                        with open(part, "wb") as fh:
                            fh.write(data)
                        os.rename(part, final)
                        done.add(fname)
                        clips_written += 1
                        counts[cls] += 1
                        # inline per-clip metadata inventory (collector_id search)
                        meta = parse_mp4_meta(data)
                        for k, v in meta.items():
                            meta_key_hist[k] += 1
                            if any(h in (k + v).lower() for h in IDENTITY_HINTS):
                                identity_findings.append({"member": name, "where": "mp4_meta",
                                                          "key": k, "value": v})
                        rec["mp4_meta_keys"] = list(meta.keys())

            led.write(json.dumps(rec) + "\n")
            if members_seen % STATE_EVERY == 0:
                flush(status)

        else:
            status = "complete"
    except tarfile.ReadError as e:
        # Truncated gzip/tar stream. Expected when we were signalled to stop (curl killed),
        # otherwise a mid-stream network interruption -> resumable, not a hard error.
        if _stop["flag"]:
            status = "stopped"
        else:
            status = "interrupted"
        led.write(json.dumps({"note": "stream_truncated", "detail": repr(e),
                              "stop_flag": _stop["flag"]}) + "\n")
    except Exception as e:  # noqa: BLE001
        status = "error"
        led.write(json.dumps({"error": repr(e)}) + "\n")
    finally:
        rc = None
        try:
            curl.terminate()
            rc = curl.poll()
        except Exception:
            pass
        if status == "running":
            status = "stopped" if _stop["flag"] else status
        flush(status)
        led.close()
        print(f"status={status} members={members_seen} clips={clips_written} "
              f"nonmp4={nonmp4_seen} identity_found={bool(identity_findings)} curl_rc={rc}")


if __name__ == "__main__":
    main()
