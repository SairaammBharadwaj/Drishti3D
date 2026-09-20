# Dataset inventory

Generated 2026-09-19 17:36 UTC by `drishti3d/scripts/inventory_datasets.py`.

Every figure below was read off the files in this checkout. Nothing here is carried over from an earlier report.

| Entry | Files | Size | LFS stubs | Path |
|---|---:|---:|---:|---|
| `zurich_mav/AGZ_subset` | 506 | 251.4 MB | 0 | `drishti3d/data/real_drone/AGZ_subset` |
| `zurich_mav/AGZ_subset.zip` | 1 | 279.2 MB | 0 | `drishti3d/data/real_drone/AGZ_subset.zip` |
| `zurich_mav/agz_dense` | 184 | 66.2 MB | 0 | `drishti3d/data/real_drone/agz_dense` |
| `zurich_mav/agz_pass` | 62 | 22.3 MB | 0 | `drishti3d/data/real_drone/agz_pass` |
| `zurich_mav/agz_seg2` | 62 | 43.6 MB | 0 | `drishti3d/data/real_drone/agz_seg2` |
| `zurich_mav/agz_seg2_raw` | 62 | 23.7 MB | 0 | `drishti3d/data/real_drone/agz_seg2_raw` |
| `zurich_mav/agz_undist` | 62 | 41.5 MB | 0 | `drishti3d/data/real_drone/agz_undist` |
| `video/goetheanum` | 1 | 76.0 MB | 0 | `drishti3d/data/real_drone/goetheanum.ogv` |
| `video/gymnasium_neubiberg` | 1 | 66.6 MB | 0 | `drishti3d/data/real_drone/gymnasium_neubiberg.webm` |
| `video/gymnasium_single_pass` | 1 | 71.4 MB | 0 | `drishti3d/data/real_drone/gymnasium_single_pass.mp4` |
| `video/st_lambertus` | 1 | 199.0 MB | 0 | `drishti3d/data/real_drone/st_lambertus.webm` |
| `other/shots` | 134 | 48.2 MB | 0 | `drishti3d/data/real_drone/shots` |
| `other/monterey_strip` | 44 | 481.7 MB | 0 | `drishti3d/data/real_drone/monterey_strip` |
| `other/odm_data_bellus-master` | 126 | 752.7 MB | 0 | `drishti3d/odm_data_bellus-master` |
| `other/sample_data` | 29 | 15.8 MB | 0 | `drishti3d/sample_data` |
| `mission/zurich_mav/agz_dense_pass` | 6 | 153.3 MB | 0 | `datasets/public/zurich_mav/agz_dense_pass` |

## Per-entry detail

### `zurich_mav/AGZ_subset`

- Path: `drishti3d/data/real_drone/AGZ_subset`
- 506 files, 251.4 MB, 0 unfetched LFS pointers
- Content digest: `a24fc34820014b55b94f43243d8600f79a716f5c520fdc2723b98f73b99911a9`
- Detail:

  ```json
  {
    "alt_msl_max_m": 467.7,
    "alt_msl_min_m": 464.9,
    "duration_s": 11.6,
    "eph_m_median": 9.12,
    "fix_types": [
      3
    ],
    "imgid_first": 1,
    "imgid_last": 350,
    "imgid_stride": 1,
    "median_step_m": 0.0,
    "n_images": 350,
    "n_reference_positions": 12,
    "n_telemetry_matched": 350,
    "net_displacement_m": 0.7,
    "path_length_m": 6.1
  }
  ```
- Publisher subset of the Zurich Urban MAV dataset: 350 MAV frames, 30 calibration images, 113 Street View images, and the full flight logs for all 81,169 frames.
- Reference camera positions in GroundTruthAGL.csv are Pix4D photogrammetry by the dataset authors, not independent RTK or LiDAR survey truth.
- UNUSABLE FOR RECONSTRUCTION AS SHIPPED: the 350 bundled MAV frames span 6.1 m of flight over 11.6 s (net displacement 0.7 m). This is a pre-flight hold, not a pass. No useful baseline means no triangulated depth. Flying segments must come from the full archive.
- OnboardGPS.csv epv_m is corrupt in the published release (values around 1e-43, not metres); vertical GNSS accuracy is unknown, not small.

