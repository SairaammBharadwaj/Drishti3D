# Drishti3D — Ablation Benchmark

_Generated 2026-09-04T07:34:43.279350+00:00_

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
| `nadir_grid_s2` | 60 | `15621194b52b283e` |
| `oblique_pass_s0` | 60 | `099ac80ef025438c` |
| `oblique_pass_s1` | 60 | `db15a84a1d84a271` |
| `oblique_pass_s2` | 60 | `ecb06cc17f5ea8ed` |
| `orbit_s0` | 60 | `876ceeac46821070` |
| `orbit_s1` | 60 | `33f6efd57eb2e392` |
| `orbit_s2` | 60 | `5533e8908acda130` |

## Variants compared

| Variant | Description | Parameter overrides |
|---|---|---|
| `baseline` | OpenCV incremental SfM as shipped: sequential+GPS-proximity matching, essential-matrix init, PnP registration, no bundle adjustment. | `{"bundle_adjust": false}` |

## Overall, per variant (all regimes and seeds pooled)

| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m (med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | Peak RSS MB (worst) |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 9 | 0 | 100.0% / 100.0% | 0.069 / 2.405 | 0.0014 / 0.0035 | 0.809 / 0.960 | 65.4% / 34.5% | 2.36 / 4.01 | 97.9 | 1246 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | `nadir_grid` | 3 | 0 | 100.0% | 0.577 / 2.405 | 0.0010 | 0.911 | 65.4% | 2.15 |
| `baseline` | `oblique_pass` | 3 | 0 | 100.0% | 0.020 / 0.069 | 0.0024 | 0.809 | 38.3% | 3.84 |
| `baseline` | `orbit` | 3 | 0 | 100.0% | 0.055 / 0.074 | 0.0003 | 0.675 | 95.5% | 2.30 |

## Failed cells

- none

## How to reproduce

```bash
python -m eval.benchmark --variants baseline \
    --regimes oblique_pass,nadir_grid,orbit \
    --seeds 0,1,2 \
    --frames 60 --out <dir>
```
