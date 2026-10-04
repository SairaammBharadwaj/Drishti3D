"""Reading a showcase bundle written by ``scripts/export_showcase.py``.

A bundle is an ordinary data directory -- ``drishti3d.db`` and
``projects/<id>/artifacts`` -- plus ``showcase.json``, which records what was
exported, the credit each mission's source requires on a public page, and the
size and modification time of every artifact file.

The times matter. A stored answer carries the artifact revision it was computed
against, and the revision is built from artifact sizes and modification times
(``storage.artifact_revision``). Uploading or unpacking a bundle resets those
times, so every published answer would read as superseded by a reconstruction
that never happened. :func:`restore_times` puts them back when the server
starts; a file whose size differs is left alone, because then it really has
changed and superseded is the truth.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

MANIFEST = "showcase.json"
FORMAT = 1

log = logging.getLogger(__name__)


def load(data_dir: Path) -> dict | None:
    p = Path(data_dir) / MANIFEST
    if not p.is_file():
        return None
    m = json.loads(p.read_text())
    if m.get("format") != FORMAT:
        raise ValueError(f"{p}: showcase format {m.get('format')!r}, "
                         f"this server reads {FORMAT}")
    return m


def restore_times(data_dir: Path) -> int:
    """Reset artifact modification times to the exported ones; returns how many."""
    m = load(data_dir)
    if m is None:
        return 0
    restored = 0
    for pid, proj in m["projects"].items():
        art = Path(data_dir) / "projects" / pid / "artifacts"
        for name, rec in proj["files"].items():
            f = art / name
            try:
                st = f.stat()
            except FileNotFoundError:
                log.warning("showcase: %s/%s is missing", pid, name)
                continue
            if st.st_size != rec["size"]:
                log.warning("showcase: %s/%s changed size since export; its "
                            "stored answers will read as superseded", pid, name)
                continue
            if st.st_mtime_ns != rec["mtime_ns"]:
                try:
                    os.utime(f, ns=(rec["mtime_ns"], rec["mtime_ns"]))
                    restored += 1
                except OSError as exc:
                    log.warning("showcase: cannot restore time of %s/%s: %s",
                                pid, name, exc)
    return restored


def credits(data_dir: Path) -> list[str]:
    """The credit lines the published missions' sources require, in order."""
    m = load(data_dir)
    if m is None:
        return []
    used = {p["dataset"] for p in m["projects"].values()}
    return [text for key, text in m["credits"].items() if key in used]