### `zurich_mav/AGZ_subset.zip`

- Path: `drishti3d/data/real_drone/AGZ_subset.zip`
- 1 files, 279.2 MB, 0 unfetched LFS pointers
- Content digest: `e79bf9d3da628745b83bb24bde5a7117d53002111a3b3f59a02f4d134bba8d1c`
- Source archive for the extracted AGZ_subset/ above. Keep intact; do not re-extract over the working copy.

### `zurich_mav/agz_dense`

- Path: `drishti3d/data/real_drone/agz_dense`
- 184 files, 66.2 MB, 0 unfetched LFS pointers
- Content digest: `c82e8cae94689e818274c4d862310219bf80b2d6c5ccfaf1814e0063e28639fb`
- Detail:

  ```json
  {
    "alt_msl_max_m": 474.7,
    "alt_msl_min_m": 449.4,
    "duration_s": 184.4,
    "eph_m_median": 9.43,
    "fix_types": [
      3
    ],
    "imgid_first": 57211,
    "imgid_last": 62701,
    "imgid_stride": 30,
    "median_step_m": 1.17,
    "n_images": 184,
    "n_reference_positions": 184,
    "n_telemetry_matched": 184,
    "net_displacement_m": 201.9,
    "path_length_m": 233.1
  }
  ```
- Frame subset drawn from the full AGZ archive (frame ids outside the 1-350 publisher subset), rejoined to the bundled logs by imgid.
- Real single-pass geometry: 233.1 m flown in 184.4 s, median frame-to-frame baseline 1.17 m, 184 published reference positions.

### `zurich_mav/agz_pass`

- Path: `drishti3d/data/real_drone/agz_pass`
- 62 files, 22.3 MB, 0 unfetched LFS pointers
- Content digest: `403563d3d2bca4af1d0feb418acb0d2eb1866c7612e2c8e0893a6f061444bfd5`
- Detail:

  ```json
  {
    "alt_msl_max_m": 474.6,
    "alt_msl_min_m": 449.4,
    "duration_s": 184.4,
    "eph_m_median": 9.49,
    "fix_types": [
      3
    ],
    "imgid_first": 57211,
    "imgid_last": 62701,
    "imgid_stride": 90,
    "median_step_m": 3.48,
    "n_images": 62,
    "n_reference_positions": 62,
    "n_telemetry_matched": 62,
    "net_displacement_m": 201.9,
    "path_length_m": 228.8
  }
  ```
- Frame subset drawn from the full AGZ archive (frame ids outside the 1-350 publisher subset), rejoined to the bundled logs by imgid.
- Real single-pass geometry: 228.8 m flown in 184.4 s, median frame-to-frame baseline 3.48 m, 62 published reference positions.

### `zurich_mav/agz_seg2`

- Path: `drishti3d/data/real_drone/agz_seg2`
- 62 files, 43.6 MB, 0 unfetched LFS pointers
- Content digest: `9073bb94cfc26327eadebd83d8f0600f5c2da1936329771a2e7ed944aa4e3a2c`
- Detail:

  ```json
  {
    "alt_msl_max_m": 471.3,
    "alt_msl_min_m": 462.2,
    "duration_s": 183.0,
    "eph_m_median": 8.92,
    "fix_types": [
      3
    ],
    "imgid_first": 64531,
    "imgid_last": 70021,
    "imgid_stride": 90,
    "median_step_m": 2.8,
    "n_images": 62,
    "n_reference_positions": 62,
    "n_telemetry_matched": 62,
    "net_displacement_m": 160.4,
    "path_length_m": 174.8
  }
  ```
