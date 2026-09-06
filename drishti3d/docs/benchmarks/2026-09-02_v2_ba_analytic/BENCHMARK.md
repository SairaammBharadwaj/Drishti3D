# Drishti3D — Ablation Benchmark

_Generated 2026-09-02T15:46:10.688124+00:00_

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
| `ba` | 12 | 3 | 100.0% / 3.3% | 0.009 / 6.907 | 0.0023 / 0.0301 | 0.879 / 86.710 | 50.9% / 0.0% | 2.31 / 121.21 | 161.6 | 1480 |
| `baseline` | 12 | 3 | 100.0% / 3.3% | 1.697 / 13.114 | 0.0295 / 0.0922 | 0.990 / 86.710 | 46.6% / 0.0% | 9.63 / 100.00 | 62.5 | 999 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `ba` | `low_parallax` | 3 | 2 | 3.3% | — / — | — | 86.710 | 0.0% | 100.00 |
| `baseline` | `low_parallax` | 3 | 2 | 3.3% | — / — | — | 86.710 | 0.0% | 100.00 |
| `ba` | `nadir_grid` | 3 | 0 | 66.7% | 0.014 / 0.022 | 0.0032 | 0.886 | 50.9% | 2.00 |
| `baseline` | `nadir_grid` | 3 | 0 | 66.7% | 1.789 / 2.357 | 0.0254 | 0.990 | 46.6% | 4.59 |
| `ba` | `oblique_pass` | 3 | 1 | 100.0% | 3.455 / 6.907 | 0.0168 | 1.453 | 20.7% | 62.78 |
| `baseline` | `oblique_pass` | 3 | 1 | 100.0% | 12.186 / 13.114 | 0.0667 | 2.449 | 7.4% | 73.67 |
| `ba` | `orbit` | 3 | 0 | 100.0% | 0.003 / 0.004 | 0.0003 | 0.663 | 95.1% | 2.02 |
| `baseline` | `orbit` | 3 | 0 | 100.0% | 1.234 / 1.606 | 0.0217 | 0.678 | 92.7% | 2.80 |

## Failed cells

| Variant | Regime | Seed | Error |
|---|---|---|---|
| `baseline` | `oblique_pass` | 2 | `RuntimeError: reconstruction produced no 3D points` |
| `baseline` | `low_parallax` | 0 | `RuntimeError: reconstruction produced no 3D points` |
| `baseline` | `low_parallax` | 1 | `RuntimeError: reconstruction produced no 3D points` |
| `ba` | `oblique_pass` | 2 | `RuntimeError: reconstruction produced no 3D points` |
| `ba` | `low_parallax` | 0 | `RuntimeError: reconstruction produced no 3D points` |
| `ba` | `low_parallax` | 1 | `RuntimeError: reconstruction produced no 3D points` |

## How to reproduce

```bash
python -m eval.benchmark --variants baseline,ba \
    --regimes oblique_pass,nadir_grid,orbit,low_parallax \
    --seeds 0,1,2 \
    --frames 60 --out <dir>
```
