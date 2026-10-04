# SIH 2026 presentation handoff

Use the [official 2026 PowerPoint template](https://www.sih.gov.in/letters/2026/SIH2026-IDEA-Presentation-Format.pptx). Its instructions allow **six slides including the title**, require the supplied structure and PDF submission, and say to remove the instruction slide. This document is content and speaking guidance, not a submission-ready deck; team identifiers and final experimental results still need to be supplied.

## Slide 1 — Title and problem identity

**Drishti3D — From one UAV pass to traceable spatial measurements**

- Problem statement: **SIH26158**.
- Title: Single-Pass Drone Video to Accurate 3D Model Generation System.
- Organisation: NTRO. Theme: Robotics and Drones. Category: Software.
- Team name: **[enter registered team name]**. Team ID: **[enter issued team ID]**.

**Visual:** one genuine reconstruction crop with a source-video inset. Label the dataset and indicate that it is a saved research result. Avoid a stock rendered city that could be mistaken for an output.

**Speaker note:** “Our focus is turning one recorded pass into spatial answers whose supporting evidence and limits an analyst can inspect.”

## Slide 2 — Proposed solution and distinctive contribution

**A measurement has to explain why it can be trusted.**

- Reconstruct georeferenced geometry from video and telemetry.
- Ask distance, height and area questions with a required tolerance.
- Show source observations, geometry provenance and decision limits.
- Reuse informative frames from the same recording to refine an eligible question.

**Visual:** four-step strip: recording → reconstruction → question → evidence/refinement. Show one actual question card and a visible estimated-only/refusal state.

**Speaker note:** “Video reconstruction and measurement already exist in other tools. Our proposed distinction is the combined question, evidence, refusal and targeted-refinement workflow. Calibrated acceptance is still an evaluation milestone.”

Do not claim that competitors have no confidence tools or that Drishti3D invented monocular reconstruction.

## Slide 3 — Technical approach

- React + TypeScript + Three.js workspace; FastAPI/Python backend.
- Quality/keyframe selection → OpenCV or COLMAP SfM → optional dense MVS.
- GPS/metadata alignment → ENU/georeferenced artifacts → measurement evidence.
- Optional learned components are identified by the exact tested configuration.

**Visual:** a compact architecture diagram and one real result panel. Use no more than three headline numbers: **60/60 selected cameras registered**, **2.14 M cloud points**, **444 engineering tests passed**. Label the first two UseGeo; make clear that these are not accuracy metrics.

**Speaker note:** “Our measured uncertainty is currently a geometric estimate. We retain a classical baseline and evaluate learned additions through ablations.”

Include hardware only for the experiment being shown, not a generic GPU logo or an unsupported real-time claim.

## Slide 4 — Feasibility, risks and validation

**Working prototype; the next milestone is independent compliance evidence.**

- Official targets: ≤1 m spatial accuracy; <15 min for a 10-minute video.
- Working: reconstruction, georeferencing, viewer, evidence, refinement and exports.
- Current gap: raw UseGeo LiDAR surface RMSE 1.283 m; dense runs exceed 20 minutes on shorter derived sequences.
- Plan: independent landmarks, datum/time checks, native-video timing and visible-scene completeness.

**Visual:** three rows—accuracy, completeness, speed—with “measured”, “gap”, “next test”. Link the organiser attachment in a small reference footer.

**Speaker note:** “These are separate tests: camera fit is not ground-truth accuracy, point count is not completeness, and a sparse-stage speedup is not an end-to-end timing result.”

Replace provisional figures only after the new scorer and raw artifacts are saved. Do not replace them with nearest-neighbour-derived dimensional accuracy without the qualification in the review.

## Slide 5 — Impact and benefits

- Help analysts turn a recording into inspectable spatial evidence.
- Reduce manual effort through guided questions and reusable source observations.
- Make missing coverage and unsupported answers visible before decisions.
- Validate practical benefit through task accuracy, time to answer and operator effort.

**Visual:** a single before/after analyst workflow with measurable milestones. Use proposed applications such as infrastructure inspection and disaster assessment, clearly labelled as intended uses.

**Speaker note:** “We will measure usefulness as correct tasks completed per mission and per unit of effort. We are not claiming deployments, financial savings or environmental benefits that have not been measured.”

## Slide 6 — Research and references

Use compact links/QRs with legible source titles:

- [SIH26158 official listing](https://www.sih.gov.in/sih2026PS) and [organiser attachment](https://drive.google.com/file/d/119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD/view).
- [COLMAP documentation](https://colmap.github.io/faq.html): reconstruction baseline.
- [WebODM](https://webodm.org/): closest product benchmark.
- [MASt3R-SLAM, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.html): learned video-reconstruction research.
- Project benchmark manifest, code revision and reproducible report pack: **[add team-accessible repository/report link]**.

**Visual:** a small comparison showing shared reconstruction functionality and the workflow Drishti3D is testing. Do not use unchecked crosses to claim a competitor lacks a feature.

## Demonstration sequence and handoff checklist

Suggested live sequence, independent of any formal organiser demo-time rule:

1. Open an existing completed mission; state dataset, engine and saved-run date.
2. Show source frames alongside the reconstructed region.
3. Ask a named measurement question; inspect the result status and supporting evidence.
4. Show a precomputed before/after refinement with its runtime and remaining blockers. Do not imply cached output was just reconstructed live.
5. Open the exported artifact/report and show CRS, units and version provenance.

Before submission: fill team identifiers, retain the official six-slide structure, verify every number against frozen artifacts, include the official source link, export to PDF and visually inspect all slides. The long project report supports the deck; it should not be submitted as the six-slide presentation.