- Frame subset drawn from the full AGZ archive (frame ids outside the 1-350 publisher subset), rejoined to the bundled logs by imgid.
- Real single-pass geometry: 174.8 m flown in 183.0 s, median frame-to-frame baseline 2.8 m, 62 published reference positions.

### `zurich_mav/agz_seg2_raw`

- Path: `drishti3d/data/real_drone/agz_seg2_raw`
- 62 files, 23.7 MB, 0 unfetched LFS pointers
- Content digest: `1bd33c9d0dbaa2b926eb61bdca5b818f1673689f203873e949de1ea866663310`
- Detail:

  ```json
  {
    "alt_msl_max_m": 471.3,
    "alt_msl_min_m": 462.2,
    "duration_s": 183.0,
    "eph_m_median": 8.92,
    "fix_types": [
      3
    ],
    "imgid_first": 64531,
    "imgid_last": 70021,
    "imgid_stride": 90,
    "median_step_m": 2.8,
    "n_images": 62,
    "n_reference_positions": 62,
    "n_telemetry_matched": 62,
    "net_displacement_m": 160.4,
    "path_length_m": 174.8
  }
  ```
- Frame subset drawn from the full AGZ archive (frame ids outside the 1-350 publisher subset), rejoined to the bundled logs by imgid.
- Real single-pass geometry: 174.8 m flown in 183.0 s, median frame-to-frame baseline 2.8 m, 62 published reference positions.

### `zurich_mav/agz_undist`

- Path: `drishti3d/data/real_drone/agz_undist`
- 62 files, 41.5 MB, 0 unfetched LFS pointers
- Content digest: `184b361e39fa56cee18180d4f261a32ae8e58c44096515d2a7f7587980c8aac7`
- Detail:

  ```json
  {
    "alt_msl_max_m": 474.6,
    "alt_msl_min_m": 449.4,
    "duration_s": 184.4,
    "eph_m_median": 9.49,
    "fix_types": [
      3
    ],
    "imgid_first": 57211,
    "imgid_last": 62701,
    "imgid_stride": 90,
    "median_step_m": 3.48,
    "n_images": 62,
    "n_reference_positions": 62,
    "n_telemetry_matched": 62,
    "net_displacement_m": 201.9,
    "path_length_m": 228.8
  }
  ```
- Frame subset drawn from the full AGZ archive (frame ids outside the 1-350 publisher subset), rejoined to the bundled logs by imgid.
- Real single-pass geometry: 228.8 m flown in 184.4 s, median frame-to-frame baseline 3.48 m, 62 published reference positions.

### `video/goetheanum`

- Path: `drishti3d/data/real_drone/goetheanum.ogv`
- 1 files, 76.0 MB, 0 unfetched LFS pointers
- Content digest: `945d5b1c2bb360c17d7a886903614c3f717d1f37c027f16dc7cd642a037f7282`
- Detail:

  ```json
  {
    "avg_frame_rate": "0/0",
    "codec": "theora",
    "duration_s": 283.32,
    "height": 1080,
    "nb_frames": null,
    "r_frame_rate": "25/1",
    "width": 1920
  }
  ```
- No telemetry accompanies this clip in the checkout; usable as a visual/structural stress test only, never for a georeferenced or metric claim.

### `video/gymnasium_neubiberg`

- Path: `drishti3d/data/real_drone/gymnasium_neubiberg.webm`
- 1 files, 66.6 MB, 0 unfetched LFS pointers
- Content digest: `ea586cd1005f5d83ceaa845d3642c67468d2764da88d21afe2e0327871d576e1`
- Detail:

  ```json
  {
    "avg_frame_rate": "30/1",
    "codec": "vp9",
    "duration_s": 128.966,
    "height": 1080,
    "nb_frames": null,
    "r_frame_rate": "30/1",
    "width": 1920
  }
  ```
