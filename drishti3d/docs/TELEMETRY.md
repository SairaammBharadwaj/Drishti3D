# Telemetry schema

Drishti3D accepts **CSV**, **JSON**, or **SRT** (DJI-style) telemetry.

## Required fields
| Field | Meaning | Units |
|---|---|---|
| `timestamp` | time since video start (or absolute seconds) | seconds |
| `latitude` | WGS84 latitude | degrees |
| `longitude` | WGS84 longitude | degrees |
| `altitude` | ellipsoidal/GPS altitude | metres |

If `timestamp` is missing, the row index is used.

## Optional fields
`roll`, `pitch`, `yaw` (deg) · `velocity` (m/s) · `gps_accuracy` (m; used to
weight GPS alignment) · `rtk_status` (`RTK`/`FIXED`/`4` marks RTK) ·
`barometric_altitude` · camera intrinsics `fx`, `fy`, `cx`, `cy`,
`focal_length` (px).

## Recognised aliases
`lat`, `lon`/`lng`/`long`, `alt`/`height`, `time`/`t`/`ts`, `heading`/
`compass_heading` (→ yaw), `hdop`/`accuracy`/`hacc` (→ gps_accuracy),
`fix_type` (→ rtk_status), `gimbal_pitch` (→ pitch).

## CSV example
```csv
timestamp,latitude,longitude,altitude,yaw,gps_accuracy,rtk_status
0.000,28.613900,77.209000,220.5,90.0,0.4,RTK
0.033,28.613904,77.209010,220.6,90.2,0.4,RTK
```

## JSON example
```json
[{"timestamp":0,"latitude":28.6139,"longitude":77.2090,"altitude":220.5},
 {"timestamp":0.033,"latitude":28.61390,"longitude":77.20901,"altitude":220.6}]
```
(A `{"samples": [...]}` wrapper is also accepted.)

## SRT
DJI subtitle streams containing `[latitude: …][longitude: …][abs_alt: …]` and a
`HH:MM:SS,mmm` timecode are parsed automatically.

## Validation
Rows with out-of-range lat/lon or non-finite altitude are **skipped and
reported** in the run warnings — never silently dropped. At least two valid
samples are required.
