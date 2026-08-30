# Drishti3D / SIH26158 — Canonical Project Memory

> Last updated: 27 August 2026  
> Purpose: Durable handoff context for future sessions. Read this file first, then follow the linked research documents.

## Goal

The primary goal is to maximize the probability of winning Smart India Hackathon 2026. The selected leading problem is **SIH26158**, submitted by NTRO: convert a single-pass drone video plus GPS and flight metadata into a georeferenced, metrically scaled, measurable 3D representation.

The working product name is **Drishti3D**.

The central product thesis is:

> Drishti3D turns a single operational drone pass into an evidence-backed 3D intelligence product and clearly distinguishes what was measured, what is uncertain, what was AI-assisted, what was dynamic and excluded, and what was never observed.

## Non-negotiable scientific position

Monocular video can recover relative geometry and camera motion through temporal multi-view parallax, but it does not independently establish global metric scale. GPS/GNSS, RTK/PPK, GCPs, IMU, calibrated altitude, or known dimensions are required for metric and geographic claims.

A surface absent from every input frame cannot be measured. AI may complete it visually, but the completion must not be presented as observed truth.

Required provenance classes:

- `OBSERVED_HIGH_CONFIDENCE`
- `OBSERVED_LOW_CONFIDENCE`
- `AI_ASSISTED`
- `DYNAMIC_EXCLUDED`
- `UNOBSERVED`

Measurements exclude inferred geometry by default.

## Architecture decision

Use a hybrid pipeline with a mandatory classical verified path and optional learned assistance.

The verified path is video ingestion, timestamp/telemetry synchronization, frame quality, adaptive keyframes, dynamic masking, COLMAP/PyCOLMAP reconstruction, bundle adjustment, robust GNSS Sim(3) alignment into local ENU, point-cloud cleanup, confidence/provenance, measurement, exports, and an evidence report.

VGGT and MASt3R-SLAM are optional preview/initializer/recovery adapters. They must not be the only working route. Their output begins as `AI_ASSISTED` and can be promoted only after explicit geometric verification.

Use a modular monolith with an isolated reconstruction worker. Keep immutable input and artifact manifests with SHA-256, versions, parameters, parents, coordinate frame, units, and stage lineage. Make stages restartable and cache-aware.

## Recommended implementation order

1. Reproducible Python 3.11 environment, FFmpeg, COLMAP, capability probe, artifact model, and synthetic fixture.
2. Upload, telemetry parsing, PTS-based synchronization, frame quality, adaptive keyframes, job progress, and tests.
3. Real COLMAP sparse reconstruction from uploaded frames and a viewer with camera poses.
4. WGS84/ECEF/ENU conversion, robust weighted Sim(3), metric distance/height/area, checkpoints, and reports.
5. Dynamic masking, dense reconstruction, cleanup, and calibrated confidence/provenance.
6. Optional VGGT and MASt3R-SLAM experiments.
7. Offline packaging, demo hardening, and final evidence pack.

Protect real reconstruction, alignment, measurement, and evidence before mesh polish or additional AI models.

## Local environment observed

- Windows with PowerShell 5.1
- Python 3.13.5 installed globally; use an isolated Python 3.11 environment for reconstruction compatibility
- Node 24.11.1 and npm 11.6.2; pin a supported Node LTS for the frontend
- Docker 29.6.1
- NVIDIA GeForce RTX 4060 Laptop GPU with 8188 MiB VRAM
- NVIDIA driver 610.88
- FFmpeg/ffprobe were not on PATH
- COLMAP was not on PATH

The 8 GB GPU requires measured resolution/VRAM experiments for learned models. Do not promise paper-reported FPS on this hardware.

## MASt3R-SLAM decision

MASt3R-SLAM is highly relevant as a fast dense preview, initializer, or difficult-scene recovery engine. Useful ideas include ray-based tracking for unknown/changing intrinsics, confidence-weighted pointmap fusion, motion-aware keyframing, retrieval-proposed loop closures, and separate pose versus geometry evaluation.

It does not independently solve georeferencing, metric validation, dynamic filtering, or unobserved surfaces. Its paper reports roughly 15 FPS in its tested configuration; this is not a promise for the RTX 4060. Its full dense geometry is not globally refined in the backend. The MASt3R ecosystem has CC BY-NC-SA restrictions requiring review. Keep it optional.

## SIH winning strategy

Official SIH idea-selection dimensions include novelty, complexity, clarity, feasibility, practicability, sustainability, impact, user experience, and future progression.

