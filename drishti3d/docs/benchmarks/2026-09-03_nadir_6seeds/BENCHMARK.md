# Drishti3D — Ablation Benchmark

_Generated 2026-09-03T05:39:59.656175+00:00_

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
| `nadir_grid_s3` | 60 | `caff1cca376f1148` |
| `nadir_grid_s4` | 60 | `82a8c128e48fefbc` |
| `nadir_grid_s5` | 60 | `3694ab20ab58ebb0` |

## Variants compared

| Variant | Description | Parameter overrides |
|---|---|---|
| `baseline` | OpenCV incremental SfM as shipped: sequential+GPS-proximity matching, essential-matrix init, PnP registration, no bundle adjustment. | `{"bundle_adjust": false}` |

## Overall, per variant (all regimes and seeds pooled)

| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m (med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | Peak RSS MB (worst) |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 6 | 0 | 100.0% / 100.0% | 1.259 / 2.405 | 0.0010 / 0.0042 | 0.938 / 0.962 | 64.7% / 56.5% | 2.28 / 2.69 | 90.6 | 1076 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | `nadir_grid` | 6 | 0 | 100.0% | 1.259 / 2.405 | 0.0010 | 0.938 | 64.7% | 2.28 |

## Failed cells

- none

## How to reproduce

```bash
python -m eval.benchmark --variants baseline \
    --regimes nadir_grid \
    --seeds 0,1,2,3,4,5 \
    --frames 60 --out <dir>
```
