# Public test data and hardware-aware runtime protocol

Verified 22 September 2026. This is a follow-up to the review, not a report of new reconstruction runs. Only dataset documentation and a small public file listing were fetched; the new videos and ROS bags were not downloaded or tested.

## Recommended starting point: AirLock+

[Author project page](https://airlock-wacv2026.github.io/) · [Dataset and download browser](https://huggingface.co/datasets/zhiyundeng/AirLock-WACV2026/tree/main) · [Dataset README](https://huggingface.co/datasets/zhiyundeng/AirLock-WACV2026/blob/main/README.md)

This provides actual DJI aerial MP4s, UAV SRT/CSV telemetry and camera calibration. Two published sequences exceed ten minutes: `DJI_1001` (11:25) and `DJI_1003` (11:17). The 1080p files are approximately 771 MB and 618 MB respectively, verified against the Hugging Face file API. Their 2.7K masters are approximately 7.8 GB each. The 1080p versions are derived proxies; record this provenance.

**Start with `DJI_1003`**, an urban sequence, after a short pipeline smoke test. Required repository paths:

```text
uav-video/1080p/DJI_1003_1080p.mp4
telemetry/uav/DJI_1003.srt
telemetry/uav/DJI_1003.csv
uav-video/calibration/dji_air2s_1080p.yaml
```

Use the aerial footage, not composite previews, vehicle FPV or rendered map videos. Use UAV telemetry, not the vehicle GPS columns. The project already supports DJI-style SRT and CSV, but this release's fields, timing and calibration still need an import check. Preserve camera distortion and source image dimensions through the existing backend path.

Choose a continuous 600-second interval only after checking the flight trajectory, footage continuity and changing gimbal direction. Crop telemetry on the same time axis. A ten-minute duration does not itself establish single-pass geometry or sufficient parallax. Keep the full source, interval bounds, file hashes and processing resolution in the manifest.

This is a useful video/telemetry integration and runtime benchmark. Its published geolocation data are not independent surveyed 3D structural measurements. It cannot by itself certify roof heights or road widths. The dataset card declares CC BY 4.0 with qualifications for third-party material.

## Complementary datasets

| Dataset | Suitable use | Important constraint |
|---|---|---|
| [MARS-LVIG](https://mars.hku.hk/dataset.html) | Long aerial image sequences, GNSS/IMU, RTK position references and DJI L1 mapping references. `HKairport_GNSS01` is 790 s; `AMtown01` is 1,354 s. | ROS-bag conversion is needed. Inspect route and select a suitable pass. Verify map reference error, coordinate frames and independent evaluation protocol. The old direct link for `HKairport01` returned a web-tool 404; use the author's updated download folder. |
| [UseGeo](https://github.com/3DOM-FBK/usegeo) | Continue independent LiDAR-based surface/landmark evaluation on the data already imported. | Primarily image blocks, not native ten-minute video. Multiple flight strips must not be presented as one pass. |
| [Zurich Urban MAV](https://rpg.ifi.uzh.ch/zurichmavdataset.html) | Extend existing AGZ integration using 1080p frames, GPS/IMU and calibration. Full archive approximately 28 GB. | Frame-to-video conversion; reference poses derive from photogrammetry rather than independent surveyed structure. The small publisher subset is mostly a stationary pre-flight interval; use moving segments from the full archive. |
| [KABR raw videos](https://huggingface.co/datasets/imageomics/KABR-raw-videos) | Genuine 4K/5.4K DJI video, most sessions with SRT, including clips over ten minutes. Useful decoding, dynamic-object and robustness tests. | Wildlife footage rather than a building-survey benchmark. Some files are trimmed and two early sessions lack SRT. Check per-session notes and select an uninterrupted moving-camera segment. No independent structural reference is advertised. |

MARS-LVIG's author page marks academic/non-commercial licensing. Keep LiDAR and withheld reference poses outside the reconstruction input when evaluating the monocular baseline. An RTK-assisted experiment should be labelled separately, and a reference fed to the optimiser cannot also serve as independent truth.

## What the organiser's fifteen-minute target means

The [official attachment](https://drive.google.com/file/d/119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD/view), page 2, gives a processing target but specifies no CPU, GPU, RAM, cloud allowance, power limit or timing boundary. It is therefore an incomplete hardware-comparison protocol. Do not infer a requirement to meet it on an RTX 5060, or permission to use an A100 at judging.

A100 hardware can materially change GPU-heavy processing and memory capacity; the speedup of the whole application must be measured. CPU decoding, optimisation, disk I/O, meshing and serial work do not inherit a GPU's theoretical speedup. CUDA kernels and neural models also respond differently. [NVIDIA A100 specifications](https://www.nvidia.com/en-us/data-center/a100/).

## Proposed benchmark to run

1. **Laptop track:** the actual RTX 5060 system, exact CPU/RAM/SSD, GPU VRAM, laptop power mode and driver/CUDA versions recorded.
2. **Server track, if available:** a specified A100 40/80 GB and PCIe/SXM variant, GPU allocation/MIG state, CPU/RAM and transfer costs recorded. Do not estimate its result from TFLOPS.
3. **Fixed workload:** identical source interval, input hash, resolution, frame rate, frame-selection policy, engine versions and output requirements. An additional hardware-tuned configuration may be compared, but record it separately.
4. **Timing boundary:** report compute wall time from locally available input through decoding, reconstruction, georeferencing, required mesh/cloud generation and export. Also report upload/transfer and total user waiting time. Disclose cold/warm caches and model startup; exclude cached reconstruction outputs from fresh-run claims.
5. **Quality parity:** report physical error where references exist, completeness, registration/failures and peak RAM/VRAM alongside runtime. A sparse preview is not a substitute for the final output at the same quality target.
6. **Repeatability:** run repeated trials when practical, retain stage timings and report variability. `processing time / video duration < 1.5` expresses the target for a 600-second input; it does not normalise hardware differences or justify extrapolating from a short clip.

The current AGZ dense artifact spends about 93% of its reported time in densification. This identifies a stage worth profiling; it does not establish the speedup an A100 will deliver. First run AirLock+ for actual-video behaviour, retain UseGeo for independent geometry checks, and add MARS-LVIG for a longer, reference-rich aerial test.

Organiser clarification to obtain: exact benchmark hardware and whether cloud execution is allowed; required final output and quality; start/end points of the timer; whether upload, model loading and export are included.