The flagship scenario is rapid post-disaster infrastructure assessment: one safe drone pass becomes a local, measurable 3D scene with confidence and coverage feedback.

The memorable demo moment is a judge selecting two points on a real reconstruction, receiving a metric measurement with provenance/confidence, and comparing it with independent truth.

The strongest differentiation is not “we accept video” or “we use AI.” PIX4Dmapper and OpenDroneMap already support video/frame extraction. The defensible wedge is telemetry-aware single-pass optimization, explicit observation provenance, measurement safeguards, independent accuracy evidence, offline reproducibility, and actionable coverage/recapture feedback.

Do not make universal claims that competitors lack video, confidence, GCPs, or offline support without testing named versions and citing official evidence.

## Accuracy and evaluation rules

Never confuse alignment residual with independent accuracy. GCPs/control used by the solution must remain separate from checkpoints used to evaluate it.

Report registered keyframes, reprojection-error distributions, track length, triangulation angle, ATE/RPE where truth exists, horizontal/vertical/3D alignment residual, independent checkpoint error, known-dimension error, surface accuracy/completeness, dynamic contamination, confidence calibration, runtime, RAM/VRAM, and processing-time/video-duration ratio.

ASPRS Edition 2 Version 2 uses independent checkpoint methodology and a minimum of 30 checkpoints for formal accuracy assessment. A smaller hackathon experiment must not claim standards-compliant certification.

Use a synthetic deterministic fixture, public trajectory/surface datasets such as TartanAir/EuRoC/ETH3D where suitable, and one team-captured drone dataset with independent reference measurements.

## Current problem-statement ranking

Independent win-worthiness assessment:

1. SIH26158 Drone-to-3D — 8.8/10, primary choice
2. SIH26143 oil-spill detection plus AIS attribution — 8.4/10, best fallback
3. SIH26037 adaptive planning on unstructured Indian roads — 8.1/10
4. SIH26059 Antarctic sea-ice/iceberg navigation — 7.9/10
5. SIH26054 MALE UAV engine digital twin — 7.8/10
6. SIH26161 dam-break inundation — 7.3/10
7. SIH26142 satellite super-resolution — 7.2/10
8. SIH26038 explainable diabetic-retinopathy screening — 7.1/10
9. SIH26189 criminal-network analysis — 7.0/10
10. SIH26057 side-scan-sonar marine debris — 6.9/10
11. SIH26192 hilly-region flash-flood prediction — 6.5/10
12. SIH26085 urban flood nowcasting — 6.3/10

The ranking is conditional on team capability and data access. The official portal must be checked for attached datasets, changing idea counts, exact wording, and deadline.

## Immediate technical gate

Before further UI work, obtain a real 30–60 second drone clip with synchronized telemetry and a known reference distance. Install or containerize FFmpeg and COLMAP. Produce a genuine reconstruction, align it into metric ENU, and measure the reference. Repeat the process reliably.

If this gate fails after a disciplined feasibility spike, pivot early to SIH26143 or SIH26037. Do not wait until after building a polished interface.

## Source and deadline caveat

Community mirrors report a 20 September 2026 deadline based on a 21 August snapshot of the official SIH records. This must be verified directly on `sih.gov.in`; a mirror is not the final authority.

## Research files

### Primary authority

- `codex_research/DRISHTI3D_MASTER_RESEARCH_AND_ARCHITECTURE.md` — master scientific, architectural, evaluation, security, SIH, implementation, and MASt3R-SLAM blueprint.
- `codex_research/SIH_2026_TOP_PROBLEM_STATEMENTS_WIN_WORTHINESS.md` — narrative comparison of twelve candidate statements.

### Comparative review

- `codex_research/CLAUDE_VS_CODEX_RESEARCH_REVIEW.md` — evaluation of Claude and Codex research, including verified corrections to competitive claims.
- `claude_research/Drishti3D_Complete_Research_Dossier.md` — stronger pedagogical explanation and glossary; use with the corrections recorded in the comparative review.

### Original input

- `SIH26158_Drishti3D_research_and_claude_prompt.md` — initial brief and implementation prompt.

## How a future session should resume

Read this memory file, then the master research’s executive/SIH sections and current appendices. Inspect the workspace before acting. Preserve the scientific and provenance invariants. Verify current external facts before repeating them. The next productive action is implementation or the real-data feasibility gate—not more generic architecture research unless new official material changes the problem.

