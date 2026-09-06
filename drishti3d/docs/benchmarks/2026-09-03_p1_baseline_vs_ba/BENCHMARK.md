# Drishti3D — Ablation Benchmark

_Generated 2026-09-03T03:57:32.084056+00:00_

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
| `low_parallax_s0` | 60 | `a97381a9bd987709` |
| `low_parallax_s1` | 60 | `e04b35684cf53245` |
| `low_parallax_s2` | 60 | `2408e2b22f3b5046` |
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
| `ba` | Baseline + sparse bundle adjustment (interim solves every 8 registered cameras, then one global solve). Intrinsics held fixed. | `{"bundle_adjust": true, "ba_every": 8}` |

## Overall, per variant (all regimes and seeds pooled)

| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m (med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | Peak RSS MB (worst) |
|---|---|---|---|---|---|---|---|---|---|---|
| `ba` | 12 | 2 | 100.0% / 3.3% | 0.003 / 0.256 | 0.0020 / 0.0035 | 0.805 / 86.710 | 66.1% / 0.0% | 2.87 / 100.00 | 405.3 | 1622 |
| `baseline` | 12 | 2 | 100.0% / 3.3% | 0.069 / 0.679 | 0.0020 / 0.0035 | 0.823 / 86.710 | 71.2% / 0.0% | 2.49 / 100.00 | 98.2 | 1235 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `ba` | `low_parallax` | 3 | 2 | 3.3% | — / — | — | 86.710 | 0.0% | 100.00 |
| `baseline` | `low_parallax` | 3 | 2 | 3.3% | — / — | — | 86.710 | 0.0% | 100.00 |
| `ba` | `nadir_grid` | 3 | 0 | 100.0% | 0.186 / 0.256 | 0.0020 | 0.899 | 67.3% | 3.08 |
| `baseline` | `nadir_grid` | 3 | 0 | 100.0% | 0.317 / 0.679 | 0.0022 | 0.913 | 71.6% | 2.25 |
| `ba` | `oblique_pass` | 3 | 0 | 100.0% | 0.002 / 0.002 | 0.0024 | 0.801 | 39.7% | 4.31 |
| `baseline` | `oblique_pass` | 3 | 0 | 100.0% | 0.020 / 0.069 | 0.0024 | 0.809 | 44.4% | 3.85 |
| `ba` | `orbit` | 3 | 0 | 100.0% | 0.003 / 0.004 | 0.0003 | 0.653 | 95.5% | 2.25 |
| `baseline` | `orbit` | 3 | 0 | 100.0% | 0.055 / 0.074 | 0.0003 | 0.668 | 95.5% | 2.33 |

## Failed cells

| Variant | Regime | Seed | Error |
|---|---|---|---|
| `baseline` | `low_parallax` | 0 | `RuntimeError: reconstruction produced no 3D points` |
| `baseline` | `low_parallax` | 1 | `RuntimeError: reconstruction produced no 3D points` |
| `ba` | `low_parallax` | 0 | `RuntimeError: reconstruction produced no 3D points` |
| `ba` | `low_parallax` | 1 | `RuntimeError: reconstruction produced no 3D points` |

## How to reproduce

```bash
python -m eval.benchmark --variants baseline,ba \
    --regimes oblique_pass,nadir_grid,orbit,low_parallax \
    --seeds 0,1,2 \
    --frames 60 --out <dir>
```