- No telemetry accompanies this clip in the checkout; usable as a visual/structural stress test only, never for a georeferenced or metric claim.

### `video/gymnasium_single_pass`

- Path: `drishti3d/data/real_drone/gymnasium_single_pass.mp4`
- 1 files, 71.4 MB, 0 unfetched LFS pointers
- Content digest: `1fb19620997802be7a36459ddb8f458f9f8bee8acc9bafc3ceb640766d4a69cb`
- Detail:

  ```json
  {
    "avg_frame_rate": "30/1",
    "codec": "h264",
    "duration_s": 63.5,
    "height": 1080,
    "nb_frames": "1905",
    "r_frame_rate": "30/1",
    "width": 1920
  }
  ```
- No telemetry accompanies this clip in the checkout; usable as a visual/structural stress test only, never for a georeferenced or metric claim.

### `video/st_lambertus`

- Path: `drishti3d/data/real_drone/st_lambertus.webm`
- 1 files, 199.0 MB, 0 unfetched LFS pointers
- Content digest: `abdf82baadacf54faa9e0f62e041e9a6491671c3036424700ef6785a1c0acafb`
- Detail:

  ```json
  {
    "avg_frame_rate": "19001/317",
    "codec": "vp8",
    "duration_s": 346.186,
    "height": 1080,
    "nb_frames": null,
    "r_frame_rate": "19001/317",
    "width": 1920
  }
  ```
- No telemetry accompanies this clip in the checkout; usable as a visual/structural stress test only, never for a georeferenced or metric claim.

### `other/shots`

- Path: `drishti3d/data/real_drone/shots`
- 134 files, 48.2 MB, 0 unfetched LFS pointers
- Content digest: `c3508731ac4838cd684b2fcd98176135f295d699a2571a7cc4e234bf070645f7`
- Cut-down frame sets extracted from the loose videos.

### `other/monterey_strip`

- Path: `drishti3d/data/real_drone/monterey_strip`
- 44 files, 481.7 MB, 0 unfetched LFS pointers
- Content digest: `7a86767f74d4b35b3ef60110cdc86c1aae3f83be89bafdd89fe38d097e96db06`
- Public drone photo strip; no telemetry logs in the checkout.

### `other/odm_data_bellus-master`

- Path: `drishti3d/odm_data_bellus-master`
- 126 files, 752.7 MB, 0 unfetched LFS pointers
- Content digest: `ed0bbc59f0e159059cf38a594847f9c295210b9815099284258b025f2b58dfc3`
- OpenDroneMap Bellus photo survey with gcp_list.txt. A photo survey, not a single-pass video capture.

### `other/sample_data`

- Path: `drishti3d/sample_data`
- 29 files, 15.8 MB, 0 unfetched LFS pointers
- Content digest: `30c82944670a0e38b092fb6819d6a71275dcf1fd1a321f4768e7add6fc2a83cd`
- Synthetic fixtures generated by drishti_recon.synth, with exact ground truth. Deterministic diagnosis only; never evidence of field accuracy.

### `mission/zurich_mav/agz_dense_pass`

