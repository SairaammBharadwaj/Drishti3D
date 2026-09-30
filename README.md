# Drishti3D

**Single-pass drone video to measurable, georeferenced 3D, with the evidence
behind every measurement.** Smart India Hackathon 2026, problem
[SIH26158](drishti3d/docs/PROBLEM_STATEMENT.md) (NTRO).

**Live demo:** https://drishti3d.taileff695.ts.net. This is a read-only
showcase of six finished missions: explore the point clouds, read the quality
reports, and measure. It runs on a team laptop, so it is occasionally offline.

## What it does

From one pass of drone video and its GPS or RTK telemetry, Drishti3D:

- recovers the camera path and a dense point cloud, using structure-from-motion
  and dense stereo (COLMAP, or a built-in OpenCV engine);
- places it in real-world coordinates at metric scale;
- labels every point: observed with high confidence, observed with low
  confidence, AI-assisted, a moving object that was excluded, or never
  observed. Only observed geometry is measurable by default;
- answers measurement questions (a distance, a height, an area) at a stated
  tolerance, and shows the uncertainty and which frames support the answer,
  or explains what evidence is missing.

## Results so far, and their limits

| Test | Result | Reference | Scope |
|---|---|---|---|
| Hong Kong, 2 flights ([MARS-LVIG](https://mars.hku.hk/)), native 10 Hz video + RTK, single pass | vertical RMSE **0.38–0.42 m**; horizontal placement 0.08–0.28 m | LiDAR on the same drone, same flight | one site, one day ([details](drishti3d/docs/VIDEO_ACCURACY_MARS_LVIG.md)) |
| UseGeo 1, 60 calibrated nadir photos | surface RMSE **0.32 m** | independent RIEGL LiDAR survey | still photos, not video; one site ([DEC-041](DECISIONS.md)) |
| Austin, 11 min 18 s of native 1080p DJI video | 80/80 keyframes registered; the full job takes **12.2 min** on a laptop RTX 5060 (target: under 15) | none; accuracy not scored here | [DEC-041](DECISIONS.md) |

None of this is certified dimensional accuracy. The app deliberately does not
yet mark any measurement "meets requirement": that needs a validated
calibration of its uncertainty, which is still open
([DEC-003](DECISIONS.md), [DEC-006](DECISIONS.md)). Every figure above was
produced by the scripts in `drishti3d/eval` and `drishti3d/scripts`, and the
decision log records how each one was checked.

## Repository map

| Path | What is there |
|---|---|
| [`drishti3d/`](drishti3d/README.md) | The application; its README has setup and architecture |
| `drishti3d/reconstruction/` | The geometry, uncertainty and measurement library (`drishti_recon`) |
| `drishti3d/backend/`, `drishti3d/frontend/` | FastAPI server; React and Three.js workspace |
| `drishti3d/eval/`, `drishti3d/scripts/`, `drishti3d/tests/` | Benchmark harness and scorers; operator tools; test suite |
| `drishti3d/deploy/` | The public read-only showcase: image build and laptop-server kit |
| [`drishti3d/docs/`](drishti3d/docs/README.md) | Accuracy write-ups, benchmarks, operations guides, reviews |
| `datasets/` | Catalogue of the datasets used; the data itself is not in git |
| [`DECISIONS.md`](DECISIONS.md) | Every engineering decision, with its evidence (DEC-001 onwards) |
| [`TESTS_AND_RESULTS.md`](TESTS_AND_RESULTS.md), [`WORKLOG.md`](WORKLOG.md) | Dated test results; chronological work log |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md), [`SYSTEM_FLOW.md`](SYSTEM_FLOW.md) | How the system fits together |
| [`NEXT_STEPS.md`](NEXT_STEPS.md) | Open work |

## Running it

After the one-time setup in [`drishti3d/README.md`](drishti3d/README.md)
("Quick start"), from the repository root:

```bash
drishti3d/scripts/serve.sh     # API on 127.0.0.1:8000, workspace on 127.0.0.1:5173
```

To publish finished missions read-only, see "Public showcase" in
[`drishti3d/README.md`](drishti3d/README.md) and
[`drishti3d/deploy/showcase/server/README.md`](drishti3d/deploy/showcase/server/README.md).

## Data and licences

The showcase missions come from MARS-LVIG (HKU MaRS Lab, CC BY-NC-SA 4.0),
UseGeo (3DOM, FBK, CC BY-NC-SA 4.0), AirLock+ (CC BY 4.0) and the Zurich Urban
MAV dataset (academic research use). Reconstructions derived from them carry
the same terms. Models, datasets and dependencies are listed in
[`drishti3d/MODEL_LICENSE_MANIFEST.md`](drishti3d/MODEL_LICENSE_MANIFEST.md).
