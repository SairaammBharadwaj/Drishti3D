"""One evidence package for a finished mission: what ran, on what, and what it rests on.

    python scripts/evidence_package.py data/projects/<id>/artifacts \\
        [--video path/to/input.mp4] [--run-tests "pytest -q tests/test_rasters.py"]

Writes ``evidence_package.json`` (and ``evidence_package.md``) beside the
artifacts. It gathers, without inventing anything:

* the input video's SHA-256, re-hashed from ``--video`` when given and checked
  against the run's manifest;
* the machine: CPU, RAM, GPU (``nvidia-smi``), OS, Python and key packages;
* stage timings and end-to-end wall time (``timing.json``) against video length;
* a SHA-256 of every output file;
* CRS, vertical datum, placement source (``georeference.json``);
* the accuracy policy and truth source (``accuracy.json`` if a checkpoint
  report exists; otherwise it says there is none);
* the test command and its result, when ``--run-tests`` is given.

Anything missing is recorded as missing with the reason, so a reviewer can see
the gap rather than an empty field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Files that are logs or this package itself, not outputs to hash.
_SKIP = {"evidence_package.json", "evidence_package.md"}

ACCURACY_POLICY = (
    "Absolute accuracy is reported only against surveyed points. Points used to fit a "
    "correction (GCPs) are never reported as independent accuracy; their residuals and "
    "leave-one-out scores are labelled as such. GNSS alignment residuals are not "
    "accuracy. An ASPRS accuracy class needs at least 30 independent checkpoints.")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _cmd(args, timeout=20) -> str | None:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def hardware() -> dict:
    cpu = platform.processor() or None
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    ram = None
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal"):
                ram = round(int(line.split()[1]) / 1024 / 1024, 1)
                break
    except OSError:
        pass
    gpu = _cmd(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader"])
    return {"cpu": cpu, "cpu_count": os.cpu_count(), "ram_gb": ram,
            "gpu": gpu.splitlines() if gpu else None,
            "gpu_note": None if gpu else "nvidia-smi not available: no NVIDIA GPU recorded",
            "os": platform.platform(), "python": sys.version.split()[0]}


def packages() -> dict:
    from importlib import metadata
    out = {}
    for name in ("numpy", "scipy", "opencv-python-headless", "pyproj", "laspy",
                 "rasterio", "open3d", "pycolmap", "torch", "fastapi"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    out["colmap"] = _cmd(["colmap", "-h"], 10)
    if out["colmap"]:
        out["colmap"] = out["colmap"].splitlines()[0]
    out["assimp"] = (_cmd(["assimp", "version"], 10) or "").splitlines()[1:2] or None
    return out


def run_tests(command: str) -> dict:
    t0 = time.time()
    r = subprocess.run(shlex.split(command), capture_output=True, text=True, cwd=ROOT)
    tail = (r.stdout + r.stderr).strip().splitlines()
    summary = next((l for l in reversed(tail) if " passed" in l or " failed" in l
                    or " error" in l), tail[-1] if tail else "")
    return {"command": command, "exit_code": r.returncode, "summary": summary.strip("= "),
            "seconds": round(time.time() - t0, 1), "passed": r.returncode == 0}


def build(art: Path, video: Path | None = None, tests: str | None = None) -> dict:
    art = Path(art)
    manifest = _load(art / "manifest.json") or {}
    geo = _load(art / "georeference.json") or {}
    timing = _load(art / "timing.json")
    quality = _load(art / "quality_report.json") or {}
    acc = _load(art / "accuracy.json")
    rasters = _load(art / "rasters.json")
    mesh = _load(art / "mesh_formats.json")

    vid = {"sha256_manifest": manifest.get("video_sha256")}
    if video:
        vid["path"] = str(video)
        vid["sha256_file"] = sha256(Path(video))
        vid["matches_manifest"] = vid["sha256_file"] == vid["sha256_manifest"]
    vid["duration_s"] = (timing or {}).get("video_s") or (
        quality.get("performance") or {}).get("video_duration_s")

    outputs = {}
    for p in sorted(art.iterdir()):
        if p.is_file() and p.name not in _SKIP:
            outputs[p.name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}

    if timing:
        timings = {"source": "timing.json (one monotonic clock)",
                   "wall_s": timing.get("wall_s"), "video_s": timing.get("video_s"),
                   "wall_over_video": timing.get("wall_over_video"),
                   "stages_s": timing.get("stages_s")}
    else:
        perf = quality.get("performance") or {}
        timings = {"source": "quality_report.json stage sum (understates end-to-end; "
                             "timing.json absent)",
                   "wall_s": perf.get("processing_time_s"),
                   "video_s": perf.get("video_duration_s"),
                   "stages_s": quality.get("timings_s")}

    if acc:
        truth = {"source": acc.get("truth_source"), "headline": acc.get("headline"),
                 "n_gcp": acc.get("n_gcp"), "n_check": acc.get("n_check"),
                 "asprs": acc.get("asprs"),
                 "artifact_revision": acc.get("revision"),
                 "note": "GET /api/projects/<id>/accuracy reports whether this "
                         "revision is still the current reconstruction"}
    else:
        gt = quality.get("ground_truth_evaluation")
        truth = {"source": None,
                 "note": "no checkpoint report (accuracy.json) for this mission; absolute "
                         "accuracy is not established by this package",
                 "ground_truth_evaluation": gt}

    pkg = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifacts_dir": str(art),
        "input_video": vid,
        "hardware": hardware(),
        "software": packages(),
        "params": manifest.get("params"),
        "timings": timings,
        "georeference": {
            "georeferenced": geo.get("georeferenced"),
            "projected_crs": geo.get("projected_crs") or (rasters or {}).get("crs"),
            "vertical_datum": geo.get("vertical_datum") or manifest.get("vertical_datum"),
            "vertical_reference": geo.get("vertical_reference"),
            "vertical_datum_basis": geo.get("vertical_datum_basis")
                                    or manifest.get("vertical_datum_basis"),
            "placement_source": geo.get("scale_source"),
        },
        "truth": truth,
        "accuracy_policy": ACCURACY_POLICY,
        "display_only": {
            "mesh": (mesh or {}).get("caveat"),
            "fill": "inferred hole fill is a separate layer (fill.npz) and never answers "
                    "a measurement" if (art / "fill.npz").exists() else None,
        },
        "outputs": outputs,
        "warnings": manifest.get("warnings"),
    }
    if tests:
        pkg["tests"] = run_tests(tests)
    return pkg


def to_markdown(pkg: dict) -> str:
    v, t, g, tr = pkg["input_video"], pkg["timings"], pkg["georeference"], pkg["truth"]
    hw = pkg["hardware"]
    lines = [
        "# Evidence package", "",
        f"Generated {pkg['generated_utc']} from `{pkg['artifacts_dir']}`.", "",
        "## Input",
        f"- Video SHA-256 (manifest): `{v.get('sha256_manifest')}`",
    ]
    if "sha256_file" in v:
        lines.append(f"- Video SHA-256 (re-hashed): `{v['sha256_file']}` — "
                     + ("matches" if v["matches_manifest"] else "**DOES NOT MATCH**"))
    lines += [f"- Duration: {v.get('duration_s')} s", "", "## Machine",
              f"- CPU: {hw['cpu']} ({hw['cpu_count']} threads), RAM {hw['ram_gb']} GB",
              f"- GPU: {', '.join(hw['gpu']) if hw['gpu'] else hw['gpu_note']}",
              f"- OS: {hw['os']}, Python {hw['python']}", "", "## Timing",
              f"- Source: {t['source']}",
              f"- Wall: {t.get('wall_s')} s for {t.get('video_s')} s of video"
              + (f" ({t['wall_over_video']}x)" if t.get("wall_over_video") else ""), ""]
    for k, s in (t.get("stages_s") or {}).items():
        lines.append(f"  - {k}: {s} s")
    lines += ["", "## Placement",
              f"- Georeferenced: {g['georeferenced']}; CRS {g['projected_crs']}",
              f"- Vertical datum: {g['vertical_datum']} ({g['vertical_datum_basis']})",
              f"- Placement source: {g['placement_source']}", "", "## Truth and accuracy",
              f"- Truth source: {tr.get('source') or 'none'}"]
    if tr.get("headline"):
        lines.append(f"- {tr['headline'].get('text')}")
        if tr["headline"].get("warning"):
            lines.append(f"- **{tr['headline']['warning']}**")
    if tr.get("note"):
        lines.append(f"- {tr['note']}")
    lines += [f"- Policy: {pkg['accuracy_policy']}", ""]
    if pkg.get("tests"):
        tt = pkg["tests"]
        lines += ["## Tests", f"- `{tt['command']}` → {tt['summary']} "
                  f"(exit {tt['exit_code']}, {tt['seconds']} s)", ""]
    lines += ["## Outputs", "", "| File | Bytes | SHA-256 |", "|---|---:|---|"]
    for name, o in pkg["outputs"].items():
        lines.append(f"| {name} | {o['bytes']} | `{o['sha256'][:16]}…` |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifacts", type=Path)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--run-tests", dest="tests")
    a = ap.parse_args(argv)
    pkg = build(a.artifacts, a.video, a.tests)
    (a.artifacts / "evidence_package.json").write_text(json.dumps(pkg, indent=2))
    (a.artifacts / "evidence_package.md").write_text(to_markdown(pkg))
    print(f"wrote {a.artifacts / 'evidence_package.json'} and .md")
    if "matches_manifest" in pkg["input_video"] and not pkg["input_video"]["matches_manifest"]:
        print("WARNING: the video does not match the one this run processed")
        return 2
    if pkg.get("tests") and not pkg["tests"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
