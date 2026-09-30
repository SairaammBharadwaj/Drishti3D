# Drishti3D: a defensible route to a model in under 15 minutes

**Review date:** 23 September 2026. **Reviewed HEAD:** `ed65bd163b8780dd02142f806020a1b21c720f6a`, plus the current working tree, including the new inferred hole-fill work. This is a performance audit and implementation plan, not a claim that the target has been achieved. Production code was not changed for this review.

**Recommendation:** keep the successful camera reconstruction and measurement safeguards; remove memory waste and Python overhead, expose dense-stereo controls, then test those controls independently. Run the same validated configuration on the A100 before sacrificing resolution. The A100 is a promising route, but neither its speedup nor the eventual laptop runtime has been measured.

## 1. What the current results actually establish

The saved DJI runs are the most relevant duration tests. Both registered all 80 selected cameras.

| Saved result | DJI_1003, downtown | DJI_1001, interchange |
|---|---:|---:|
| Actual video length | 677.89 s / 11 min 18 s | 685.32 s / 11 min 25 s |
| Analysed frames | 2,391 | 2,283 |
| Selected / registered cameras | 80 / 80 | 80 / 80 |
| Sparse reconstruction | 253.55 s | 251.08 s |
| Dense stage | 1,585.29 s | 1,593.72 s |
| Reported processing time | 1,950.39 s / 32.51 min | 1,939.94 s / 32.33 min |
| Dense share of reported time | 81.3% | 82.2% |
| Final cloud | 2.69 million points | 3.27 million points |
| Median point spacing | 0.379 m | 0.367 m |
| Median reprojection error | 0.303 px | 0.339 px |

Sources: [baseline evidence](baseline_evidence.json), extracted from the saved quality reports and manifests. These are archived results, not fresh timings of today's uncommitted code. Despite their `t10` tags, these inputs are longer than ten minutes.

**The timing currently understates the complete job.** `quality.py:179` sums recorded stages before exports happen. `pipeline.py:799` subsequently remaps observations, compresses arrays, writes model files and coverage, and now creates inferred fill. Some sensor/coverage/distortion work is outside those stage timers. The two old runs have no external `run_*.json` record. Therefore, 32.5 minutes is reported stage time, not a verified end-to-end wall time; the dense percentage is not a GPU utilisation measurement.

The dense timer includes image undistortion, PatchMatch, stereo fusion, file parsing, visibility translation, and uncertainty calculation. An A100 accelerates only the eligible GPU parts. First separate them.

**Accuracy is encouraging on one calibrated site, but not established for these DJI flights.** The newer UseGeo fixed-calibration result reports 0.324 m surface RMSE against LiDAR, versus 1.283 m before the calibration fix. Preserve that improvement. It also reports only 29.9% coverage for nominal 95% uncertainty intervals and 67.9% reference completeness within 0.5 m. These remain limitations. See [the current results record](../../../TESTS_AND_RESULTS.md) and [saved LiDAR score](../../data/runs/usegeo_1__fixedcal/lidar_score.json). Surface distance is not independently identified building-length accuracy.

The DJI missions have no supplied camera calibration or independent truth assessment. Their approximately 2.8 m GPS alignment residuals are not independent accuracy measurements. A faster result with equally low reprojection error can still have wrong scale, height or missing surfaces.

## 2. The speedup we actually need

For DJI_1003, the recorded non-dense work is approximately 365 seconds:

`new reported time ≈ 365 + 1,585 / dense_speedup`

| Hypothetical speedup of the whole dense stage | Estimated recorded time, excluding missing overhead |
|---|---:|
| 2× | 19.3 min |
| 3× | 14.9 min |
| 4× | 12.7 min |
| 5× | 11.4 min |

These are arithmetic scenarios, not GPU forecasts. Three times faster dense processing barely fits before exports; it is not enough margin. Halving sparse reconstruction would save another 127 seconds. Even making sparse reconstruction instantaneous would leave about 28 minutes of recorded work, so SfM alone cannot solve this.

The organiser's attachment gives a ten-minute-video / fifteen-minute-processing target without specifying a hardware benchmark in that attachment. Preserve a genuine 600-second test and also keep these longer full-flight stress tests. Do not multiply their runtimes by `600 / duration`: selected image count, scene extent and stereo complexity do not scale linearly with video length. [Previously retrieved official attachment](../review_2026_09_22/sources/SIH26158_official_attachment.pdf).