- Path: `datasets/public/zurich_mav/agz_dense_pass`
- 6 files, 153.3 MB, 0 unfetched LFS pointers
- Content digest: `bf4da67de3849f9fe757f8bc76f62d2f0cbc2fbd9102a11b95a73968989dc88a`
- Detail:

  ```json
  {
    "allowed_claims": [
      "Relative reconstruction and metric reconnaissance on real aerial imagery with real consumer-grade GNSS."
    ],
    "artifacts": {
      "camera": {
        "path": "calibration/camera.json",
        "sha256": "bb6fe99341cbe0679878daaed41ce937a5a181c7258e1328c1d072b05a4fb7c9"
      },
      "frame_index": {
        "path": "raw/frame_index.csv",
        "sha256": "15a3e1f90f5a9df12ec6dfd70786a2255f86492ebbc27f6cf18a744fe313260e"
      },
      "telemetry": {
        "path": "raw/telemetry.csv",
        "rows": 184,
        "sha256": "270dc380a43b117da08da3a3f1f972fe69f826df929ba62f69ad7993dc4a9470"
      },
      "video": {
        "bytes": 153269857,
        "encoder": "libx264 crf=12 preset=slow, VFR from log presentation timestamps",
        "path": "raw/video.mp4",
        "sha256": "3b9bd9754db9c188e7fff96ee6994e5ff8d67fefb00c681b6adc7f6bc854e1da"
      }
    },
    "built_by": "drishti3d/scripts/build_agz_mission.py",
    "built_utc": "2026-09-19T17:10:57+00:00",
    "camera": {
      "cx": 951.1310042974931,
      "cy": 555.1335007742958,
      "distortion_applied_to_images": false,
      "fx": 893.3901081378665,
      "fy": 898.3264861625313,
      "image_height": 1080,
      "image_width": 1920,
      "k1": -0.2805251302544365,
      "k2": 0.1158064134556822,
      "k3": -0.027021503433937236,
      "model": "OPENCV",
      "notes": [
        "Intrinsics are for the full 1920x1080 frame; scale them if the pipeline processes at a reduced width.",
        "Strong barrel distortion (k1=-0.281). Images in raw/ are NOT undistorted; undistort once and carry the new intrinsics, never twice.",
        "The publisher does not state a calibration uncertainty."
      ],
      "p1": -0.0009843367849156311,
      "p2": 0.0001584792476978901,
      "source": "AGZ_subset/calibration_data.npz (publisher factory calibration from 30 checkerboard images)"
    },
    "capture": {
      "alt_msl_max_m": 474.7,
      "alt_msl_min_m": 449.4,
      "duration_s": 184.413,
      "gnss_eph_m_median": 9.43,
      "gnss_fix_types": [
        3
      ],
      "imgid_first": 57211,
      "imgid_last": 62701,
      "imgid_stride": 30,
      "median_frame_baseline_m": 1.17,
      "n_frames": 184,
      "net_displacement_m": 201.9,
      "path_length_m": 233.1
    },
    "dataset": "Zurich Urban Micro Aerial Vehicle (AGZ)",
    "known_deviations": [
      "video.mp4 is an H.264 re-encode of already-JPEG-compressed frames, not an original camera bitstream. Compression artefacts are therefore double-applied. Use raw/frame_index.csv to cite the original JPEG for any evidence display.",
      "The frame set is a stride subsample of a 30 Hz capture; the video is variable-frame-rate with the real log spacing between frames. Frames between the sampled ids exist in the full AGZ archive and are the natural candidate pool for same-pass refinement, but are not present in this checkout.",
      "sigma_u_m is empty: AGZ's epv_m column is corrupt in the published release. Vertical GNSS accuracy is unknown.",
      "Images are distorted; camera.json carries k1..k3,p1,p2 and distortion_applied_to_images is false."
    ],
    "mission_id": "agz_dense_pass",
    "prohibited_claims": [
      "Any independently validated survey deliverable. There are no independent checkpoints and no reference dimensions for this site.",
      "Any positional accuracy class: agreement with the AGZ reference is not an accuracy assessment."
    ],
    "reference": {
      "crs": "EPSG:32632 (WGS 84 / UTM zone 32N)",
      "independence": "NOT independent. Pix4D photogrammetry by the dataset authors over the full image set with loop closures; uncertainty not published.",
      "n_reference_positions": 184,
      "path": "datasets/truth/agz_dense_pass"
    },
    "schema_version": 1,
    "source_image_dir": "drishti3d/data/real_drone/agz_dense",
    "source_license": "AGZ MAV imagery: academic research use, per AGZ_subset/readme.txt"
  }
  ```
- Built mission in the plan's datasets/ layout; regenerate with scripts/build_agz_mission.py.

