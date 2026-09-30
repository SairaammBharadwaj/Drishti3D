"""Print a read-only machine/engine inventory before a laptop or Colab trial.

Run with the same Python interpreter/environment as the reconstruction worker.
Does not install software, load AI models, or start a reconstruction.
"""
from __future__ import annotations

import datetime
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return {"returncode": result.returncode,
                "output": (result.stdout + result.stderr).strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def main():
    out = {
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(), "python": platform.python_version(),
        "logical_cpus": os.cpu_count(),
        "allowed_cpus": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "cwd": os.getcwd(), "colmap_executable": shutil.which("colmap"),
        "thread_environment": {k: os.environ.get(k) for k in
                               ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "packages": {},
    }
    for package in ("pycolmap", "pycolmap-cuda12", "numpy", "scipy", "torch"):
        try:
            out["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            out["packages"][package] = None
    try:
        import pycolmap
        capability = getattr(pycolmap, "has_cuda", None)
        out["pycolmap_has_cuda"] = capability() if callable(capability) else capability
    except ImportError as exc:
        out["pycolmap_import_error"] = str(exc)
    for key, args in {
        "gpu": ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used", "--format=csv"],
        "gpu_processes": ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv"],
        "cpu": ["lscpu"], "memory": ["free", "-b"],
        "disk": ["df", "-B1", "."],
        "patch_match_help": ["colmap", "patch_match_stereo", "-h"],
        "fusion_help": ["colmap", "stereo_fusion", "-h"],
        "git_head": ["git", "rev-parse", "HEAD"],
        "git_status": ["git", "status", "--short"],
    }.items():
        out[key] = command(args)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
