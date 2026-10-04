#!/usr/bin/env python3
"""Assemble the folder a read-only showcase image is built from.

The folder is both the Docker build context (deploy/showcase/Dockerfile) and,
unchanged, the contents of a Hugging Face Space. It holds exactly what the image
needs -- the backend, the ``drishti_recon`` package, the frontend source and a
bundle from ``export_showcase.py`` -- and a Space card crediting each dataset.
Whatever is in it becomes public when uploaded, so it is assembled from an
allow-list rather than by excluding things from the repository.

Left out on purpose: the Gymnasium footage and everything made from it
(``public/prototype``, the home page's comparison still). It came from
Wikimedia Commons under CC BY-SA, and its author was never recorded, so it
cannot be credited on a public page. The showcase UI hides the parts that use it.

Usage (from the drishti3d directory):
  .venv/bin/python scripts/export_showcase.py --out data/showcase
  .venv/bin/python scripts/build_space.py --bundle data/showcase --out data/space
  docker build -t drishti3d-showcase data/space
  docker run --rm -p 7860:7860 --memory 6g drishti3d-showcase     # http://127.0.0.1:7860

Publish (your Hugging Face account; create a blank Docker Space first):
  huggingface-cli login
  huggingface-cli upload <you>/<space> data/space . --repo-type=space
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]           # drishti3d/
sys.path.insert(0, str(APP / "backend"))

from app import showcase                              # noqa: E402

#: Present in every folder this script writes; --replace deletes nothing else.
MARKER = ".drishti3d-space"

FRONTEND_FILES = ["package.json", "package-lock.json", "index.html",
                  "tsconfig.json", "tsconfig.node.json", "vite.config.ts"]
#: Frontend assets that must not be published (see the module docstring).
UNCREDITED = {"public/prototype", "public/showcase/comparison.jpg"}

CARD = """---
title: Drishti3D Showcase
emoji: 🛰️
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
license: other
short_description: Single-pass drone video to measurable, georeferenced 3D
---

# Drishti3D: read-only showcase

Finished reconstructions from single drone passes. Open a mission to explore
the point cloud, read its quality report and evidence, and measure it. Each
measurement carries its propagated uncertainty and acceptance status.

This is a read-only showcase. Nothing can be uploaded or processed, and
measurements a visitor makes are private to their browser and temporary.
Source videos are not included.

## Data credits

{credits}

Reconstructions derived from these datasets are shared under the same terms.
The CC BY-NC-SA material may not be used commercially.

Exported {exported_at} from code version `{code_version}`.
"""

#: Large binaries go through LFS when this folder is pushed with git;
#: `huggingface-cli upload` handles them without it.
GITATTRIBUTES = "".join(f"{p} filter=lfs diff=lfs merge=lfs -text\n" for p in (
    "*.npz", "*.db", "*.bin", "*.glb", "*.ply", "*.las", "*.jpg", "*.png",
    "*.mp4"))


def fail(msg: str) -> None:
    sys.exit(f"build_space: {msg}")


def _skip(src: Path, names: list[str]) -> set[str]:
    return {n for n in names if n in ("__pycache__", ".venv", "node_modules",
                                      "dist") or n.endswith(".egg-info")}


def copy_frontend(dst: Path) -> None:
    src = APP / "frontend"
    dst.mkdir()
    for name in FRONTEND_FILES:
        shutil.copy2(src / name, dst / name)
    shutil.copytree(src / "src", dst / "src", ignore=_skip)

    def public_skip(d: str, names: list[str]) -> set[str]:
        rel = Path(d).relative_to(src)
        return {n for n in names if (rel / n).as_posix() in UNCREDITED}
    shutil.copytree(src / "public", dst / "public", ignore=public_skip)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bundle", type=Path, required=True,
                    help="a bundle written by export_showcase.py")
    ap.add_argument("--out", type=Path, required=True,
                    help="folder to assemble the image source in")
    ap.add_argument("--replace", action="store_true",
                    help="overwrite --out if this script wrote it before")
    args = ap.parse_args()

    m = showcase.load(args.bundle)
    if m is None:
        fail(f"{args.bundle} holds no {showcase.MANIFEST}; export one with "
             f"scripts/export_showcase.py")
    out = args.out
    if out.exists() and any(out.iterdir()):
        if not args.replace:
            fail(f"{out} is not empty; pass --replace to overwrite it")
        if not (out / MARKER).is_file():
            fail(f"{out} was not written by this script; refusing to delete it")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    shutil.copy2(APP / "deploy/showcase/Dockerfile", out / "Dockerfile")
    shutil.copy2(APP / "deploy/showcase/requirements.txt",
                 out / "requirements.txt")
    shutil.copytree(APP / "backend/app", out / "backend/app", ignore=_skip)
    (out / "reconstruction").mkdir()
    shutil.copy2(APP / "reconstruction/pyproject.toml",
                 out / "reconstruction/pyproject.toml")
    shutil.copytree(APP / "reconstruction/drishti_recon",
                    out / "reconstruction/drishti_recon", ignore=_skip)
    copy_frontend(out / "frontend")
    shutil.copytree(args.bundle, out / "showcase-data")

    credits = "\n".join(f"- {c}" for c in showcase.credits(args.bundle))
    (out / "README.md").write_text(CARD.format(
        credits=credits, exported_at=m["exported_at"],
        code_version=m["code_version"]))
    (out / ".gitattributes").write_text(GITATTRIBUTES)
    # Uploaded with everything else, so nothing about this machine goes in it.
    (out / MARKER).write_text(json.dumps(
        {"exported_at": m["exported_at"], "missions": len(m["projects"])})
        + "\n")

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"assembled {out} ({size / 1e6:.0f} MB, {len(m['projects'])} "
          f"missions)\n\nbuild and run it:\n"
          f"  docker build -t drishti3d-showcase {out}\n"
          f"  docker run --rm -p 7860:7860 --memory 6g drishti3d-showcase")


if __name__ == "__main__":
    main()
