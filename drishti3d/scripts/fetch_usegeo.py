#!/usr/bin/env python3
"""Download the UseGeo UAV benchmark from its Synology share.

The three download links in the UseGeo README open a JavaScript file browser,
not a file, so a plain `curl <link>` fetches an HTML shell. The share is a
Synology DSM folder share; this speaks its API directly:

  1. GET /sharing/<id>                       -> sets a `sharing_sid` cookie
  2. SYNO.Core.Sharing.Login                 -> activates the session
  3. SYNO.FolderSharing.List                 -> walks the tree, with sizes
  4. SYNO.FolderSharing.Download             -> fetches one file

Two details cost an hour to find and are easy to get wrong again:
`_sharing_id` and `folder_path` are sent **unquoted** to List, while `path` is
a **JSON array** for Download; and the download CGI is
`/fsdownload/webapi/file_download.cgi/<name>`, not the `/fsdownload/<id>/...`
the browser URL suggests.

The server's TLS certificate expired on 30 August 2024 (a genuine University
of Twente certificate from GEANT, simply not renewed), so verification is
disabled here. That is safe for this specific use -- the data is public,
CC BY-NC-SA licensed, and checked by size after download -- and it is why
`curl` without `-k` fails. The authors also note that institutional firewalls
often block port 5001.

Downloads resume, so an interrupted run can be repeated.

Usage:
  python scripts/fetch_usegeo.py --list 1
  python scripts/fetch_usegeo.py --dataset 1 --profile minimal --out datasets/public/usegeo
  python scripts/fetch_usegeo.py --dataset 1 --profile full
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HOST = "https://eostore.itc.utwente.nl:5001"
SHARES = {"1": "1gJRLdQ71", "2": "c4LlTkVjT", "3": "r4o1tdCNv"}

#: What to fetch. "minimal" is everything needed to reconstruct a mission and
#: score it against the LiDAR reference, and nothing else. The skipped items
#: are genuinely redundant: `Metashape_outputs_images` holds a second copy of
#: the same 224 images, `LiDAR_ODM_files` holds the raw scanner strips the
#: merged .las is built from, and `MVS_*.las` is the authors' own
#: photogrammetric result -- useful as a comparison, but not reference truth.
PROFILES = {
    "minimal": {
        "include": ["Camera_Inputs/", "Undistorted_images_full_res/",
                    "Depth_resized/", "LiDAR_dataset", "Image_orientations",
                    "trajectory"],
        "exclude": ["Metashape_outputs_images/", "LiDAR_ODM_files/", "MVS_"],
    },
    "reference-only": {          # just the truth, for scoring an existing run
        "include": ["LiDAR_dataset", "Camera_Inputs/", "Image_orientations",
                    "trajectory"],
        "exclude": ["Metashape_outputs_images/", "LiDAR_ODM_files/", "MVS_"],
    },
    "full": {"include": [""], "exclude": []},
}


def curl(args: list[str], *, capture=True) -> str:
    cmd = ["curl", "-sk", "--max-time", "0", *args]
    r = subprocess.run(cmd, capture_output=capture, text=capture)
    return r.stdout if capture else ""


def session(sid: str, tmp: Path) -> Path:
    jar = tmp / f"usegeo_{sid}.cookies"
    curl(["--max-time", "60", "-c", str(jar), "-o", "/dev/null",
          f"{HOST}/sharing/{sid}"])
    # Login, not Session.get: only Login grants the session the download CGI
    # checks. Session.get returns the share's metadata and leaves the cookie
    # unprivileged, so every download comes back as a 38-byte error JSON.
    curl(["--max-time", "60", "-b", str(jar), "-c", str(jar), "-o", "/dev/null",
          f"{HOST}/webapi/entry.cgi?api=SYNO.Core.Sharing.Login"
          f"&version=1&method=login&sharing_id=%22{sid}%22"])
    if not jar.exists() or "sharing_sid" not in jar.read_text():
        raise SystemExit(
            "could not open a session with the share.\n"
            "  The host is reachable on port 5001 but institutional firewalls\n"
            "  often block it -- the dataset authors say so themselves. Try a\n"
            "  home connection.")
    return jar


def api_list(sid: str, jar: Path, folder: str, *, tries: int = 4) -> list[dict]:
    """List one folder, retrying a dropped or empty reply.

    Walking a 1,100-file share is many requests over a link the dataset
    authors themselves describe as firewall-prone, and one empty response used
    to abort the whole run -- losing the tree walk, not just that folder.
    """
    q = urllib.parse.urlencode({
        "api": "SYNO.FolderSharing.List", "version": 2, "method": "list",
        "filetype": "all", "folder_path": folder, "_sharing_id": sid,
        "additional": '["size"]', "limit": 20000})
    last = ""
    for attempt in range(tries):
        out = curl(["--max-time", "300", "-b", str(jar),
                    f"{HOST}/webapi/entry.cgi?{q}"])
        try:
            d = json.loads(out)
        except json.JSONDecodeError:
            last = out[:200] or "(empty reply)"
            time.sleep(2 * (attempt + 1))
            continue
        if not d.get("success"):
            # A stale session is worth one silent re-login before giving up.
            if attempt == 0:
                session(sid, jar.parent)
                continue
            raise SystemExit(f"listing {folder} failed: {d.get('error')}")
        return d["data"]["files"]
    raise SystemExit(f"listing {folder} failed after {tries} tries: {last}")


def walk(sid: str, jar: Path, folder: str) -> list[dict]:
    """Every file under `folder`, depth-first, with its size."""
    out, stack = [], [folder]
    while stack:
        here = stack.pop()
        for f in api_list(sid, jar, here):
            if f["isdir"]:
                stack.append(f["path"])
            else:
                out.append(f)
    return out


def wanted(path: str, root: str, profile: dict) -> bool:
    rel = path[len(root):].lstrip("/")
    if any(x and x in rel for x in profile["exclude"]):
        return False
    return any(i == "" or i in rel for i in profile["include"])


def download(sid: str, jar: Path, remote: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    q = urllib.parse.urlencode({
        "api": "SYNO.FolderSharing.Download", "version": 2,
        "method": "download", "mode": "download", "stdhtml": "false",
        "path": json.dumps([remote]), "_sharing_id": sid})
    url = (f"{HOST}/fsdownload/webapi/file_download.cgi/"
           f"{urllib.parse.quote(dest.name)}?{q}")
    # -C - resumes a partial file; --retry survives a dropped connection.
    # A progress bar into a log file is thousands of useless lines; the
    # per-file line printed by the caller is the useful granularity there.
    progress = "--progress-bar" if sys.stderr.isatty() else "--silent"
    subprocess.run(["curl", "-k", "-L", "--fail", "-C", "-",
                    "--retry", "5", "--retry-delay", "5",
                    progress, "-b", str(jar), "-o", str(dest), url],
                   check=True)
    # The API answers HTTP 200 with a small JSON error body rather than a 4xx,
    # so --fail does not catch it and the file would look downloaded.
    if dest.stat().st_size < 4096:
        head = dest.read_bytes()[:200]
        if b'"success":false' in head or b'"error"' in head:
            dest.unlink()
            raise SystemExit(f"server refused {remote}: {head.decode(errors='replace')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=sorted(SHARES), help="1, 2 or 3")
    ap.add_argument("--list", dest="just_list", choices=sorted(SHARES),
                    help="print the tree and sizes, download nothing")
    ap.add_argument("--profile", default="minimal", choices=sorted(PROFILES))
    ap.add_argument("--out", default="datasets/public/usegeo")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be fetched and how much it is")
    a = ap.parse_args()
    if not a.dataset and not a.just_list:
        ap.error("one of --dataset or --list is required")

    which = a.just_list or a.dataset
    sid = SHARES[which]
    tmp = Path.home() / ".cache" / "drishti3d"
    tmp.mkdir(parents=True, exist_ok=True)
    jar = session(sid, tmp)
    root = f"/Dataset-{which}"

    print(f"listing {root} ...", flush=True)
    files = walk(sid, jar, root)
    total = sum(f["additional"]["size"] for f in files)
    print(f"{len(files)} files, {total / 1e9:.2f} GB in the share\n")

    if a.just_list:
        by_dir: dict[str, list[int]] = {}
        for f in files:
            d = f["path"].rsplit("/", 1)[0][len(root):].lstrip("/") or "."
            by_dir.setdefault(d, []).append(f["additional"]["size"])
        for d in sorted(by_dir):
            n, sz = len(by_dir[d]), sum(by_dir[d])
            print(f"  {d or '.':<45} {n:>5} files  {sz / 1e9:8.2f} GB")
        return 0

    prof = PROFILES[a.profile]
    picked = [f for f in files if wanted(f["path"], root, prof)]
    want = sum(f["additional"]["size"] for f in picked)
    print(f"profile '{a.profile}': {len(picked)} files, {want / 1e9:.2f} GB "
          f"({(total - want) / 1e9:.2f} GB skipped)\n")
    if a.dry_run:
        for f in picked[:20]:
            print("   ", f["path"])
        if len(picked) > 20:
            print(f"    ... and {len(picked) - 20} more")
        return 0

    out_root = Path(a.out) / f"dataset_{which}"
    done = 0
    for i, f in enumerate(picked, 1):
        rel = f["path"][len(root):].lstrip("/")
        dest = out_root / rel
        size = f["additional"]["size"]
        if dest.exists() and dest.stat().st_size == size:
            done += size
            continue
        print(f"[{i}/{len(picked)}] {rel}  ({size / 1e6:.1f} MB)", flush=True)
        download(sid, jar, f["path"], dest)
        got = dest.stat().st_size
        if got != size:
            print(f"    ! size mismatch: expected {size}, got {got}",
                  file=sys.stderr)
        done += got
    print(f"\ndone: {done / 1e9:.2f} GB under {out_root}")
    print("Licence: CC BY-NC-SA 4.0 -- research use, attribute UseGeo/ISPRS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