An initial engineering budget, **not a prediction**, is:

| Required work | Target budget |
|---|---:|
| Ingestion, telemetry, decoding, frame quality and selection | 75 s |
| Feature extraction, matching, mapping and bundle adjustment | 160 s |
| Dense image preparation, stereo and stereo fusion | 500 s |
| Georeferencing, uncertainty, observations, coverage and required exports | 100 s |
| Mesh and requested cosmetic fill | 25 s |
| Runtime margin | 40 s |
| Total | **900 s** |

Aim for a typical complete run below 13 minutes so variability does not routinely break the deadline. Reallocate this budget once substage measurements exist.

## 3. Implement first: preserve the computation, remove waste

### A. Stop keeping thousands of large images alive

`pipeline.py:213–313` retains every analysed BGR image throughout reconstruction. DJI_1003 holds roughly `2,391 × 1,600 × 900 × 3 = 10.33 GB` of image arrays alone, while its 80 selected images need about 346 MB. The laptop has about 16 GB installed RAM. This is avoidable memory pressure before millions of cloud points and observation tracks are allocated.

First separate frame metadata from image buffers and release every unselected full-size image after selection. Remove residual references such as the optional undistortion `imgs` list. Keep all timestamps, decoded frame indices, quality metrics and selected pixels unchanged. That preserves the reconstruction inputs; it does not imply a measured runtime saving yet.

Then remove the ingestion peak: stream quality scores and selection thumbnails, using a bounded disk cache or a second sequential decode to recover selected frames. Preserve exact container timestamps and existing distortion/selection semantics. Test selected-frame hashes and telemetry associations. A second decode costs time, but may be preferable to memory pressure; benchmark that tradeoff. Randomly seeking thousands of H.264 frames is not a guaranteed shortcut.

The inspection snapshot had about 4.4 GB available RAM and 3.7 GB swap occupied. This does not prove archived runs were actively swapping. Record peak RSS and swap-in/out during the next run.

### B. Vectorise per-point evidence calculations

`mvs.py:141` loops in Python over each dense point to calculate the widest contributing-camera angle. The pipeline also creates and remaps millions of small visibility arrays.

I tested a grouped, batched calculation on 50,000 evenly distributed points from DJI_1003:

| Three-run median | Current implementation | Grouped prototype |
|---|---:|---:|
| Calculation time | 0.701 s | 0.152 s |
| Relative speed | 1× | **4.60×** |

Maximum observed angle difference was **0.0 degrees**; invalid indices, insufficient views and zero-length rays were also checked. [Probe source](parallax_probe.py), [raw result](parallax_probe_result.json).

This is a CPU microbenchmark, not a 4.6× reconstruction speedup. A simple linear extrapolation suggests about 29 seconds saved on 2.63 million points, excluding parsing/remapping and memory effects; verify at full size. Productionise with bounded chunks and a compact offsets-plus-indices representation, avoiding a second huge Python object graph. Retain the actual contributing views and uncertainty semantics. Add correctness tests for ragged/invalid tracks before integrating it.

### C. Make exports efficient and measure them

`pipeline.py:1190` writes compressed cloud and observation archives. PLY export and observation remapping deserve separate profiling. Use a vectorised binary PLY writer with explicit coordinate precision; consider configurable compression for local intermediate arrays. Reuse spatial indices where inputs match. Confirm round-trip positions, observation identities and provenance.

Do not reduce measurement coordinates to low precision just to make files smaller. Preserve the complete observed cloud; use separate viewer levels of detail. The recent full-cloud viewer work helps inspect the result but does not accelerate stereo reconstruction.

The new inferred fill runs during exports and is absent from the old baseline. Time it separately. It remains cosmetic and excluded from measurements. An early preview is useful, but label the final model ready only after the agreed required artifacts exist. If fill is deferred, report both readiness times.

### D. Manage resources explicitly

At inspection, the existing backend occupied about 4.9 GB of the laptop's 8 GB GPU memory. I did not stop it. Add explicit model lifecycle management or separate short-lived inference workers so unused model allocations can be released before stereo. `empty_cache()` alone cannot release tensors still referenced by a live model.

