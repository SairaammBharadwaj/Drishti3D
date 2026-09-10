# Drishti3D — Ablation Benchmark

_Generated 2026-09-02T16:27:27.039255+00:00_

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
| `baseline` | 9 | 1 | 100.0% / 66.7% | 1.697 / 13.114 | 0.0053 / 0.0217 | 0.965 / 2.825 | 47.7% / 2.7% | 4.42 / 67.34 | 63.0 | 997 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | `nadir_grid` | 3 | 0 | 66.7% | 1.789 / 2.357 | 0.0057 | 0.991 | 46.3% | 4.26 |
| `baseline` | `oblique_pass` | 3 | 1 | 100.0% | 12.186 / 13.114 | 0.0113 | 2.430 | 7.4% | 52.91 |
| `baseline` | `orbit` | 3 | 0 | 100.0% | 1.234 / 1.606 | 0.0048 | 0.685 | 92.8% | 3.46 |

## Failed cells

| Variant | Regime | Seed | Error |
|---|---|---|---|
| `baseline` | `oblique_pass` | 2 | `RuntimeError: reconstruction produced no 3D points` |

## How to reproduce

```bash
python -m eval.benchmark --variants baseline \
    --regimes oblique_pass,nadir_grid,orbit \
    --seeds 0,1,2 \
    --frames 60 --out <dir>
```
