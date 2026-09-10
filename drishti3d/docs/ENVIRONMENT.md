# Reproducible environment

The repository audit could not run a single test, because the system interpreter
(Python 3.14) has no OpenCV wheel and no pytest. Any accuracy claim made from an
environment nobody can rebuild is unverifiable, so this is the first gate: a
clean machine must reach a passing test suite before any number is believed.

## Build it

```bash
cd drishti3d
uv venv --python 3.12 .venv                 # 3.14 has no OpenCV wheel yet
VIRTUAL_ENV=.venv uv pip install \
    numpy scipy "opencv-python-headless>=4.8" pyproj imageio imageio-ffmpeg \
    fastapi "uvicorn[standard]" sqlalchemy pydantic python-multipart aiofiles \
    httpx laspy open3d pytest
VIRTUAL_ENV=.venv uv pip install -e reconstruction
.venv/bin/python -m pytest tests -q
```

`pip` works identically; `uv` is used here only because it is already on the
machine and resolves faster.

## Verified configuration

Everything committed under `docs/` that reports a measurement was produced on
this exact stack:

| Component | Version |
|---|---|
| Python | 3.12.14 |
| OpenCV (headless) | 5.0.0 |
| NumPy | 2.5.2 |
| SciPy | 1.18.1 |
| pyproj | 3.7.2 |
| Open3D | 0.19.0 |
| imageio | 2.37.4 |
| laspy | 2.7.0 |
| FastAPI / SQLAlchemy / Pydantic | 0.141.1 / 2.0.52 / 2.13.5 |
| pytest | 9.1.1 |

**Status: 40/40 tests pass** (32 pre-existing + 8 new bundle-adjustment tests).
The pre-existing suite passed unmodified, so the audit's "tests could not be
executed" was a missing environment, not broken code.

Every benchmark run additionally writes its own `env.lock.txt` (a full
`pip freeze`) beside its results, so a report is never separated from the
environment that produced it.

## Why Python 3.12

3.13 and 3.14 currently have no `opencv-python-headless` wheel, and OpenCV is a
hard dependency of the reconstruction path. 3.12 is the newest interpreter with
the whole stack available as binary wheels, so the environment builds without a
compiler.

## Data is *not* in this checkout

`git-lfs` is not installed here, and **128 of the 130 tracked binary files are
unfetched LFS pointers** (~130-byte text stubs), including:

- all 123 Bellus aerial images (`odm_data_bellus-master/.../images/*.jpg`),
- the synthetic fixture video `sample_data/synthetic/synthetic_flight.mp4`,
- every committed `cloud.npz`, `mesh.glb` and `point_cloud.ply`.

Only `sample_data/proj_*/artifacts/point_cloud.las` are real files.

This corrects an assumption in the original audit: the real Bellus imagery is
*referenced* by the repository but is not present, so no real-data reconstruction
can run here until the content is fetched:

```bash
sudo pacman -S git-lfs      # or: apt install git-lfs / brew install git-lfs
git lfs install
git lfs pull
```

Until then the truth harness runs on **procedurally generated** synthetic scenes
(`drishti_recon.synth`), which need no download because they are rendered from a
known 3D scene at run time. See [BENCHMARK.md](BENCHMARK.md).