Choose host-memory budgets after image buffers are released. The installed stereo tools advertise 32 GB cache defaults; that is not a suitable blanket assumption for this machine. Cache allocation is not necessarily all resident, and fusion's `use_cache` setting matters. Measure RSS and cache behaviour rather than treating one flag as a hard process-memory limit. Start conservatively within available RAM, reserving space for arrays, OS and exports; tune upward only when memory permits.

## 4. The main lever: reduce dense work carefully

The saved workspaces use `__auto__, 20` source images per reference. Installed COLMAP 4.1.0 advertises five PatchMatch iterations, fifteen samples, patch step one and geometric consistency enabled. The current wrapper exposes image size, geometric consistency and fusion minimum support, but not the other performance controls.

COLMAP documents source-view limits, patch sampling, iterations, image size and same-GPU worker concurrency as tuning controls. It warns that quality can change. These are experiment candidates, not free speedups. [Official dense reconstruction guidance](https://colmap.github.io/faq.html#speedup-dense-reconstruction).

Expose typed parameters in `PipelineParams`, the MVS wrapper and mission CLI; record their resolved values in the manifest. Reject unsupported settings instead of silently using defaults. Persist successful subprocess logs and separate timers for undistortion, PatchMatch, fusion, visibility loading and uncertainty.

Run this ladder, changing one setting against a fixed baseline before combining winners:

| Trial | Sparse image width | Dense maximum dimension | Sources/reference | Patch step | Iterations | Purpose |
|---|---:|---:|---:|---:|---:|---|
| B0 | 1600 | 1600 | 20 | 1 | 5 | Reproducible baseline |
| D1 | 1600 | 1600 | 12 | 1 | 5 | Less redundant support work |
| D2 | 1600 | 1600 | 10 | 1 | 5 | Test further support reduction |
| D3 | 1600 | 1600 | 20 | 2 | 5 | Cheaper patch evaluation |
| D4 | 1600 | 1600 | 20 | 1 | 3 | Fewer optimisation sweeps |
| D5 | 1600 | 1280 | 20 | 1 | 5 | Explicit resolution tradeoff |

Across these trials, keep all 80 reference cameras, geometric consistency, filtering, patch radius five, samples fifteen, fusion minimum support five, and the existing geometric thresholds. Source-view budget and fusion minimum support are different controls. Ten available sources do not guarantee five valid observations at every surface.

**My preferred first candidate is D1**, because it retains the pixel grid and camera solution. Fewer redundant sources could save work without discarding scene detail, but support near occlusions and thin structures may fall. Inspect those areas. For a later custom selector, choose sources using covisibility plus useful angular baseline, not time proximity alone.

Patch step two changes samples used to compare patches; it does not directly halve the output image dimensions. It may weaken matching on roofs, repetitive facades and low-texture surfaces. Reducing iterations may leave difficult pixels unconverged. Their effects must be measured separately.

At 1280 instead of 1600, the image contains 64% as many pixels. This offers less pixel work, not a guaranteed 36% total-runtime reduction. For fixed geometry and roughly constant pixel error, the depth uncertainty term increases by about 25% because focal length in pixels falls. Existing DJI spacing is already around 0.37 m, so thinner structures need particular attention. Avoid an immediate jump to 1024 or fewer reference cameras.

**Fix the uncertainty units before D5.** `pipeline.py:400–432` uses the sparse camera focal length with a dense pixel-noise assumption of one pixel. When dense images have a different scale, that focal length is in the wrong pixel coordinate system. Read the actual undistorted dense camera intrinsics and propagate their scale, or transform pixel noise consistently into sparse-image units. For a pure 0.8 resize, use `f_dense = 0.8 × f_sparse`; real undistortion/cropping requires the actual camera matrices. Add a scale-invariance test and revalidate uncertainty calibration. Do not let a faster low-resolution result claim unchanged confidence accidentally.

If D1 passes, combine it with whichever of D3/D4 independently passes, then re-evaluate the combination: interactions can break quality even when individual changes pass. D5 is a fallback with an explicit accuracy cost. Only later test fewer samples. Keep photometric-only stereo as a preview experiment rather than the default measurement product.

## 5. Make the A100 test meaningful

The local CLI is CUDA-enabled COLMAP **4.1.0**. Local PyCOLMAP is **4.2.0 with `has_cuda=False`**. Additionally, `colmap_adapter.py:207–211` explicitly selects `Device.cpu` for feature extraction. Copying this environment to an A100 will not automatically move this step onto its GPU.

Provide an explicit `cpu/cuda/auto` backend choice, enable compatible GPU extraction/matching, and log the resolved device. Preserve camera calibration, feature limits, matching policy and bundle adjustment. The official installation page provides Linux CUDA wheels under `pycolmap-cuda12`; a compatible wheel or the CUDA CLI can support this work. Verify the actual installation and API instead of trusting the package name. [Official PyCOLMAP installation](https://colmap.github.io/pycolmap/index.html#installation).

The four-thread SfM cap should become configurable. Benchmark two/four/eight threads where the allocation permits, after fixing memory retention. More threads can increase memory consumption and contention. Preserve exhaustive matching for these small, successful 80-camera sets: it tests 3,160 pairs and recently fixed disconnected reconstruction problems. Changing the matching graph is a separate accuracy experiment.

An A100 is the GPU, not a specification for its host CPU. Colab's assigned CPU, RAM and GPU availability must be recorded. Paid access does not mean a fixed machine on every session. Use local `/content` storage for active workspaces, copying inputs in and completed artifacts out, rather than running thousands of intermediate accesses against mounted Drive. [Colab resource and storage guidance](https://research.google.com/colaboratory/faq.html).

Suggested A100 order:

1. Run the supplied `preflight.py` with the actual worker interpreter. Check GPU name/VRAM, allowed CPU count, RAM, executable versions, CUDA support and available disk. Pin a compatible tested environment; current online COLMAP development docs may describe features absent from installed 4.1.0.
2. Stage the mission on local disk and verify video/telemetry/calibration hashes. Record transfer/setup separately from compute. For a user-facing upload-to-download claim, include transfer and queue time too.
3. Run B0 with the same input, resolution and algorithm, a fresh output directory, and no unrelated GPU workload. This isolates the hardware effect. Do not assume A100 tensor throughput translates into PatchMatch throughput.
4. Test verified CUDA feature extraction/matching separately. Time extraction, matching and mapping/BA independently. An A100 cannot remove CPU-only mapping, parsing or export time.
5. Within dense stereo, compare GPU index `0` with `0,0` only when VRAM and host memory allow it. This schedules two stereo workers on the same GPU; it is not two GPUs. It may improve utilisation or merely create contention. Measure before trying more workers.
6. Apply validated D1/combined settings only if baseline hardware improvements are insufficient. Prefer retaining 1600-pixel dense images when the A100 can meet the budget.

**Laptop candidate:** memory fixes, GPU-capable SfM, D1 first, one stereo worker, host threads/cache sized to available resources. **A100 candidate:** the same correctness fixes, B0 first, then worker-concurrency and D1 trials. Neither candidate is currently benchmark-qualified.

New GPU bundle-adjustment backends, global mapping and learned dense reconstruction are later research tracks. They require compatible engine versions and fresh accuracy validation. At 80 cameras, replacing the whole reconstruction engine is a larger risk than fixing the demonstrated dense bottleneck. An LLM does not accelerate these numerical kernels. Generative completion can improve appearance without supplying measured geometry.

## 6. Prove speed and accuracy together

Before benchmarking, add one monotonic wall clock around the complete pipeline, from accepted local input to the final required artifact/manifest. Write the final timing summary after export completes. The newer mission runner already records wall time around `pipeline.run`, which is useful, but uses `time.time`; move to `perf_counter` for elapsed time. Retain stage timers without summing overlapping tasks as if they were sequential.

Record command, source commit **and dirty diff/hash**, input hashes, all resolved parameters, engine versions, CPU/GPU/RAM, peak RAM/VRAM, disk, swap activity and substage logs. A successful Python exit is insufficient: dense failures are currently caught and can leave a sparse-only result. Explicitly fail the benchmark if required dense output, observations, coverage or required exports are missing.

For cheap initial dense ablations, reuse an immutable copy of the same sparse model and selected images. Give each trial a new dense workspace: existing depth maps can be skipped on reruns and make a changed setting appear artificially fast. Do not reuse or share writable depth-map output. A dense-only trial must be labelled dense-only; finish with fresh full-pipeline runs of the winning settings.

Predeclare these **engineering regression gates**, which are not organiser-defined tolerances:

| Property | Proposed gate |
|---|---|
| Camera solution | All 80 DJI cameras still registered; no new disconnected component; retain loop coverage |
| Independent surface error | RMSE and p95 no more than 5% worse than the calibrated baseline on a fixed evaluation region; separately report the absolute errors and unpaired/outlier fraction |
| Completeness | No more than two percentage points lower reference coverage at the same fixed distance threshold; no new missing critical roof, facade, edge or thin structure |
| Actual dimensions | Independently identified endpoints/planes and held-out surveyed lengths/heights/areas; predeclare tolerances and compare baseline vs candidate |
| Uncertainty and provenance | Correct pixel scaling; report empirical interval coverage; inferred fill remains excluded from measured geometry |
| Latency | Complete required output under 900 s on each tested run; report all runs and machine details, not only the best |

Recompute p95 for the fixed-calibration baseline; its documented table currently gives p90. Keep the same reference region and alignment policy across candidates. Use bidirectional surface coverage so deleting difficult points cannot manufacture an accuracy improvement. Report georeferenced error separately from any fitted translation/similarity diagnostic. Camera-pair dimensions are useful but do not replace building dimensions.

UseGeo supplies the initial independent LiDAR reference. The two DJI missions test runtime, coverage and robustness, but cannot establish absolute measurement accuracy without independent references. Add a second calibrated scene before generalising. Do not use the previously withdrawn nearest-neighbour endpoint test as proof of dimensional accuracy.

Run one fresh trial per candidate during screening, then at least three fresh runs for each finalist and baseline, interleaved where practical. Report individual times, median and maximum; three trials do not establish a reliable p95 latency. Keep a held-out scene/settings freeze for the final demonstration to reduce benchmark overfitting.

## 7. Concrete implementation sequence

1. **Trustworthy baseline:** wall clock, dense substage logs, required-artifact checks, machine inventory, new full-pipeline baseline including the current fill work.
2. **Same-input efficiency:** release frame buffers; bound ingestion memory; vectorise parallax/visibility; profile exports. Confirm frame identity, point/provenance consistency and selected functional tests.
3. **Controlled settings:** expose source count, patch step, iterations, samples, GPU workers, CPU threads and memory settings; fix dense uncertainty pixel units; record resolved configuration.
4. **Small experiment ladder:** B0/D1/D2/D3/D4 on immutable sparse input, then accuracy scoring. Test D5 only with the uncertainty correction. Combine only passing settings.
5. **A100 session:** preflight, local input staging, unchanged-algorithm baseline, CUDA SfM test, concurrency test, winning dense configuration.
6. **Qualification:** fresh end-to-end runs on a real ten-minute clip and both full DJI flights, plus independent accuracy tests. Publish hardware-specific runtime/accuracy together.

The most defensible current conclusion is that the project has substantial avoidable overhead and an identified dominant stage. There is a plausible route to under 15 minutes, especially on the A100. There is not yet evidence for a particular final runtime or a zero-loss dense preset.

## 8. Files produced and how to reproduce this review

This directory contains the plan, archived-run evidence with source hashes, laptop preflight, and the executable parallax microbenchmark plus its result. Run from the repository root:

```bash
drishti3d/.venv/bin/python drishti3d/docs/performance_2026_09_23/preflight.py
drishti3d/.venv/bin/python drishti3d/docs/performance_2026_09_23/parallax_probe.py \
  --workspace drishti3d/data/runs/dji_1003__t10/colmap_workspace
```

The first command is read-only inventory; the second reads an existing dense cloud and times CPU calculations. Neither starts reconstruction. On Colab, use the configured environment's `python` instead of this laptop venv path.

After staging the dataset and verifying the environment, this is an **existing-CLI baseline example**, not an optimised command. Use a unique tag for every fresh run and execute from `drishti3d/` with the appropriate Python interpreter:

```bash
python scripts/run_mission.py --set field_clips --mission dji_1003 \
  --engine colmap --max-frames 2400 --proc-width 1600 \
  --preset balanced --densify mvs --tag a100_baseline_01
```

The proposed dense tuning/device flags need implementation; they are not accepted by today's mission CLI. No new full reconstruction or A100 run was performed during this review. Existing user changes were preserved.
