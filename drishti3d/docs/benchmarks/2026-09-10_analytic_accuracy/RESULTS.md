# Drishti3D — Ablation Benchmark

_Generated 2026-09-10T06:32:30.902801+00:00_

Every number below was produced by `python -m eval.benchmark` on the inputs and commit recorded in this file. Numbers are reported as **median / worst** across trials, because a system intended for field use is described by its tail, not its best run.

## Provenance

| Field | Value |
|---|---|
| Commit | `64fd2ad7ffdb` |
| Branch | `sfm-hardening-and-colmap-engine` |
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

## Overall, per variant (all regimes and seeds pooled)

| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m (med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | Peak RSS MB (worst) |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 12 | 2 | 100.0% / 3.3% | 0.074 / 1.749 | 0.0014 / 0.0035 | 0.065 / 0.115 | 68.1% / 35.5% | 2.16 / 100.00 | 90.1 | 1205 |

## Per capture regime

The regime is the dominant driver of reconstructability. A variant that only wins on `orbit` has not been shown to help a real mapping flight.

| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m (med/worst) | Scale err | Cloud acc m | Complete | Dim err % |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | `low_parallax` | 3 | 2 | 3.3% | — / — | — | — | — | 100.00 |
| `baseline` | `nadir_grid` | 3 | 0 | 100.0% | 0.343 / 1.749 | 0.0008 | 0.022 | 68.1% | 1.08 |
| `baseline` | `oblique_pass` | 3 | 0 | 100.0% | 0.069 / 0.132 | 0.0024 | 0.084 | 36.5% | 2.50 |
| `baseline` | `orbit` | 3 | 0 | 100.0% | 0.056 / 0.074 | 0.0003 | 0.054 | 94.9% | 2.29 |

## Failed cells

| Variant | Regime | Seed | Error |
|---|---|---|---|
| `baseline` | `low_parallax` | 0 | `RuntimeError: reconstruction produced no 3D points` |
| `baseline` | `low_parallax` | 1 | `RuntimeError: reconstruction produced no 3D points` |

## How to reproduce

```bash
python -m eval.benchmark --variants baseline \
    --regimes oblique_pass,orbit,nadir_grid,low_parallax \
    --seeds 0,1,2 \
    --frames 60 --out <dir>
```
