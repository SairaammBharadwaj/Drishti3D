# Drishti3D — Ablation Benchmark

_Generated 2026-09-04T06:55:14.866886+00:00_

Every number below was produced by `python -m eval.benchmark` on the inputs and commit recorded in this file. Numbers are reported as **median / worst** across trials, because a system intended for field use is described by its tail, not its best run.

## Provenance

| Field | Value |
|---|---|
| Commit | `efae0334cc3d` **(dirty tree — not reproducible from this commit alone)** |
| Branch | `main` |
| Python | 3.12.14 |
| Platform | Linux-7.1.9-arch1-2-x86_64-with-glibc2.44 |
| CPU count | 24 |
| numpy / scipy / OpenCV | 2.5.2 / 1.18.1 / 5.0.0 |

### Inputs

| Scene | Frames | SHA-256 (video) |
|---|---|---|
| `nadir_grid_s0` | 60 | `5649a583a06ca29d` |
| `nadir_grid_s1` | 60 | `59df55993ebecd42` |
| `oblique_pass_s0` | 60 | `099ac80ef025438c` |
| `oblique_pass_s1` | 60 | `db15a84a1d84a271` |
| `orbit_s0` | 60 | `876ceeac46821070` |
| `orbit_s1` | 60 | `33f6efd57eb2e392` |

## Variants compared

| Variant | Description | Parameter overrides |
|---|---|---|
| `baseline` | OpenCV incremental SfM as shipped: sequential+GPS-proximity matching, essential-matrix init, PnP registration, no bundle adjustment. | `{"bundle_adjust": false}` |
| `lightglue` | Baseline with learned features (DISK) matched by LightGlue. Permissively licensed weights only; SuperPoint is refused by default. | `{"bundle_adjust": false, "matcher": "lightglue"}` |

## Overall, per variant (all regimes and seeds pooled)

| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m (med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | Peak RSS MB (worst) |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 6 | 0 | 100.0% / 100.0% | 0.062 / 2.405 | 0.0017 / 0.0035 | 0.819 / 0.960 | 62.4% / 34.5% | 2.22 / 4.01 | 97.9 | 1247 |
| `lightglue` | 6 | 0 | 100.0% / 100.0% | 0.171 / 2.327 | 0.0026 / 0.0054 | 0.974 / 0.994 | 64.3% / 37.4% | 3.11 / 7.92 | 118.0 | 2815 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | `nadir_grid` | 2 | 0 | 100.0% | 1.287 / 2.405 | 0.0016 | 0.935 | 62.4% | 1.69 |
| `lightglue` | `nadir_grid` | 2 | 0 | 100.0% | 2.004 / 2.327 | 0.0043 | 0.984 | 64.3% | 5.60 |
| `baseline` | `oblique_pass` | 2 | 0 | 100.0% | 0.040 / 0.069 | 0.0028 | 0.819 | 38.5% | 3.31 |
| `lightglue` | `oblique_pass` | 2 | 0 | 100.0% | 0.092 / 0.116 | 0.0028 | 0.980 | 43.9% | 2.97 |
| `baseline` | `orbit` | 2 | 0 | 100.0% | 0.048 / 0.055 | 0.0008 | 0.677 | 95.1% | 2.17 |
| `lightglue` | `orbit` | 2 | 0 | 100.0% | 0.161 / 0.227 | 0.0008 | 0.919 | 88.9% | 2.26 |

## Failed cells

- none

## How to reproduce

```bash
python -m eval.benchmark --variants baseline,lightglue \
    --regimes orbit,oblique_pass,nadir_grid \
    --seeds 0,1 \
    --frames 60 --out <dir>
```
