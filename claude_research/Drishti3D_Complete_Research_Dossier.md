# Drishti3D — Complete Project Research Dossier

### Single-Pass Drone Video → Accurate, Georeferenced 3D Model Generation

**Problem statement:** SIH26158 · **Organization:** National Technical Research Organisation (NTRO)
**Category:** Software · **Theme:** Robotics & Drones
**Working product name:** Drishti3D
**Document purpose:** A single, self-contained reference that takes you from "I know nothing" to "I can explain the problem, the science, the architecture, the stack, the risks, and exactly how we win SIH26158." Read it top to bottom once; use the Table of Contents to return to any part later.

**Prepared:** 2026-08-27 · **Lens:** Everything below is framed around one goal — **winning SIH26158 with a real, defensible, working prototype.**

---

## How to read this document

This dossier is layered. If you read only three sections, read **§1 (the problem decoded)**, **§4 (the core scientific truth)**, and **§15 (the winning strategy)** — together they contain the entire soul of the project. The rest gives you the depth to defend every sentence of those three under questioning.

A recurring idea threads through the whole document, so meet it now: **a single-pass drone video can honestly deliver a metrically accurate 3D model of the surfaces it actually saw — and it must never pretend to have measured the surfaces it did not.** Most teams will miss this. It is simultaneously the hardest scientific constraint and our single biggest competitive advantage. Hold onto it.

---

## Table of Contents

1. The Problem Statement, Decoded
2. The Program — Understanding SIH and How It Is Won
3. The Customer — NTRO and Why This Capability Matters
4. The Core Scientific Truth (the intellectual heart)
5. The Competitive Landscape and Our Wedge
6. The Solution — Drishti3D System Architecture
7. The Reconstruction Pipeline, Stage by Stage
8. Coordinate Systems and Georegistration — the Metric Backbone
9. The Technology Stack — Every Tool, Why, License, GPU
10. Reconstruction Engines Compared (COLMAP / VGGT / MASt3R-SLAM / DROID-SLAM)
11. Evaluation, Metrics, and Defensible Accuracy Claims
12. Frontend and User Experience
13. Security and Offline Operation
14. Risks, Limits, and Honest Constraints
15. The Winning Strategy — Demo, Pitch, and Judge Q&A
16. Execution Roadmap to the Finale
17. Glossary of Every Term Used
18. Open Decisions and References

---

## 1. The Problem Statement, Decoded

### 1.1 What SIH26158 literally asks for

Build an **AI-enabled software system** that takes:

- a **single-pass UAV (drone) video** — one continuous flyover, *not* a planned repeat-grid photo mission,
- the drone's **GPS coordinates**, and
- **flight metadata** (telemetry: altitude, orientation, timing, camera parameters where available),

and produces a **georeferenced and metrically accurate 3D representation** of the scene. "Georeferenced" means every point sits at a real-world coordinate (latitude, longitude, elevation). "Metrically accurate" means distances, heights, and areas measured on the model correspond to true metres on the ground.

The desired outputs enumerated by NTRO: **terrain, structures, façades, rooftops, roads, infrastructure, vegetation, obstacles, point clouds, and textured meshes** — usable for **measurement, visualization, and analysis**.

### 1.2 What the words secretly demand (reading between the lines)

Each phrase in the statement hides a hard technical requirement. Decoding them is how you show a judge you *understand* the problem rather than just restating it:

| Phrase in the statement | What it actually requires |
|---|---|
| "Single-pass video" | You get **one trajectory**. No revisits → no loop closure → drift must be controlled by GPS/IMU (see §4.4). Large parts of the scene will be **unseen**; you must handle that honestly (see §4.6). |
| "GPS coordinates + flight metadata" | These are your **only source of metric scale and geolocation**. Monocular video alone cannot recover true size (see §4.5). Telemetry quality directly bounds output accuracy. |
| "Metrically accurate" | The output must be validated against **ground truth** with real error numbers (RMSE), not asserted. Accuracy claims without evidence are a disqualifier. |
| "Georeferenced" | You must correctly handle **geodesy** — WGS84, ECEF, ENU, height datums (see §8). Mixing degrees and metres is a classic, fatal bug. |
| "Terrain, structures, … obstacles" | Implies **semantic awareness** and, for a moving scene, **dynamic-object removal** (cars, people) so they don't pollute a static map. |
| "For measurement" | Measurements must be **trustworthy**. That forces the central design idea: distinguish **measured** geometry from **inferred/AI-completed** geometry and never let the latter drive a measurement silently (see §4.7). |
| "AI-enabled" | Judges expect meaningful AI — learned depth, learned matching, learned reconstruction priors, semantic masking — not a buzzword. But AI must augment a verifiable geometric backbone, not replace it. |

### 1.3 The one-sentence thesis

> **Drishti3D turns a single drone flyover into a georeferenced 3D model in which every surface is explicitly labelled as measured or inferred, so operators can trust the numbers they act on.**

That sentence is the whole pitch. Everything else in this document exists to make it true and defensible.

---

## 2. The Program — Understanding SIH and How It Is Won

### 2.1 What SIH is

The Smart India Hackathon (SIH) is a nationwide, government-run open-innovation competition organized by the Ministry of Education's Innovation Cell with AICTE, running annually since 2017. Government ministries, PSUs, and industry submit **real-world problem statements**; student teams pick one and build a solution. It runs as parallel **Software** and **Hardware** editions (plus a schools "Junior" track). SIH26158 is a **Software-edition** statement submitted by NTRO.

Scale for context: recent editions release **hundreds** of problem statements across ~17 themes (SIH 2026 released 226 in its first lot — 172 software + 54 hardware). SIH26158 sits in the **Robotics & Drones** theme.

> *Verification note:* Exact calendar dates and prize figures vary by edition and were drawn from secondary guides, not the official sih.gov.in portal, in our research pass. Confirm the current cycle's dates, prize (commonly cited around ₹1 lakh per winning statement), and rules on the official portal before relying on them.

### 2.2 The format and the timeline

1. **Problem-statement release** and institution/SPOC registration.
2. **Internal college hackathon** — each college shortlists and nominates teams.
3. **Idea submission & online screening** — a fixed-template **PPT** (and often a video); national-level screening selects finalists.
4. **Grand Finale** — a **36-hour non-stop hackathon** held simultaneously at multiple **nodal centers** nationwide, with juries evaluating each team **several times** during the 36 hours (not one final pitch).

**Team rules (recent editions):** exactly **6 students** from the **same institution**, **at least one female member mandatory**, members may be **cross-departmental**, plus 1–2 mentors.

### 2.3 What the judges actually reward — and how we target each

Juries typically pair an **industry expert with an academic**, and they visit repeatedly. From the patterns in how SIH is judged, five things win — mapped here to our concrete plan:

| What judges reward | How Drishti3D delivers it |
|---|---|
| **A live, working prototype** (mockups and hardcoded demos get caught) | We commit to a real reconstruction from *uploaded* video on stage — at least one pipeline path produces genuine geometry. No canned 3D model. This is our non-negotiable (see §6.3, §15). |
| **Genuine, meaningful AI** | Learned depth/matching, feed-forward 3D (VGGT/MASt3R-SLAM adapters), semantic dynamic-object masking — all with a clear role, not decoration. |
| **Deep problem understanding** | The §1.2 decoding and the scientific-honesty thesis show we understand *why the problem is hard*, which most teams won't articulate. |
| **Feasibility, impact, scalability** | Honest accuracy targets (§11), a real operational customer story (§3), and a modular architecture that scales from laptop to GPU server (§6). |
| **A crisp startup-style pitch** | The §15 narrative and demo script; the memorable hook is the confidence-coloured 3D model. |

### 2.4 The meta-insight for winning

Most teams attacking a "video → 3D" statement will do one of two things: (a) wrap an existing tool and show a pretty model, or (b) fake a slick dashboard over a pre-baked asset. Both are fragile under expert questioning ("Is that scale real? How accurate? What's the far side of that building — did you measure it?").

**Our edge is intellectual honesty made visible.** By explicitly separating *measured* from *inferred* geometry and showing per-point confidence, we answer the exact questions that expose other teams — and we do it as a *feature*, not an apology. Judges remember the team that understood the science. That is the wedge (developed fully in §4.7 and §15).

---

## 3. The Customer — NTRO and Why This Capability Matters

### 3.1 Who NTRO is (public information only)

The **National Technical Research Organisation** is India's premier **technical-intelligence (TECHINT)** agency, established in 2004, operating under the Prime Minister's Office and reporting to the National Security Advisor. Its public mandate spans **geospatial/imagery intelligence (GEOINT/IMINT)**, **signals intelligence (SIGINT)**, **cyber security** (it is the parent of NCIIPC, which protects critical information infrastructure), and **cryptology**. It functions as a "super-feeder" — supplying technical intelligence to other agencies and the armed forces.

Publicly, NTRO has historically leaned heavily on **satellite** imagery (Cartosat, RISAT, EMISAT-class assets) and was noted to lack its own large aircraft/UAV fleet. That gap is precisely why a **lightweight, deployable drone-video → 3D** capability is strategically resonant: it complements slow-revisit, cloud-limited satellite IMINT with **on-demand, higher-resolution, ground-level 3D** from a cheap platform.

> *Honesty note:* No public NTRO document states a "single-pass 3D" requirement. The operational rationale below is **reasoned inference from NTRO's public mandate**, not sourced doctrine. Present it that way — never imply official endorsement or attach fake classified markings (the problem brief explicitly forbids this, and doing so reads as amateurish to a defense-adjacent jury).

### 3.2 Why "single-pass" is operationally sacred

A conventional survey-grade 3D map needs a **planned overlapping grid ("lawnmower") mission** plus orbits — hundreds of stills, structured flight planning, multiple minutes-to-hours over the target. In the situations NTRO cares about, you often **cannot** do that:

- **Reconnaissance in contested airspace:** every second over a target is exposure and detection risk. One fast pass minimizes both.
- **Time-critical crises:** after an earthquake or flood, video is frequently the *first* airborne data available; there is no time to plan a grid.
- **Covertness and simplicity:** a single flyover needs no elaborate mission plan and can be flown by non-specialists.

So the constraint "single pass" is not an arbitrary difficulty — it mirrors **real operational reality**, and a system that embraces it (rather than assuming an ideal grid) is genuinely useful. That framing plays extremely well with an NTRO-adjacent jury.

### 3.3 The operational use cases (and the accuracy each needs)

| Use case | Why single-pass matters here | Accuracy typically needed |
|---|---|---|
| **Military / intelligence reconnaissance** | Minimizes exposure; on-demand and higher-res than satellite | Relative cm–dm on target geometry; absolute improves with RTK/PPK/GCP |
| **Disaster response** (quake/flood damage) | Video is the first data available; no time for grid missions | Studies show video-3D within **~2 cm** of photo-based 3D; debris-volume error <0.5% in one case |
| **Infrastructure inspection** (bridges, towers, lines) | One orbit captures full structure geometry | 1–3 cm with GCPs; ~3 cm vertical with survey LiDAR at 120 m |
| **Urban / terrain mapping** | Rapid coverage without multi-day campaigns | dm–cm; GCPs move absolute error from 1–3 m (GPS) to 1–3 cm |
| **Mining / volumetrics** | Single flyover yields a volumetric surface | ~1–3 % volumetric error |
| **Precision agriculture** | Fast single-pass field coverage | cm–dm; relative accuracy usually sufficient |

**The load-bearing evidence for the whole project thesis:** a peer-reviewed disaster-response study (NHESS 2018) found aerial **video** and **photos** give nearly identical 3D usability — only a **~2 cm** external-accuracy gap, comparable damage classification, and video sometimes *better* on volume estimation. This is the citation that lets us say, credibly, **"single-pass video is good enough for rapid operations"** — the premise our product rests on.

### 3.4 Pick ONE flagship scenario and make the whole prototype cohere around it

A spread of six use cases proves breadth but wins nothing on stage. Choose **one** and make every demo action serve it. Recommended flagship:

> **Rapid post-disaster infrastructure assessment** — a drone gets one safe pass over a damaged bridge/building corridor; Drishti3D produces the observed 3D scene, flight path, structure geometry, measurements, and per-surface confidence, entirely offline.

Why this scenario beats the others for the demo: it *explains why there is only one pass* (danger/time), makes near-real-time processing obviously valuable, makes offline/air-gapped credible and important, makes measurements decision-relevant, and naturally surfaces dynamic objects, occlusion, and poor access. Mention military/intelligence reconnaissance as an *application*, but demo on a safe campus/structure dataset — never simulate classified branding or sensitive coordinates. Everything in §15 (pitch, demo, Q&A) should be told through this one scenario.

---

## 4. The Core Scientific Truth (the intellectual heart)

This section is the one to understand *cold*. If you can explain §4.5 and §4.6 to a judge at a whiteboard, you have already beaten most of the field. We build from "how does 3D-from-video even work?" up to the two hard limits and the confidence idea that turns those limits into our advantage.

### 4.1 How a moving camera sees depth — parallax

A single camera moving through a static scene photographs the same 3D points from many positions. Nearer points shift more between frames than farther points — the way roadside trees streak past a car window while distant mountains barely move. This differential motion is **parallax**, and it is the raw signal that encodes depth. Every technique below is a way of turning parallax into geometry.

### 4.2 Structure from Motion (SfM) — recovering shape and camera path together

SfM solves a chicken-and-egg problem: you can't know where a 3D point is without knowing where the cameras were, and you can't solve camera poses without knowing which 3D points they saw. It bootstraps out of this as follows:

1. **Feature detection & description.** In each frame, find a few thousand distinctive, repeatable local points ("keypoints") and describe each one's neighbourhood with a vector (a *descriptor*) that survives changes in scale, rotation, and lighting. The classic is **SIFT**; fast alternatives include ORB and AKAZE; modern learned versions are **SuperPoint** (§4.7).
2. **Matching.** Match keypoints between frames by nearest-descriptor. Lowe's ratio test and **RANSAC** geometric verification throw out bad matches. The surviving chains — one physical point seen across many frames — are **feature tracks**.
3. **Epipolar geometry.** Two views of the same scene are geometrically linked: a point in image 1 must lie on a specific line (its *epipolar line*) in image 2. This constraint is captured by the **fundamental matrix F** (uncalibrated cameras) or the **essential matrix E** (calibrated). Decomposing E yields the **relative rotation and the *direction* of translation** between two cameras.
   - **The seed of everything hard:** E gives translation *direction* but **not magnitude** — you learn which way the camera moved, never how far. Monocular scale ambiguity (§4.5) is born right here.
4. **Triangulation.** With relative pose known, each matched pixel is a ray in 3D; the two rays should meet at the point. Their intersection (in practice the least-error point) is the triangulated 3D position. Reliability depends critically on the **angle between the rays** — the triangulation/parallax angle (§4.8).
5. **Grow & refine.** *Incremental* SfM (COLMAP's default) registers each new image via **PnP** (pose from 2D–3D correspondences), triangulates new points, and repeatedly runs bundle adjustment. *Global* SfM solves all rotations then translations at once — faster, but more fragile to outliers. For drone video (ordered, high-overlap frames), sequential/video-aware matching is natural.

*SfM and "photogrammetry" overlap heavily; photogrammetry is the older surveying term and usually implies the full pipeline through dense reconstruction and metric georeferencing.*

### 4.3 Bundle Adjustment (BA) — the accuracy backbone

Take every 3D point, project it back into every camera that saw it using the current pose and intrinsics, and measure the pixel gap between the projection and the actually-observed keypoint. That gap is the **reprojection error**. BA jointly nudges **all camera poses and all 3D points** (optionally the camera **intrinsics** too — "self-calibration") to minimize the sum of squared reprojection errors across every observation:

> minimize Σ over (camera *i*, point *j*) of ‖ observed_pixel(i,j) − project(cameraᵢ, pointⱼ) ‖²

Everything upstream is a greedy local estimate with accumulated error; BA is the single global nonlinear least-squares optimization (Levenberg–Marquardt, exploiting sparsity via Ceres/g2o, with a robust Huber/Cauchy loss) that reconciles all measurements at once. It is what turns a rough skeleton into a metrically consistent (up to scale) reconstruction.

**What BA cannot do:** it cannot recover absolute scale (a uniformly scaled world has *identical* reprojection error — §4.5), and it cannot invent points never observed (§4.6). Keep these two impossibilities in mind — they define the honest boundary of the product.

### 4.4 Dense reconstruction (MVS) and the SLAM-vs-SfM distinction

**Multi-View Stereo (MVS).** SfM outputs only a *sparse* cloud (the few thousand matchable keypoints per frame) — enough for camera poses, far too sparse for a usable surface. MVS takes the now-known poses as fixed input and estimates depth for (ideally) *every pixel*:
1. **Per-image depth maps** by sweeping candidate depths and keeping the depth where a pixel's neighbourhood, projected into neighbouring frames, matches best (photo-consistency). **PatchMatch stereo** does this efficiently and also estimates a per-pixel surface normal, handling slanted surfaces.
2. **Depth-map fusion** merges the noisy per-image maps, keeping only depths that agree across multiple views (this cross-view agreement is itself a confidence filter).
3. **Optional meshing** (Poisson or ball-pivoting) + texture mapping.

MVS relies on photo-consistency, so it **struggles on textureless walls, reflective/transparent surfaces, and repetitive patterns** — producing holes or noise even where the surface *was* observed.

**Visual SLAM vs SfM.** Both recover structure + motion from images; the difference is regime and intent:

| | **SfM** | **Visual SLAM** |
|---|---|---|
| Timing | Offline, batch, all frames at once | Online, real-time, frame by frame |
| Goal | Best possible reconstruction accuracy | Localize *now* + build a usable map within a latency budget |
| Optimization | Global BA over everything | Local/windowed BA; global only at loop closure |

Key SLAM ideas: **keyframes** (map only a representative subset of frames, not all 30 fps), **drift** (incremental pose errors accumulate along the path), and **loop closure** (recognizing a revisited place and redistributing accumulated error via pose-graph optimization).

**The single-pass consequence — write this on the whiteboard:** a single forward flyover has **no revisits, therefore no loop closures**, therefore **drift along the flight direction is uncorrected unless an external signal (GPS/IMU) constrains it.** This is a structural limitation of single-pass capture, independent of how good the algorithm is — and it is exactly why the problem statement hands us GPS and telemetry.

### 4.5 THE MONOCULAR SCALE-AMBIGUITY PROBLEM ★

**The claim:** one moving camera recovers the scene's **shape** and the camera's **relative motion**, but **not its absolute metric size**. The identical set of images could depict a real house across the street or a dollhouse on a desk.

**Why — the mechanism (the argument that impresses judges):** scale the entire world by a factor *s* — every 3D point and every camera translation ×*s*. A perspective camera projects by *dividing by depth* (`u = f·X/Z`). If X and Z both scale by *s*, the ratio X/Z is unchanged, so **every pixel lands in exactly the same place.** The reprojection error is *identical* for the true scene and any uniformly scaled copy. Since images are all a monocular camera has, no algorithm operating on images alone can prefer one scale. This is **not** a weakness of current methods — it is a **fundamental unobservability**, a gauge freedom in the problem.

**The precise language — Sim(3) vs SE(3):**
- **SE(3)** = rigid transforms (rotation + translation, 6 DoF). Preserves distances. The space of genuine poses in a *metric* world.
- **Sim(3)** = similarity transforms (rotation + translation + **one uniform scale**, 7 DoF). Preserves shape/ratios but not absolute size.
- A purely monocular reconstruction is determined **only up to a Sim(3) transform.** To get a metric (SE(3)) model you must **pin the extra scale degree of freedom** with information from outside the images.

**How we recover metric scale — supply that missing DoF externally:**
- **GPS camera positions** — real-world metres per frame; even coarse GPS over a long flight fixes overall scale and rough geolocation. *(Standard for drone work; this is our default.)*
- **RTK / PPK GNSS** — centimetre-level camera positions; the gold standard, giving accurate scale *and* absolute georeferencing together.
- **IMU (visual-inertial)** — accelerometers measure real m/s²; fused with vision this gives metric scale and fights drift. *Caveat: IMU scale is only well-observed under sufficient acceleration; near-constant-velocity flight weakens it.*
- **Known object / Ground Control Point** — one known real-world distance fixes scale and improves absolute accuracy.
- **Stereo rig** — a known fixed baseline *is* a ruler (but that exits the monocular regime).

**Bottom line for Drishti3D:** monocular drone video **must** be paired with GPS (ideally RTK/PPK) and/or IMU to yield metrically meaningful numbers. Without them, the model is shape-correct but scale-arbitrary, and *any* length/area/volume is meaningless. This is why our pipeline treats georegistration (§8) as core, not optional.

### 4.6 THE UNOBSERVED-SURFACE PROBLEM ★

**The claim:** a single flight path physically **cannot measure** surfaces it never saw — the far side of a building, the underside of an overhang, an interior courtyard. This is a statement about *information*, not about software quality.

**Why — the mechanism:** reconstruction is triangulation *from observations*. A 3D point's position is inferred from its appearance in ≥2 images. A surface that never projected into *any* frame contributed **zero measurements** — no photo-consistency signal, no feature track, nothing to triangulate. You cannot least-squares your way to a quantity for which you have no equations. The far wall, seen from a drone that only flew along the front, is simply **absent from the input.**

The governing concepts are **occlusion** (near geometry hides far geometry) and **coverage** (a surface is measurable only if it falls in the field of view, at adequate resolution, from ≥2 sufficiently-separated viewpoints, unoccluded). A single linear pass satisfies this only for surfaces facing the flight corridor — which is exactly why survey missions fly grids *plus* orbits to guarantee all-face coverage. Single-pass capture inherently leaves large unobserved regions.

**Why AI "completion" is inference, not measurement:** learned models can *plausibly fill* unseen regions from statistical priors ("the backs of buildings usually look like this"). The result may look convincing and even be approximately right for regular structures — but it is a **prediction conditioned on training data**, not a measurement of *this* object, and it can be confidently wrong (an unusual rear façade, a hidden extension, undocumented damage). For a measurement product used in intelligence or disaster response, that distinction is **safety-critical**.

**The design consequence (this is the product):** completed geometry must be **clearly labelled as inferred**, kept in a **separate layer**, and **never feed a metric claim as if measured.** The honest system reports coverage and marks holes rather than silently closing a surface. This constraint, embraced openly, becomes our differentiator (§4.7).

### 4.7 Confidence and provenance — turning the limits into the winning idea ★★

The two hard limits above (unknown scale, unseen surfaces) plus the ordinary noisiness of reconstruction mean **not every point deserves equal trust.** A measurement system should *attach and visualize* per-point confidence. The geometric signals that tell us how much to trust a point:

- **Reprojection error** (§4.3) — after BA, how many pixels a point misses its observations by. Low & consistent ⇒ well-constrained; high or erratic ⇒ suspect. The most direct per-point quality signal.
- **Triangulation angle / parallax / baseline (the big one)** — the angle between the rays that triangulated the point. Two near-parallel rays (small angle) meet at a shallow, ill-conditioned intersection where a tiny pixel error swings depth enormously. Depth uncertainty scales roughly as **1/parallax**. **Wide baseline ⇒ sharp, confident depth; weak baseline ⇒ low confidence.** (Drone-specific: points far off the flight line, or seen only over a short straight segment, have small parallax and are inherently low-confidence even if the pixels matched perfectly.)
- **Feature-track length / observation count** — a point seen in 15 frames is far more trustworthy than one triangulated from 2; more observations average out noise and expose outliers. Short tracks are the fragile tail.
- **Cross-view MVS consistency** — a dense depth accepted only when multiple views agree is more reliable; fusion consistency counts serve as a dense-cloud confidence proxy.
- **Secondary:** local point density; formally, the **covariance from BA's information matrix** gives a principled per-parameter uncertainty ellipsoid (expensive, usually approximated).

**Our provenance model — five explicit classes for every point/surface:**

| Class | Meaning | Colour (proposed) | Usable for measurement? |
|---|---|---|---|
| `OBSERVED_HIGH_CONFIDENCE` | Directly measured, strong geometry (wide baseline, long track, low reprojection error) | **Green** | Yes (default) |
| `OBSERVED_LOW_CONFIDENCE` | Measured but weak geometry (short baseline / few observations / high residual) | **Amber** | With warning |
| `AI_ASSISTED` | Learned depth/completion filled or improved this region | **Purple** | No, unless user opts in |
| `DYNAMIC_EXCLUDED` | Moving object (vehicle/person/animal) removed from the static map | — (masked) | No |
| `UNOBSERVED` | Never seen by any frame | **Red / transparent (holes)** | No |

**Measurements default to observed geometry only.** AI-assisted surfaces are visually distinct and excluded from measurement unless explicitly enabled, with a warning when a measurement crosses low-confidence or inferred regions. *This single design choice — visible, honest confidence — is the thing judges will remember, and the thing no commercial competitor surfaces (§5).*

### 4.8 The learned/AI toolbox (and why the metric backbone stays classical)

- **Monocular depth estimation** (MiDaS, DPT, Depth Anything v2, Metric3D, ZoeDepth): predicts depth from a single image via learned priors. Most output *relative* depth (inheriting scale ambiguity, now per-image); "metric" variants exist but generalize imperfectly across cameras. Useful to **densify/fill textureless regions/initialize MVS** — but a prediction, not a triangulated measurement.
- **Learned matching** (SuperPoint + SuperGlue/LightGlue; detector-free LoFTR/RoMa): replace SIFT + nearest-neighbour, dramatically improving matches in wide-baseline, low-texture, repetitive scenes. They upgrade the SfM *front end* without changing the underlying geometry/BA — a low-risk, high-value improvement for us.
- **Feed-forward 3D** (DUSt3R → MASt3R → MASt3R-SLAM, VGGT, Fast3R): regress aligned 3D *pointmaps* directly from images in one forward pass, no calibration needed. Excellent for speed and uncooperative imagery; outputs are learned (scale typically relative), so for high-accuracy metric work they **initialize** a classical BA rather than replace it.
- **NeRF** and **3D Gaussian Splatting (3DGS)**: scene representations optimized to make *rendered images look like the input photos* (a **photometric** objective). Superb for **novel-view synthesis/visualization**; but their geometry is a soft, appearance-optimized field/fuzzy primitives, not measured surface points — extracting accurate metric geometry is an indirect, active research problem, and they inherit scale ambiguity from their input poses.

**The measurement-vs-synthesis principle (state this to judges):** classical SfM→BA→MVS optimizes *"is each 3D point consistent with where it was observed?"* — a **geometric** objective with per-point error you can quantify and report. NeRF/3DGS optimize appearance. Therefore **our metric backbone stays classical and georeferenced**, and neural methods serve **visualization** and **clearly-labelled** densification/completion. This is the accountable architecture — and "accountable" is what NTRO-adjacent judges want.

---

## 5. The Competitive Landscape and Our Wedge

### 5.1 What already exists

> *Verification note (corrected 2026-08-27):* an earlier draft of this table called Pix4D and OpenDroneMap "photo-only." **That was wrong** — verified against primary sources. Pix4Dmapper's official docs state *"Video files can also be imported and used for processing"* and its feature list advertises *"Video (mp4 or avi) — automatically extracts still frames"*; OpenDroneMap has a documented video-to-frames workflow. **Most of these tools can ingest video by extracting frames.** So "we take video" is *not* our differentiator — the column below reflects that honestly, and the real wedge is restated in §5.2. Prices still come partly from vendor pages — reconfirm before quoting.

| Tool | What it does | License / cost | Video input? | Georeferencing / GCP |
|---|---|---|---|---|
| **Pix4D (Mapper)** | Survey-grade mapping, orthomosaics, volumetrics | Commercial (~$3,490 or subscription) | **Yes** — auto-extracts frames (mp4/avi); still optimized for planned grid capture | GCP + RTK/PPK; sub-cm with GCP |
| **Agisoft Metashape** | Research-grade dense reconstruction, meshes, Python API | Commercial (Pro ~$3,499) | Yes — video/frame import; grid-oriented | GCP + RTK/PPK (Pro) |
| **DroneDeploy** | Enterprise cloud mapping, construction monitoring | Commercial (~$329/mo+) | Photo auto-capture workflow | GCP; 1–2 cm with GCP |
| **RealityCapture** | Large-scale reconstruction; merges photos + LiDAR | Commercial pay-per-input | Frames (typically extracted externally) | GCP-capable; sub-cm |
| **OpenDroneMap / WebODM** | Open-source pipeline: cloud, mesh, orthomosaic | **Free & open-source** | **Yes** — documented video-to-frames workflow | GCP; 3–10 cm no GCP, 1–3 cm with |
| **SkyeBrowse** | Cloud **video→3D**, LAZ, orthomosaics; no grid planning | Commercial (free tier; ~$99–199/model) | **Native, single-pass video** (.MP4/.MOV) | Auto-georef from telemetry; **no GCP workflow** |
| **3DF Zephyr** | Photogrammetry suite | Commercial (tiered/free-limited) | Supports video import | GCP-capable |

### 5.2 The gap — precisely stated (the corrected, harder-to-challenge version)

The honest wedge is **not** "we accept video and they don't" — several tools ingest video by extracting frames. It is a *combination* no existing product delivers at once:

1. **Built for single-pass, telemetry-aware capture — not a planned grid.** Every survey tool above (even when it accepts a video file) is engineered around a *planned overlapping-grid mission* and photo-capture logic. Feeding a single linear flyover's frames into a grid-oriented pipeline is not what they're designed to do well. Drishti3D treats the single continuous pass + its synchronized telemetry as the *primary* input.
2. **No mainstream tool surfaces observation provenance.** **None** of them expose **per-point / per-region confidence or provenance** (measured vs weak vs inferred vs unobserved) as a first-class output, or enforce **measurement safety** (refusing to measure inferred geometry by default). For intelligence and disaster decisions — where knowing *which parts to trust* is the whole point — this is a genuine, unserved need.
3. **No open, offline, single-pass, evidence-backed pipeline exists.** The free option (ODM/WebODM) is grid-oriented and provenance-blind; the strongest single-pass video tool (SkyeBrowse) is closed cloud software with no GCP rigor and no "measured vs guessed" distinction. None is designed to run **air-gapped** with **independent-checkpoint accuracy evidence** and **coverage feedback**.

### 5.3 Our positioning (and the answer to "isn't this just Pix4D/ODM?")

> **Drishti3D's wedge = single-pass + telemetry-aware + explicit observation provenance + measurement safety + independent accuracy evidence + offline reproducibility + coverage feedback.** Existing tools are credible baselines — some even accept video — but none combine these.

When a judge asks "why not just use Pix4D or OpenDroneMap?", the crisp, *accurate* answer is:

- *"Those are excellent baselines, and yes, some of them can even ingest a video by extracting frames. But they're built for planned grid missions, and — critically — none of them tell you which parts of the model were actually measured versus weakly triangulated versus AI-guessed versus never seen. We do, and we refuse to measure inferred geometry by default."*
- *"The strongest single-pass video tool, SkyeBrowse, is closed cloud software with no ground-control rigor and no provenance layer — disqualifying for an intelligence or disaster product."*
- *"And none of them run air-gapped with independent-checkpoint accuracy evidence and coverage feedback. We're built for exactly that."*

That is a positioning no other SIH team — and no shipping product — can claim in one breath. It is defensible because it is *true* (and, unlike the earlier "video is rare" framing, it survives an expert who knows Pix4D accepts video). It maps directly onto NTRO's operational reality (§3).

---

## 6. The Solution — Drishti3D System Architecture

### 6.1 The shape of the system

Drishti3D is a **modular monorepo** with three logical tiers plus supporting assets:

```
/
  frontend/          React + TypeScript + Vite operational UI (3D viewer, map, measurement, reports)
  backend/           FastAPI + Pydantic + SQLAlchemy; project/job/state management, WebSocket/SSE progress
  reconstruction/    The CV pipeline: ingestion → quality → keyframes → masking → SfM/SLAM → georef → fusion → mesh → QA
  sample_data/       Small licensed/synthetic fixtures (image seq + telemetry + expected scale)
  tests/             Unit + one end-to-end integration test (no large weight downloads)
  docs/              README, architecture, telemetry schema, capability matrix, demo script, licences
  docker-compose.yml Local + optional NVIDIA GPU worker
  .env.example
```

- **Frontend** is a thin, honest operator console — it *displays* what the backend computed and never fabricates geometry or accuracy.
- **Backend** owns projects, jobs, state, files, and streams stage-by-stage progress to the UI.
- **Reconstruction** is a set of **independently testable modules** (each pipeline stage), so any stage can be unit-tested, restarted, and cached.

### 6.2 The end-to-end data flow

```text
Drone video + telemetry (GPS/IMU/camera params)
          │
          ▼
[1] Ingestion & validation ── ffprobe/ExifTool metadata, checksums, immutable originals
          │
          ▼
[2] Synchronization ── frame timestamps ↔ interpolated telemetry (in local ENU)
          │
          ▼
[3] Frame-quality analysis ── blur (Laplacian), exposure, motion, duplicates
          │
          ▼
[4] Keyframe selection ── overlap-preserving, blur/exposure/flow/GPS-aware
          │
          ▼
[5] Dynamic-object masking ── semantic (vehicles/people/animals) + optical-flow residual
          │
          ▼
[6/7] Hybrid reconstruction
        ├── FAST PATH:   AI/SLAM preview (VGGT / MASt3R-SLAM / DROID-SLAM adapter, GPU)
        └── VERIFIED PATH: COLMAP SfM (sequential match + GPS priors) → optional dense MVS
          │
          ▼
[8] Georegistration & scale ── WGS84→ECEF→ENU; robust Sim(3) (RANSAC) to GPS camera centres
          │
          ▼
[9] Fusion & cleanup ── merge in metric frame; voxel downsample; outlier removal; normals; colour
          │
          ▼
[10] Confidence / provenance labelling ── the five classes (§4.7) per point
          │
          ▼
[11] Optional mesh ── Poisson / ball-pivoting (Open3D), provenance-preserving
          │
          ▼
[12] Quality report + exports ── PLY/LAS/GLB/GeoJSON/CSV + JSON/HTML report
          │
          ▼
Web viewer · map + trajectory · measurement tools · layer toggles · confidence legend
```

### 6.3 The dual-path principle (the architectural crux)

We deliberately run **two complementary reconstruction paths** and keep them separate:

- **Verified path (classical, accountable):** COLMAP/PyCOLMAP SfM with sequential matching and GPS pose priors → optional dense MVS. Slower, but every point has a *geometric* pedigree (reprojection error, track length, triangulation angle) we can quantify and defend. **This is the metric backbone and the source of all measurements.**
- **Fast/AI path (responsive, exploratory):** a learned front-end (VGGT / MASt3R-SLAM / DROID-SLAM behind a common adapter) produces a **quick preview** and helps difficult regions. Its output is *fused only after alignment with verified geometry* and is labelled `AI_ASSISTED`.

Why two paths win SIH: the fast path gives a **live, satisfying on-stage preview within the demo window**; the verified path gives the **defensible accuracy numbers** judges probe for. Crucially, **the system must still run if the AI models are absent** — the classical path alone produces a real reconstruction. Missing GPU/models cause *warnings, not crashes*. (This graceful degradation is explicitly in the acceptance criteria and is a common failure point for other teams.)

> **The rule that protects us on stage:** *at least one path must generate an actual reconstruction from the uploaded frames.* No hardcoded 3D model, ever. A faked demo that an expert catches is an instant loss; a modest-but-real reconstruction with honest confidence colouring wins.

---

## 7. The Reconstruction Pipeline, Stage by Stage

Each stage is a separately testable module with cached, restartable outputs. For each, the *why* matters as much as the *what*.

**Stage 1 — Ingestion & validation.** Accept MP4/MOV video and telemetry as CSV/JSON/SRT (with a documented generic CSV schema). Required telemetry: `timestamp, latitude, longitude, altitude`. Optional: `roll, pitch, yaw, velocity, barometric_altitude, focal_length, fx, fy, cx, cy, distortion, RTK status, GPS accuracy`. Use **ffprobe** for resolution/FPS/duration/codec and **ExifTool** for embedded GPS/timestamps/camera model. Validate timestamp monotonicity, coordinate ranges, and missing fields. Store **immutable originals + SHA-256 checksums** — you must be able to prove the demo used the file you claim.
*Why:* garbage-in dominates final accuracy; catching a broken telemetry file here saves a mysterious failure at stage 8.

**Stage 2 — Synchronization.** Map each extracted frame's timestamp to interpolated telemetry. Interpolate **positions linearly through a local ENU frame** (never in raw lat/lon — §8) and **orientation with angle-aware interpolation** (slerp-style, so 359°→1° doesn't average to 180°). Record a sync residual/confidence and allow a configurable video-to-telemetry time offset.
*Why:* a constant time offset between video and GPS is common and, uncorrected, injects a systematic position error into every camera prior.

**Stage 3 — Frame-quality analysis.** Per frame compute: **Laplacian-variance blur score** (`cv2.Laplacian(...).var()`), brightness + clipped-dark/clipped-bright percentages, inter-frame motion, duplicate-frame score, and sudden-exposure-change flags. Save metrics; mark rejected frames with reasons; thresholds configurable.
*Why:* motion-blurred/over-exposed frames produce bad features → bad poses → contaminated geometry. Rejecting them early is cheaper and cleaner than fixing downstream.

**Stage 4 — Keyframe selection.** Combine temporal spacing, optical-flow magnitude, feature displacement, blur, exposure, GPS displacement, and rotation change to pick a well-spaced keyframe set that **preserves overlap while dropping redundancy**. Offer **fast / balanced / quality** presets and emit a keyframe timeline.
*Why:* processing every 30-fps frame is wasteful and can *hurt* (tiny baselines = weak parallax = low-confidence points, §4.7). Good keyframing is where speed and quality are both won.

**Stage 5 — Dynamic-object masking.** A **pluggable** mask generator: start with a lightweight torchvision segmentation model to mask **people, vehicles, animals**, supplemented by **optical-flow-inconsistency** detection where feasible; **dilate** masks to avoid boundary contamination. If the model is unavailable, continue with a **clear warning** (label affected geometry accordingly) rather than crashing.
*Why:* a moving car reconstructed into a "static" map is both wrong and embarrassing on stage. Masked pixels are excluded from features and tagged `DYNAMIC_EXCLUDED`.

**Stage 6 — Verified reconstruction (COLMAP).** SfM with **sequential matching + limited loop candidates** (video-appropriate), **shared intrinsics** across frames from the same video, supplied intrinsics used when available (else estimated with reported uncertainty). Exclude dynamic-masked pixels from features where feasible. Produce sparse points, registered poses, **reprojection errors, track lengths, per-point observation counts** (the raw material for confidence, §4.7). Attempt dense MVS when a CUDA GPU is present; **if dense is unavailable, keep the sparse output and issue a precise capability warning** (never silently drop to nothing).
*Why:* this is the accountable backbone. Its per-point statistics are what let us defend accuracy.

**Stage 7 — AI reconstruction adapter.** A clean Python interface — `is_available()`, `prepare_inputs()`, `reconstruct()`, `get_camera_poses()`, `get_depth_maps()`, `get_point_cloud()`, `get_uncertainty()` — with adapters/stubs for **MASt3R-SLAM** and **VGGT**. Detect installation; give exact setup instructions if missing; **never report that a model ran when it didn't**; do **not** auto-download large weights at startup. Fuse AI output only *after* alignment to verified geometry.
*Why:* honesty and offline-safety. The adapter pattern also means we can add/swap the fast-moving learned models without touching the rest of the pipeline.

**Stage 8 — Georegistration & scale.** Convert WGS84 telemetry → ECEF → **local ENU** (metric). Associate GPS positions with reconstructed **camera centres**. Estimate a **robust Sim(3) transform via RANSAC** (require ≥3 non-collinear correspondences; weight by GPS accuracy when known; reject outliers; compute residuals). Transform cameras *and* cloud into metric ENU, preserving the WGS84 origin so any point can be converted back to lat/lon. Distinguish **relative / GPS-derived / RTK-derived** scale in the output metadata. (Full geodesy detail in §8.)
*Why:* this is the stage that makes the model *metric and located*. It resolves the Sim(3) gauge freedom from §4.5 using the GPS the problem statement hands us.

**Stage 9 — Fusion & cleanup.** Merge points **only in the common metric frame** (never mix frames/units). **Voxel downsample**; **statistical + radius outlier removal**; **normal estimation**; colour points from source frames; retain confidence/provenance attributes through every operation. **Do not fill unseen areas as observed geometry** — optional inferred completion lives in a *separate* layer (§4.6). (Open3D handles these ops on CPU.)
*Why:* clean, normal-bearing, provenance-tagged clouds are what the viewer, measurements, and meshing all depend on.

**Stage 10 — Confidence / provenance labelling.** Assign each point one of the five classes (§4.7) from reprojection error, track length, observation count, triangulation angle, AI-uncertainty, GPS residual, and blur/exposure of source frames. This is a distinct, testable stage so the classification logic can be validated against known-good/known-bad fixtures.
*Why:* it is our signature feature; making it a first-class stage (not a side effect) keeps it correct and demonstrable.

**Stage 11 — Optional mesh.** Open3D **Poisson** (watertight) or **ball-pivoting** (surface-preserving) meshing; crop low-density artefacts; **preserve the point cloud if meshing fails**; retain provenance labels; export **GLB/OBJ** where feasible.
*Why:* meshes are visually compelling for the demo, but must never be the *only* output — point clouds are the reliable deliverable.

**Stage 12 — Quality report + exports.** Compute and expose: registered-keyframe count/percentage, median & percentile reprojection error, mean track length, GPS-alignment horizontal/vertical RMSE, point density, model bounding dimensions, **percentage of geometry in each confidence class**, per-stage processing time, and the **processing-time-to-video-duration ratio**. Export **PLY** (RGB + confidence), **LAS/LAZ**, **GLB/OBJ**, **GeoJSON** (trajectory + measurements), **CSV** (camera trajectory), **JSON** quality report, and a printable **HTML** report.
*Why:* the report *is* the evidence. It is what converts "trust us, it's accurate" into "here are the measured numbers."

### 7.1 Cross-cutting engineering rules (non-functional, but they win points)

- Preserve raw inputs; make stages **restartable** and **cache** intermediates.
- **Structured logging**; actionable errors; **never fabricate output**.
- **Deterministic seeds** where applicable (reproducible demo runs).
- Keep **units and coordinate frames explicit** in every data structure; **never mix geographic degrees with metric coordinates** (§8.5).
- Type hints + docstrings; prefer maintainable modules over premature abstraction.

### 7.2 Reproducibility spine — stage state machine + immutable artifact lineage

This is the engineering that converts "trust our demo" into "reproduce our result," and it is what an NTRO-adjacent jury actually respects. Two mechanisms:

**Stage state machine.** Every stage moves through explicit states: `PENDING → RUNNING → SUCCEEDED | SUCCEEDED_WITH_WARNINGS | FAILED | CANCELLED | SKIPPED`. A stage may **restart only when its input hashes and config hash are unchanged**; otherwise all downstream artifacts are invalidated. Progress is an **append-only event log** streamed over SSE — never a decorative percentage.

**Immutable, manifest-driven runtime layout.** Never scatter outputs across ad-hoc folders. Use:

```text
data/projects/{project_uuid}/
├── inputs/           original_video.ext · original_telemetry.ext · manifest.json
├── jobs/{job_uuid}/  config.snapshot.json · logs/events.jsonl · frames/ · masks/
│                     sparse/ · dense/ · aligned/ · mesh/ · exports/ · stage-manifest.json
└── current.json      # pointer to the accepted job's artifacts
```

Every artifact record carries: **SHA-256, byte size, MIME/type, producing stage, parent artifacts, software+model versions, parameters, coordinate frame, units, creation time.** That lineage chain makes stage caching *safe* (you can prove an input is unchanged) and lets another engineer take the original inputs + recorded config and reproduce the accepted artifacts exactly. Definition of done for Drishti3D is not "a 3D model appears" — it is "a stranger reproduces the numbers and understands every transform."

---

## 8. Coordinate Systems and Georegistration — the Metric Backbone

Getting geodesy right is unglamorous but it is where sloppy teams silently lose accuracy. This section is the reference.

### 8.1 WGS84 — the GPS datum (angular, not metric)

GPS reports positions as **latitude (φ), longitude (λ) in degrees** plus a height, on the WGS84 ellipsoid (semi-major axis *a* = 6,378,137.0 m, flattening *f* = 1/298.257223563). It is **angular**: a degree of latitude is ~111 km everywhere, but a degree of longitude is **111 km·cos φ** — ~111 km at the equator, shrinking to 0 at the poles. So lat and lon have *different, position-dependent* ground scales. You **cannot** treat (lat, lon) as planar (x, y): Euclidean operations (distances, dot/cross products, least-squares, SVD) assume an isotropic metric space, which degrees are not.

### 8.2 ECEF — the global metric bridge

**Earth-Centered, Earth-Fixed** is a right-handed Cartesian frame **in metres**, rotating with Earth: origin at the centre of mass, +Z through the North Pole, +X through the equator/prime-meridian intersection, +Y completing the set. It is fully metric and global, so it is the natural intermediate: **WGS84 → ECEF → local ENU**. Downside: coordinates are millions of metres, so using ECEF *directly* in reconstruction wrecks floating-point conditioning — hence the shift to a local frame.

### 8.3 Local ENU — the working frame for reconstruction

Pick an anchor (first GPS fix or scene centroid) and build a plane tangent to the ellipsoid there with axes **East, North, Up**. Convert by translating to the anchor in ECEF and applying a fixed rotation (a function of the anchor's φ, λ). We do **all** reconstruction geometry here because: (a) axes are in **metres**, isotropic, roughly gravity-aligned; (b) values are small and near the origin → good numerical conditioning for BA/ICP/Sim(3); (c) rigid transforms, normals, and volumes behave correctly. Over a single survey (hundreds of m to a few km) the flat-plane error is negligible; it only matters over tens of km.

### 8.4 UTM (for GIS delivery)

**Universal Transverse Mercator** splits the globe into **60 zones of 6° longitude**, each a transverse-Mercator projection giving **easting/northing in metres**, with a 0.9996 central-meridian scale factor. Convenient and GIS-standard, but **breaks across zone boundaries**. Use it as an **export/mapping** frame, not the local geometry frame; for a single site ENU is cleaner.

### 8.5 The cardinal rule — never mix degrees and metres

If X/Y are degrees and Z is metres (an extremely common bug), then 1 unit of "X" ≈ 111,000 m while 1 unit of "Z" = 1 m — every nearest-neighbour search, normal estimate, RANSAC threshold, or scale computation becomes meaningless. Doing geometry directly in lat/lon also adds **anisotropy** (longitude compressed by cos φ) and **non-linearity** (a straight ground line isn't straight in lat/lon). **Rule: project to a metric frame (ENU/UTM) first, do all geometry there, convert back only for storage/display.** `pyproj` performs every conversion.

### 8.6 Height is subtle — ellipsoidal vs orthometric

- **Ellipsoidal height (h):** above the reference ellipsoid — **what raw GNSS outputs.**
- **Orthometric height (H):** above the **geoid** (≈ mean sea level) — what maps and surveyors mean.
- Related by **h = H + N**, where **N is the geoid undulation** (globally roughly −107 m to +85 m).

A drone's reported "altitude" might be ellipsoidal, orthometric, height-above-takeoff, or barometric — differing by *tens of metres*. Comparing a reconstruction's Z to ground truth requires knowing which datum each uses and applying the right geoid model (e.g., EGM2008). **Mismatched height datums are a frequent source of large systematic vertical error** — call this out proactively; it signals real competence.

### 8.7 The alignment math — robust Sim(3)

A monocular reconstruction is fixed only up to a **7-DoF similarity transform** (3 rotation + 3 translation + 1 scale — the gauge freedom of §4.5). Georegistration removes it by aligning to a metric reference — usually the **GPS-measured camera centres**, matched to the **SfM-estimated camera centres**.

Map source **x** (reconstruction) to target **y** (world/ENU): **y = s·R·x + t**, with R ∈ SO(3), t ∈ ℝ³, s > 0 — this is **Sim(3)**.

- **Closed-form solution:** the **Umeyama (1991)** algorithm — SVD of the cross-covariance (with a sign correction guaranteeing a proper rotation, det = +1, no reflection), then scale from the variance ratio, then translation. It is the standard for aligning both point sets and SLAM trajectories.
- **Why ≥3 non-collinear points:** translation needs 1 point, scale needs ≥2 (a baseline), and fully constraining 3D rotation needs **≥3 non-collinear** points. If all correspondences are collinear, rotation about that line is unconstrained (degenerate). In practice we use many more and solve least-squares.
- **Why RANSAC:** GPS camera centres contain outliers (multipath, single-epoch fixes, timestamp/sync errors). Plain Umeyama is not robust — a few gross outliers bias R, t, s. RANSAC fits Sim(3) on random minimal samples, scores by inlier count within a metric threshold, keeps the best consensus set, then refits Umeyama on all inliers.
- **Residual analysis:** after alignment, compute per-correspondence residuals and summarize with **RMSE (overall, and horizontal vs vertical separately)**. Inspect *structure*, not just magnitude: a spatial tilt ⇒ datum/scale mismatch; a **dome/bowl** in Z ⇒ classic self-calibration/lens-distortion or GPS-altitude bias; a few large isolated residuals ⇒ leftover outliers. Good alignment ⇒ small, zero-mean, spatially unstructured residuals.

### 8.8 GCPs and RTK/PPK — where accuracy really comes from

- **Ground Control Points (GCPs):** physical, precisely surveyed, visually identifiable markers with known world coordinates, added as constraints. **Checkpoints** are the same but *withheld* from the solution and used only to *measure* accuracy (this is how you produce honest RMSE numbers).
- **RTK (Real-Time Kinematic)** and **PPK (Post-Processed Kinematic):** both **carrier-phase differential GNSS** using a base station + rover. RTK corrects live over a radio link; PPK logs raw GNSS and corrects after landing (same accuracy class, robust to link dropouts).
- **Why RTK/PPK is centimetre vs GPS metre:** standard GNSS uses **code-based pseudorange** (metre-scale noise + uncorrected atmosphere/orbit/clock) → **~1–5 m**. RTK/PPK resolves the **integer carrier-phase ambiguity** using the ~19–24 cm carrier wavelength, differenced against a base that cancels common-mode errors → **~1–3 cm**.

**Design takeaway:** our absolute accuracy is *bounded by the telemetry we're given.* With plain GPS we honestly report metre-level absolute accuracy; with RTK/PPK or GCPs we can claim decimetre-or-better. We never claim centimetre accuracy without measured ground-truth evidence (§11.4). Relative measurements (a wall length *within* the model) are much better than absolute, because they depend only on internal scale consistency, not on the GNSS datum.

---

## 9. The Technology Stack — Every Tool, Why, License, GPU

All facts below were verified against current (2025–2026) sources. **Licences matter for SIH** (and for any real deployment) — a jury may ask, and an air-gapped government context cares.

### 9.1 Frontend

| Tool | Role | License | Notes |
|---|---|---|---|
| **React + TypeScript + Vite** | Operator UI shell | MIT | Fast dev, type-safe |
| **CesiumJS** | Georeferenced 3D globe/viewer | Apache-2.0 | Native WGS84 globe + terrain; streams huge datasets via **3D Tiles**; consumes glTF/GLB. Use when the model must sit at real coordinates on a globe. |
| **Three.js** | Fallback 3D model viewer | MIT | General WebGL engine; simple, flexible; **no geospatial concept** (you manage coordinates). Use if Cesium integration blocks progress. |
| **MapLibre GL JS** | 2D map + flight-path overlay | BSD-3-Clause | Open-source Mapbox-GL fork for 2D/2.5D vector maps. |

### 9.2 Backend

| Tool | Role | License |
|---|---|---|
| **Python 3.11** | Backend + reconstruction language | PSF |
| **FastAPI + Pydantic** | REST API + validation | MIT / MIT |
| **SQLAlchemy** | ORM | MIT |
| **SQLite → PostgreSQL/PostGIS** | DB (prototype → production) | Public-domain / PostgreSQL license |
| **WebSocket / SSE** | Live stage progress to UI | — |
| **Local worker → Celery + Redis** | Background jobs (start simple, scale later) | BSD / BSD |

### 9.3 Reconstruction & media

| Tool | Role | CPU/GPU | License |
|---|---|---|---|
| **FFmpeg / ffprobe** | Frame extraction; video metadata | CPU (opt. NVENC/NVDEC) | LGPL-2.1+/GPL |
| **ExifTool** | GPS/timestamp/camera metadata from media | CPU | Perl Artistic/GPL |
| **OpenCV** | Frame processing, **Laplacian blur**, optical flow | CPU (opt. `cv2.cuda`) | Apache-2.0 |
| **COLMAP / PyCOLMAP** | Verified SfM (+ dense MVS) | Sparse: CPU ok (GPU-accelerated features); **Dense MVS: CUDA effectively required** | **BSD-3-Clause** |
| **Open3D** | Cloud cleanup, downsample, normals, meshing | CPU (opt. CUDA) | MIT |
| **pyproj / PROJ** | WGS84 ↔ ECEF ↔ ENU ↔ UTM | CPU | MIT / X11-style |
| **VGGT (adapter)** | Fast feed-forward 3D | **NVIDIA GPU** | Repo commercial-friendly; **only the `VGGT-1B-Commercial` checkpoint is commercial-safe** |
| **MASt3R-SLAM (adapter)** | Real-time dense monocular SLAM | **NVIDIA GPU** | **CC BY-NC-SA 4.0 (non-commercial)** ⚠ |
| **DROID-SLAM (adapter, optional)** | Deep dense-BA SLAM | **NVIDIA GPU (≥11 GB)** | **BSD-3-Clause** |
| **Torchvision seg. model** | Dynamic-object masking | CPU ok / GPU faster | BSD |

### 9.4 The licensing analysis (say this before a judge asks)

- **Commercially / deployment safe (permissive):** COLMAP, DROID-SLAM (BSD); Open3D, pyproj, OpenCV, React, Three.js (MIT/Apache/BSD); CesiumJS (Apache-2.0). **Our metric backbone is entirely permissive** — this is deliberate.
- **Non-commercial (⚠ research-only):** **MASt3R-SLAM** and the underlying **DUSt3R/MASt3R** are **CC BY-NC-SA 4.0**. Fine for an SIH prototype and research demonstration; a **blocker for a shipped commercial product.** Keep them behind the adapter so they are optional and swappable.
- **Checkpoint nuance:** **VGGT** code is commercial-friendly but only the **`VGGT-1B-Commercial`** checkpoint is licensed for commercial use — the original checkpoint is research-only. Verify per checkpoint.
- **Consequence for the roadmap:** the **default, always-available path uses only permissive software (COLMAP + Open3D + pyproj)**; the non-commercial learned models are optional accelerators. This means Drishti3D is legally deployable air-gapped even if every non-commercial model is removed.

---

## 10. Reconstruction Engines Compared

The heart of the technical choice: which engine(s) drive reconstruction. All learned engines below need an NVIDIA GPU and **none georeferences natively** — COLMAP + pyproj remain the path to metric, GPS-aligned output.

| Engine | What it is | Output | GPU | License | Best role for us |
|---|---|---|---|---|---|
| **COLMAP / PyCOLMAP** | Classical SfM + MVS; the research reference engine | Poses + sparse cloud; dense cloud/mesh via MVS | Sparse: CPU ok; **dense: CUDA** | **BSD-3** | **Verified metric backbone**; sequential matching + GPS priors + `model_aligner` georegistration |
| **VGGT** | ~1B-param feed-forward transformer (Meta+Oxford), **CVPR 2025 Best Paper** | Intrinsics+extrinsics, depth, point maps, tracks — **one forward pass (<1 s network time)** | **NVIDIA** | Commercial checkpoint available | **Fast preview / initializer**; exports **COLMAP format** (`demo_colmap.py`) → refine + georegister in COLMAP |
| **MASt3R-SLAM** | Real-time dense monocular SLAM on MASt3R priors (Imperial), **CVPR 2025** | Globally-consistent poses + dense pointmap cloud, with loop closure | **NVIDIA** (**~15 FPS on RTX 4090**) | **CC BY-NC-SA (NC)** ⚠ | Optional real-time live-capture front-end; NC-licensed |
| **DROID-SLAM** | Deep SLAM with differentiable dense bundle adjustment (Princeton), NeurIPS 2021 | Poses + per-pixel dense depth | **NVIDIA (≥11 GB)** | **BSD-3** | Optional permissive-licensed dense front-end |
| **DUSt3R / MASt3R** | NAVER "geometric foundation models"; pointmaps from uncalibrated pairs | Pointmaps → pose/depth/matches | **NVIDIA** | **CC BY-NC-SA (NC)** ⚠ | Underlying priors (consumed via MASt3R-SLAM / MASt3R-SfM) |

**Confirmed facts (from our verification pass):** VGGT won the CVPR 2025 Best Paper Award (announced 13 Jun 2025), exports COLMAP format, sub-second network forward pass. MASt3R-SLAM is CVPR 2025, ~15 FPS on an RTX 4090, CC BY-NC-SA. DROID-SLAM is BSD-3, needs ≥11 GB GPU for its demos. **Could not confirm:** a canonical FPS for VGGT on drone video specifically (only "<1 s" forward pass); MASt3R-SLAM FPS is GPU-class-specific.

### 10.1 Our recommended engine strategy

1. **Ship the classical path first and always.** COLMAP (sequential matching + shared intrinsics + GPS priors) → `model_aligner` georegistration → optional dense MVS → Open3D cleanup. Permissive, metric, defensible. **This alone satisfies the acceptance criteria.**
2. **Add VGGT as the fast preview + initializer.** It's permissive-checkpoint-available, produces COLMAP-format output we can georegister, and gives the crowd-pleasing near-instant on-stage 3D. Best risk/reward learned engine for us.
3. **Treat MASt3R-SLAM / DROID-SLAM as optional real-time front-ends** behind the adapter, enabled only when a capable GPU is present — with MASt3R-SLAM's non-commercial licence clearly flagged.

### 10.2 CPU / GPU capability matrix (what runs where)

| Capability | CPU-only laptop | + NVIDIA GPU |
|---|---|---|
| Ingestion, ffprobe/ExifTool, frame extraction | ✅ | ✅ |
| Frame quality, keyframe selection, optical flow | ✅ | ✅ (faster) |
| Dynamic masking (torchvision) | ✅ (slow) | ✅ |
| COLMAP **sparse** SfM + poses | ✅ | ✅ (faster features) |
| COLMAP **dense** MVS | ❌ (impractical) | ✅ |
| Georegistration (Sim(3)), fusion, cleanup, mesh (Open3D) | ✅ | ✅ |
| Confidence labelling, measurements, exports, report | ✅ | ✅ |
| VGGT / MASt3R-SLAM / DROID-SLAM | ❌ | ✅ |

**Read this carefully:** a **full, honest, metric reconstruction runs on a CPU-only laptop** via sparse COLMAP + georegistration + Open3D (you lose only dense MVS and the learned engines). That means we have a **guaranteed demo even if the GPU box fails on the day** — a critical resilience most teams lack.

---

## 11. Evaluation, Metrics, and Defensible Accuracy Claims

The problem statement is explicitly evaluation-driven. Knowing these metrics — and stating honest targets — is how we convert a demo into a *credible* demo.

### 11.1 The metrics, defined

- **Horizontal / vertical RMSE** — reconstruction vs **independent surveyed checkpoints** (points *not* used in processing). Horizontal = √(mean(Δx²+Δy²)); Vertical = √(mean(Δz²)). Report separately: **vertical error is typically 2–3× worse** than horizontal in nadir photogrammetry. Also report the **mean (bias)** separately — a large mean signals a systematic datum/scale error, not just noise.
- **Absolute Trajectory Error (ATE)** — align the estimated camera trajectory to ground truth with one global Sim(3), then RMSE of the per-pose translational differences. Measures **global consistency** of the whole path.
- **Relative Pose Error (RPE)** — error of the *relative* motion over a fixed interval (Δtime or Δdistance). Measures **local drift** (drift per metre/second); needs no global alignment. (KITTI's odometry metric is essentially segment-averaged RPE.)
- **Cloud-to-cloud (C2C)** — nearest-point distance between two clouds; fast but overestimates where the reference is sparse.
- **Point-to-mesh (C2M)** — distance from points to the nearest reference *surface*; more accurate when a reference mesh exists.
- **Chamfer distance** — symmetric mean nearest-neighbour distance between two point sets (definition varies by paper — *state which you use*).
- **Completeness / Accuracy / F-score @ tolerance d** — Accuracy/Precision@d = fraction of *reconstructed* points within *d* of ground truth (penalizes spurious geometry); Completeness/Recall@d = fraction of *ground-truth* points within *d* of the reconstruction (penalizes missing geometry); **F-score@d** = their harmonic mean — the standard single-number MVS score (the **Tanks and Temples** protocol). Always report the tolerance *d*.
- **Reprojection error (px)** — the BA cost; measures *internal self-consistency*, **not** world accuracy (a model can have 0.3 px reprojection error yet be badly georeferenced). Good ≈ **sub-pixel (0.3–1.0 px)** for well-textured aerial blocks.

### 11.2 Mapping metrics to the problem statement's desired outputs

| Desired output | Criterion | Our metric |
|---|---|---|
| Georeferenced cloud/mesh | Geographic accuracy | Horizontal/vertical RMSE vs RTK/GCP checkpoints |
| Metrically scaled model | Dimensional accuracy | Absolute & % error on known distances/heights/areas |
| Accurate camera trajectory | Pose accuracy | ATE + RPE |
| Complete visible reconstruction | Completeness | % of reference surface reconstructed within tolerance |
| Geometric fidelity | Surface accuracy | Point-to-mesh RMSE / Chamfer / C2C |
| Robust video processing | Frame usability | % frames correctly accepted/rejected |
| Dynamic-object resistance | Static-map cleanliness | Dynamic points remaining in final model |
| Confidence-aware output | Confidence calibration | Error rate grouped by predicted confidence band |
| Near-real-time | Efficiency | Processing time ÷ video duration |
| Portable output | Interoperability | Successful PLY/LAS/GLB/OBJ/GeoJSON/CSV exports |

### 11.3 Benchmark datasets (verified) — for validation without a drone

| Dataset | Domain | Ground truth |
|---|---|---|
| **EuRoC MAV** | Indoor micro-aerial-vehicle, stereo + IMU (VIO/SLAM) | 6-DoF pose from Vicon + Leica laser tracker; 3D laser scan of environment |
| **TartanAir** | Large synthetic (AirSim) drone/robot, hard conditions | Dense perfect GT: depth, pose, semantics, optical flow |
| **KITTI** | Automotive outdoor, stereo + LiDAR odometry | Velodyne LiDAR + RTK-GPS/INS pose |
| **ETH3D** | Multi-view stereo (indoor+outdoor) + SLAM track | Survey-grade laser-scanner geometry; F-score server |
| **Tanks and Temples** | MVS benchmark, realistic scenes, **video input** | Laser-scanner GT; precision/recall/F-score protocol |

Also verified UAV-adjacent: **UZH-FPV** (drone-racing VIO, Leica GT) and **Blackbird** (MIT indoor quadrotor, motion-capture GT). **Gap to flag:** there is **no single canonical outdoor georeferenced-UAV-photogrammetry benchmark** analogous to EuRoC — outdoor accuracy is usually reported per-study against local surveyed checkpoints. (Candidate newer sets like "UseGeo" and "Mid-Air" were *not* verified in our pass — check the source before citing.)

**Practical plan:** validate SLAM/pose on **EuRoC/TartanAir** (real numbers, no drone needed), validate MVS surface accuracy on **ETH3D/Tanks-and-Temples**, and validate *our* georeferencing on **one team-captured dataset** with a few surveyed checkpoints. That combination gives defensible numbers for the report.

### 11.4 Defensible accuracy targets (say these, not "centimetre accurate")

- **With RTK/PPK:** target **decimetre or better** georegistration (subject to camera, altitude, flight geometry). Literature reaches 1–3 cm horizontal / 2–5 cm vertical under good conditions.
- **With ordinary GPS:** **explicitly report GPS-limited absolute accuracy — metre-level (~1–5 m).** Do not hide this; owning it is credibility.
- **Relative dimensional error** on well-observed surfaces: target **below 3–5%**, often much better. *Caveat: there is no universal fixed "%" — it depends on object size and GSD. Never cite a bare percentage without stating the object size and GSD it came from.*
- **Speed:** fast preview close to video duration; refined reconstruction may take several × video duration.
- **The GSD rule of thumb:** achievable positional accuracy ≈ **1–3 × the Ground Sampling Distance** when well-controlled (RTK/good GCPs). E.g., at 3 cm GSD expect ~3–9 cm; vertical is the looser bound.
- **The unbreakable rule:** **never claim centimetre accuracy without measured ground-truth evidence.** A confidence-calibrated "here is the error grouped by our own confidence bands" is worth more to a jury than an unbacked "it's super accurate."

### 11.5 Standards vocabulary and the ablation matrix (proving the AI isn't decoration)

**Speak the standards language, but do not claim certification.** The current **ASPRS Positional Accuracy Standards for Digital Geospatial Data (Edition 2, Version 2, 2024)** adds dedicated photogrammetry, UAS, and oblique-imagery guidance and emphasises **independent checkpoints**, raising the minimum to **30 checkpoints** for a *formal* product-accuracy assessment. A hackathon prototype will have fewer — so align your report's *terminology* with ASPRS (independent checkpoints, horizontal/vertical RMSE at stated confidence) while explicitly calling the result an **experiment, not a standards-compliant certification.** Using the right vocabulary honestly signals real geospatial literacy.

**The ablation matrix — this is what defeats "your AI is just a label."** Run each comparison on *identical* keyframes and put the deltas in the report:

| Ablation | What it proves |
|---|---|
| Uniform every-Nth sampling **vs** adaptive keyframes | our selection improves registration/coverage |
| No masks **vs** semantic **vs** semantic + motion masks | dynamic rejection measurably cleans the static map |
| SfM only **vs** GPS pose priors **vs** post-hoc Sim(3) alignment | how each georeferencing choice moves accuracy |
| Estimated intrinsics **vs** calibrated intrinsics | calibration payoff |
| Classical init **vs** learned (VGGT) init | the learned path earns its place — or doesn't |
| Ordinary GPS **vs** RTK/GCP | the absolute-accuracy ceiling is telemetry-bound |

Each row is a slide-ready number that answers a hostile question *before* it is asked. It is the single most convincing evidence that our innovations create measurable value rather than decorative "AI-enabled" claims.

---

## 12. Frontend and User Experience

### 12.1 The API surface the UI consumes

```
POST   /api/projects                         create mission
GET    /api/projects                         list missions
GET    /api/projects/{id}                    mission detail
POST   /api/projects/{id}/video              upload video
POST   /api/projects/{id}/telemetry          upload telemetry
POST   /api/projects/{id}/process            start pipeline
GET    /api/jobs/{id}                         job status
GET    /api/jobs/{id}/events                  live progress (SSE/WebSocket)
GET    /api/projects/{id}/quality             quality/QA report
GET    /api/projects/{id}/trajectory          camera trajectory (GeoJSON)
GET    /api/projects/{id}/model               point cloud / mesh
POST   /api/projects/{id}/measurements        add measurement
GET    /api/projects/{id}/measurements        list measurements
DELETE /api/projects/{id}/measurements/{mid}  delete measurement
GET    /api/projects/{id}/exports             list exports
POST   /api/projects/{id}/exports             generate export
```

Explicit Pydantic schemas, validation, and useful errors throughout.

### 12.2 The five screens

- **A. Mission dashboard** — recent missions, processing status, quality summaries.
- **B. New-reconstruction wizard** — video + telemetry upload, telemetry preview, optional camera intrinsics, processing preset (fast/balanced/quality), input validation.
- **C. Processing monitor** — per-stage progress, frame/keyframe counts, warnings/failures, **honest elapsed + estimated** progress (never fake a progress bar).
- **D. Analysis workspace** — large 3D viewer, map + UAV trajectory, keyframe timeline strip, **layer toggles** (observed / uncertain / dynamic / inferred), **confidence legend**, point-size control, **measurement tools**, live coordinates, quality + export panels.
- **E. Report view** — input summary, reconstruction statistics, accuracy/confidence, performance, **known limitations**, JSON + printable HTML output.

### 12.3 Measurements

Point coordinate · 3D polyline distance · vertical height difference · polygon area on a best-fit plane · optional terrain profile. Each measurement records model ID, coordinates, units, **confidence**, whether inferred geometry was used, and a timestamp. **Warn when a measurement intersects low-confidence or AI-assisted geometry.** Measurements default to observed geometry only.

### 12.4 Design language

Professional, **dark, high-contrast operational** aesthetic; no decorative animation; laptop-display and keyboard-navigation friendly. The **confidence colour legend is a hero element** — green/amber/purple/red is the visual signature of the whole product (§4.7). **Do not** claim official NTRO endorsement or add fake classified markings — it is forbidden by the brief and reads as amateurish.

---

## 13. Security and Offline Operation

For a defense-adjacent, air-gap-capable product, security is a *feature*, not an afterthought — and it scores points.

- **Input safety:** validate MIME types and sizes; **sanitize filenames; prevent path traversal**; never execute uploaded data.
- **Offline by default:** **no network calls during processing**; bind to localhost by default; do not auto-download model weights at startup (document the manual, one-time weight install for air-gapped machines).
- **Data hygiene:** don't log precise coordinates unnecessarily; safe, scoped mission deletion; preserve immutable originals + checksums.
- **Air-gapped deployment documented** end-to-end: dependencies, COLMAP install, optional weights, GPU/CPU matrix, demo procedure, troubleshooting.

> **Security-awareness note:** the API and any dev server must be **bound locally** by default. If we ever expose it on a network, authentication/access control is required — an unauthenticated reconstruction service holding operational imagery would be a real vulnerability. Flag this explicitly in the README rather than shipping an open port silently.

---

## 14. Risks, Limits, and Honest Constraints

Naming your own limits *before* the jury does is a credibility multiplier. These are the real ones and how we mitigate each.

| Risk / limit | Why it exists | Mitigation |
|---|---|---|
| **Single-pass leaves unseen surfaces** | Physics of coverage (§4.6) | Label `UNOBSERVED`; show holes; never fake the far side; offer separate, clearly-marked inferred layer |
| **Monocular scale is unobservable** | Gauge freedom (§4.5) | Recover scale from GPS/RTK/IMU; report which scale source was used; refuse metric claims if none present |
| **No loop closure on one pass ⇒ drift** | Sequential estimation (§4.4) | GPS/IMU constraints in georegistration; report ATE/RPE honestly |
| **Absolute accuracy capped by GPS** | Code-phase GPS is metre-level (§8.8) | State "GPS-limited, metre-level" plainly; support RTK/PPK/GCP when available |
| **COLMAP fails on textureless/repetitive scenes** | Photo-consistency limits (§4.4) | Learned matching (SuperGlue/LightGlue); mark low-confidence; VGGT fallback |
| **Dense MVS + learned models need a GPU** | Compute (§10.2) | Full metric pipeline runs CPU-only (sparse + georef + Open3D); GPU is an accelerator, not a dependency |
| **MASt3R-SLAM / DUSt3R are non-commercial** | Licence (§9.4) | Keep behind adapter; default path is fully permissive (COLMAP/Open3D/pyproj) |
| **Demo hardware fails on the day** | Live-event reality | CPU-only fallback demo + pre-captured sample dataset ready; deterministic seeds so runs reproduce |
| **Height datum confusion** | Ellipsoidal vs orthometric (§8.6) | Detect/record datum; apply geoid model; report which height is used |
| **Dynamic objects pollute the map** | Moving cars/people (§7 stage 5) | Semantic + optical-flow masking; `DYNAMIC_EXCLUDED` class; report residual dynamic points |

**The honesty dividend:** every row above, presented as *"here is a real limit and here is exactly how we handle it,"* is worth more than a slick claim. It is precisely the posture an intelligence organization trusts, and it is what separates us from teams who assert accuracy they cannot back.

---

## 15. The Winning Strategy — Demo, Pitch, and Judge Q&A

This section is the playbook. The technology exists to serve it.

### 15.1 The narrative arc (90-second pitch skeleton)

1. **The reality:** *"NTRO doesn't get a planned survey mission. In a crisis or over a target, they get one drone flyover — a single pass. Every existing survey tool assumes the opposite."*
2. **The hard truth:** *"A single monocular pass has two unbreakable limits: you can't recover true scale from video alone, and you can't measure a surface the camera never saw. Most systems hide this and hand you a confident-looking model that's partly guessed."*
3. **Our answer:** *"Drishti3D uses GPS to recover real metric scale, reconstructs what was actually observed, and — this is the key — **colours every surface by whether it was measured or inferred.** Green you can trust and measure. Purple is an AI guess. Red was never seen. Measurements use only measured geometry, by default."*
4. **The proof:** *"Here's a real reconstruction from an uploaded video, live — with a quality report showing our error grouped by our own confidence bands. Nothing here is hardcoded."*
5. **The fit:** *"Video-native, single-pass, georeferenced, confidence-aware, and fully offline. No shipping product and no other approach occupies all five."*

### 15.2 The demo script (what to show, in order)

1. **Upload** a real drone video + telemetry in the wizard (screen B) — show telemetry preview validating.
2. **Process** live; the monitor (screen C) shows honest per-stage progress: frames extracted → blurry frames rejected → keyframes chosen → dynamic car masked → reconstruction running.
3. **Fast preview** (VGGT/SLAM path, if GPU present) pops a 3D preview within the demo window — the "wow."
4. **Verified result** (screen D): rotate the georeferenced cloud on the Cesium globe at real coordinates; toggle the **confidence layers**; the green/amber/purple/red legend is front and centre.
5. **Measure** a building height on green geometry → show the number + confidence. Then measure across a **purple** region → the tool **warns** it's inferred. *(This single moment is the whole thesis, live.)*
6. **Trajectory** on the 2D map (MapLibre) matching the GPS path.
7. **Report** (screen E): reconstruction stats, RMSE vs checkpoints, % geometry per confidence class, processing-time ratio, and a **"Known limitations"** section. Export a PLY/LAS/GLB to prove interoperability.

### 15.3 Anticipated judge questions and crisp answers

- **"Is that scale real / how do you know the size?"** → *"From GPS camera positions we solve a robust similarity transform — RANSAC Sim(3) — to recover metric scale. With RTK it's decimetre; with plain GPS we report metre-level absolute, and we say so."* (§4.5, §8.7)
- **"What about the far side of that building?"** → *"We never saw it, so we don't claim it — it's marked unobserved. We can optionally show an AI completion, clearly labelled purple, but it's excluded from measurement."* (§4.6)
- **"Isn't this just OpenDroneMap/Pix4D?"** → the §5.3 answer (photo-grid vs single-pass video; no competitor surfaces confidence; we run offline).
- **"How accurate is it?"** → *"Here are measured RMSE numbers against surveyed checkpoints, and here's error grouped by our confidence bands — calibrated, not asserted."* (§11.4)
- **"Does it need a GPU?"** → *"A full metric reconstruction runs CPU-only; the GPU accelerates dense MVS and the learned preview. Missing GPU degrades gracefully with warnings, never crashes."* (§10.2)
- **"What's actually AI here?"** → learned matching, feed-forward 3D (VGGT), monocular-depth densification, semantic masking — each with a defined role over a classical, accountable backbone. (§4.8)

### 15.4 The three things that lose SIH — and our guard against each

1. **A faked/hardcoded demo an expert catches.** → Guard: at least one path always reconstructs from the *uploaded* frames; the report is computed from real inputs.
2. **Over-claiming accuracy.** → Guard: confidence-calibrated, ground-truth-backed numbers; explicit GPS-limited caveats.
3. **A prototype that won't start / crashes on stage.** → Guard: runnable after every phase; CPU-only fallback; pre-captured dataset; deterministic seeds; graceful degradation on missing GPU/models.

---

## 16. Execution Roadmap to the Finale

**Golden rule:** the application must be **runnable after every phase.** Never enter a long broken state — a system that always starts beats a more ambitious one that doesn't.

**Phase 1 — Foundation (real inputs → real metrics).**
Repo scaffold · DB + schemas · upload wizard · telemetry parsing · frame extraction (FFmpeg) · frame-quality analysis (OpenCV) · processing-progress stream · unit tests. *Exit:* a user creates a mission, uploads video+telemetry, and sees quality metrics computed from real inputs.

**Phase 2 — Real reconstruction (the credibility milestone).**
COLMAP adapter (sequential matching, shared intrinsics, GPS priors) · store poses + sparse cloud · point-cloud API · 3D viewer · trajectory visualization. *Exit:* a genuine reconstruction from uploaded frames is displayed. **This is the phase that makes the demo real — prioritize it.**

**Phase 3 — Metric + measurable (the differentiator's foundation).**
WGS84→ECEF→ENU conversion · robust Sim(3) alignment · metric measurements (distance/height/area) · quality report · exports (PLY/LAS/GLB/GeoJSON/CSV/JSON/HTML). *Exit:* GPS aligns the model to metric ENU; distance/height measurement works; results export.

**Phase 4 — Intelligence layer (the winning feature).**
Dynamic masking · **confidence/provenance classification (the five classes)** · AI adapter interface · optional MASt3R-SLAM/VGGT integration. *Exit:* the confidence legend is live and measurements respect provenance.

**Phase 5 — Polish + deploy.**
Mesh generation · UI refinement · Docker/offline deployment · full testing + demo documentation. *Exit:* air-gapped Docker deployment; complete test suite; rehearsed demo.

### 16.1 Priority order if time is short (from the brief)

1. Real point-cloud reconstruction from video → 2. GPS-aligned camera trajectory → 3. Distance & height measurement → 4. Confidence visualization → 5. Dynamic-object masking → 6. Exportable artifacts → 7. Reproducible evaluation report.

*(Note the ordering: a **real reconstruction + measurement + confidence** is worth more than mesh polish. If forced to cut, cut meshing and extra exports, never the confidence story or the real reconstruction.)*

### 16.2 Acceptance criteria (the definition of "done enough to win")

The prototype is credible only if: it **starts with documented commands**; a user can create a mission and upload video+telemetry; **metadata/quality come from real inputs**; keyframes are extracted from the uploaded video; **at least one real reconstruction engine runs**; poses + cloud are stored and displayed; GPS aligns to metric ENU; distance/height measurement works; quality + confidence are shown; results export; **missing GPU/models warn rather than crash**; tests pass; and **no screen shows invented accuracy or fabricated results.**

### 16.3 First actions before writing code (the brief's starting instruction)

1. Inspect repo + dev environment. 2. Report detected OS/Python/Node/Docker/CUDA/GPU/FFmpeg/COLMAP availability. 3. Propose the final directory tree. 4. Identify restrictive-licence dependencies (§9.4). 5. State CPU-vs-GPU capabilities (§10.2). 6. Produce a concise plan + acceptance tests. 7. Implement Phase 1 fully. 8. Run its tests, show real results. 9. **Stop after Phase 1 and review** — do not generate all phases blindly.

### 16.4 Local environment findings (probe this machine before committing)

An environment probe on the target dev machine (2026-08-27) recorded:

| Capability | Detected | Action |
|---|---|---|
| OS shell | Windows PowerShell 5.1 | Build the GPU/COLMAP worker in **Docker/Linux** for reproducibility |
| Python | 3.13.5 | **Create a dedicated Python 3.11 env** — 3.13 has wheel gaps in PyTorch/PyCOLMAP/scientific stacks |
| Node / npm | 24.11.1 / 11.6.2 | Node 24 is ahead of some frontend packages — **pin an LTS** in `.nvmrc`/Volta and lock deps |
| Docker | 29.6.1 | Available — use for the reconstruction worker |
| GPU | **RTX 4060 Laptop, 8188 MiB** | 8 GB is tight: VGGT needs downscaled/windowed inputs; dense MVS needs controlled resolution; expect OOM tuning |
| FFmpeg / ffprobe | **Not on PATH** | Install and pin explicitly before any ingestion work |
| COLMAP | **Not on PATH** | Install/pin explicitly — never let the UI imply reconstruction capability just because the API starts |

**Consequence:** the 8 GB laptop GPU means the *permissive CPU path (sparse COLMAP + georegistration + Open3D) is the guaranteed backbone*, and every GPU stage (dense MVS, VGGT, MASt3R-SLAM) is capability-gated behind a preflight probe that records executable versions, CUDA availability, VRAM, disk, and writable paths. Presets are derived from that probe, not hardcoded.

### 16.5 Team-of-six ownership and finale role freeze

SIH teams are exactly six. Assign clear ownership but **cross-train every critical function** — no subsystem may have only one operator:

| Role | Owns | Backup knowledge |
|---|---|---|
| CV/reconstruction lead | COLMAP, learned adapters, masks | dataset + demo recovery |
| Geospatial/evaluation lead | sync, ENU/Sim(3), checkpoints | reconstruction diagnostics |
| Backend/platform lead | API, jobs, artifacts, offline packaging | storage recovery |
| Frontend/3D lead | viewer, map, measurement UX | API + model conventions |
| QA/data lead | capture, fixtures, tests, metrics, licences | demo operation |
| Product/pitch lead | NTRO workflow, submission, narrative, Q&A | full end-to-end demo |

**During the finale, freeze roles:** presenter, demo operator, technical-answer lead, system monitor/recovery, evidence navigator, note-taker/mentor liaison. Juries visit *several times* over the 36 hours — keep a short **change log** across rounds showing what you learned and improved (visible progression scores points). At each mentor visit: show newest working evidence in 60 s, ask one concrete decision question, classify feedback as required/experiment/out-of-scope, confirm interpretation, then demonstrate the change next round.

### 16.6 Quantitative win board and final go/no-go gates

Maintain a visible internal scorecard, updated from **real runs** (these are engineering gates, not promises to publish before measurement — replace targets with actual results in the presentation):

| KPI | Minimum demo gate | Stretch |
|---|---|---|
| End-to-end success on the fixed demo dataset | 5 consecutive runs | 10 consecutive |
| Registered selected keyframes | ≥ 70% | ≥ 90% |
| Relative known-distance error (strong observed region) | < 5% | < 3% |
| Independent checkpoint result | reported honestly | GPS: metre-level · RTK/GCP: decimetre or better |
| Fast-preview processing ÷ video duration | ≤ 2× | near 1× |
| Dynamic contamination reduction | measurable | ≥ 50% without major static loss |
| Offline smoke test | complete | fresh-machine reproducible |
| Demo recovery time after a failure | < 2 min | < 30 s |

**Final go/no-go (24 h before judging — add no feature unless it fixes a judging-critical gap).** The release candidate must pass: fresh start + capability preflight; full **offline** end-to-end smoke test; live short-dataset reconstruction; rich accepted-dataset viewer + artifact lineage; all measurement/geodesy tests; **no fabricated placeholder values or broken controls**; export/report download-and-open verification; 6-/3-/1-minute pitch rehearsals; a hostile-Q&A drill; and a backup machine/media with a rehearsed recovery path. The final optimisation is **reliability and clarity, not feature count.**

**Demo reliability engineering:** carry the exact raw demo inputs and immutable accepted outputs; keep a short 30–60 s "live" dataset with a predictable time envelope *and* a richer precomputed dataset whose lineage/logs can be inspected; cache only through the documented stage system and disclose cached stages if asked; record a backup demo video but use it only if hardware fails; never modify code/data right before evaluation without rerunning the smoke suite.

---

## 17. Glossary of Every Term Used

**Geometry & reconstruction**
- **SfM (Structure from Motion):** recovering 3D structure + camera poses from overlapping images.
- **Photogrammetry:** measurement from photographs; overlaps SfM, usually through dense + georeferenced output.
- **MVS (Multi-View Stereo):** densifying SfM output into a per-pixel dense point cloud/mesh.
- **SLAM (Simultaneous Localization and Mapping):** real-time, sequential tracking + mapping from a sensor stream.
- **VO (Visual Odometry):** estimating camera motion frame-to-frame (SLAM without global map optimization).
- **Bundle Adjustment (BA):** global nonlinear least-squares that minimizes reprojection error over all poses + points.
- **Reprojection error:** pixel gap between a 3D point's projection and its observed keypoint; the BA cost.
- **Feature / keypoint / descriptor:** a distinctive image location + a vector describing its neighbourhood (SIFT/ORB/SuperPoint).
- **Feature track:** one physical 3D point's chain of observations across frames; long tracks = higher confidence.
- **Epipolar geometry:** the constraint linking two views of a point to a line (the epipolar line).
- **Fundamental matrix (F) / Essential matrix (E):** encode epipolar geometry for uncalibrated / calibrated cameras; E factors into relative rotation + translation *direction*.
- **Triangulation:** intersecting rays from ≥2 views to locate a 3D point.
- **Triangulation / parallax angle:** angle between those rays; small angle (weak baseline) = uncertain depth.
- **Baseline:** distance between two camera viewpoints; wide baseline = better-conditioned depth.
- **PnP (Perspective-n-Point):** solving a camera's pose from known 2D–3D correspondences.
- **RANSAC:** robust estimation by random sampling + consensus; rejects outliers.
- **Keyframe:** a selected representative frame used for mapping (not every video frame).
- **Loop closure:** recognizing a revisited place to correct accumulated drift.
- **Drift:** accumulation of small sequential pose errors along a trajectory.
- **Dense / sparse cloud:** per-pixel vs keypoint-only 3D points.
- **Poisson / ball-pivoting:** surface-reconstruction (meshing) methods.
- **Point cloud / mesh / texture:** set of 3D points / connected surface of triangles / image draped on the surface.

**Scale, pose, transforms**
- **Monocular scale ambiguity:** a single camera cannot recover absolute size from images alone.
- **Gauge freedom:** an unobservable degree of freedom in a problem's solution (here, the overall similarity transform).
- **SE(3):** rigid transforms (rotation + translation), 6 DoF, distance-preserving.
- **Sim(3):** similarity transforms (rotation + translation + uniform scale), 7 DoF.
- **Umeyama algorithm:** closed-form least-squares Sim(3)/rigid alignment between two point sets.
- **Intrinsics / extrinsics:** camera internal parameters (focal length, principal point, distortion) / external pose.
- **Self-calibration:** estimating intrinsics during BA.

**Geodesy**
- **WGS84:** the global GPS datum/ellipsoid; lat/lon in degrees + height.
- **ECEF:** Earth-Centered Earth-Fixed metric Cartesian frame.
- **ENU:** local East-North-Up tangent-plane metric frame (our working frame).
- **UTM:** zoned metric map projection (easting/northing).
- **GSD (Ground Sampling Distance):** ground size of one image pixel; drives achievable accuracy.
- **Ellipsoidal vs orthometric height:** above the ellipsoid (GNSS) vs above the geoid/MSL (maps); **h = H + N**.
- **Geoid undulation (N):** ellipsoid-to-geoid separation.
- **GNSS / GPS:** satellite positioning; standard code-phase ≈ metre-level.
- **RTK / PPK:** carrier-phase differential GNSS (real-time / post-processed) ≈ centimetre-level.
- **GCP / checkpoint:** surveyed control point used in / withheld from the solution (the latter measures accuracy).
- **Georegistration:** aligning a reconstruction to real-world coordinates.

**Evaluation**
- **RMSE:** root-mean-square error (report horizontal and vertical separately).
- **ATE / RPE:** Absolute Trajectory Error (global) / Relative Pose Error (local drift).
- **Chamfer / C2C / C2M:** symmetric NN distance / cloud-to-cloud / point-to-mesh distance.
- **Precision / Recall / F-score @ d:** MVS accuracy/completeness within a tolerance (Tanks-and-Temples protocol).

**Models & tools**
- **COLMAP / PyCOLMAP:** reference classical SfM+MVS engine (+ Python bindings); BSD-3.
- **VGGT:** feed-forward transformer for poses/depth/points/tracks; CVPR 2025 Best Paper; COLMAP-exportable.
- **MASt3R-SLAM:** real-time dense monocular SLAM (~15 FPS on RTX 4090); CC BY-NC-SA.
- **DROID-SLAM:** deep dense-BA SLAM; BSD-3; ≥11 GB GPU.
- **DUSt3R / MASt3R:** feed-forward pointmap "geometric foundation models"; CC BY-NC-SA.
- **NeRF / 3D Gaussian Splatting:** neural/appearance-optimized scene representations for novel-view synthesis.
- **SuperPoint / SuperGlue / LightGlue / LoFTR / RoMa:** learned feature detection/matching.
- **Monocular depth (MiDaS/DPT/Depth Anything/Metric3D/ZoeDepth):** single-image depth prediction.
- **Open3D:** point-cloud processing + meshing (MIT). **pyproj/PROJ:** coordinate transforms (MIT).
- **FFmpeg/ffprobe:** frame extraction + video metadata. **ExifTool:** media GPS/metadata. **OpenCV:** frame processing/blur/optical flow.
- **CesiumJS / Three.js / MapLibre GL:** georeferenced 3D globe / general 3D viewer / 2D vector maps.
- **PLY / LAS-LAZ / OBJ / GLB / GeoJSON:** point-cloud / LiDAR-survey cloud / mesh interchange / web mesh / 2D geo-features.

---

## 18. Open Decisions and References

### 18.1 Decisions to confirm early (from the brief)

Confirm as soon as possible — several bound the whole design:

- Expected **NTRO telemetry formats** (what CSV/SRT/JSON fields we'll actually receive).
- Available **NVIDIA GPU and VRAM** (decides which learned engines are on the table).
- Whether deployment must be **internet-free / air-gapped** (assume yes; design for it).
- Whether **point-cloud output alone is sufficient** for the primary demo (likely yes; mesh is a bonus).
- **Licences permitted** for AI models/weights (rules MASt3R-SLAM/DUSt3R in or out for any commercial angle — §9.4).
- **Test drone/camera** and whether camera calibration is available (supplied intrinsics improve accuracy).
- One **public evaluation dataset** + one **team-captured dataset** with surveyed checkpoints (for honest RMSE).
- Which **accuracy claims** are backed by actual tests (never claim beyond the evidence).

### 18.2 Verification flags carried through this dossier

- **SIH dates/prize** are from secondary guides, not the official portal — reconfirm on sih.gov.in.
- **NTRO operational rationale** is inference from public mandate, not sourced doctrine — present it as such; no fake endorsements/markings.
- **Competitor prices/video-support** partly from a vendor page — reconfirm on each vendor's site.
- **VGGT drone-video FPS** unconfirmed (only "<1 s" network forward pass); **MASt3R-SLAM 15 FPS** is RTX-4090-specific.
- **No canonical outdoor georeferenced-UAV benchmark** exists; "UseGeo"/"Mid-Air" unverified.
- **No universal "relative dimensional error %"** — always state object size + GSD behind any figure.
- **SIH26158 submission deadline** is reported as **20 September 2026** on a problem-statement mirror (`sih2026.vuce.in/en/ps/SIH26158`) — as of today (2026-08-27) that is **~3.5 weeks out**; verify against the official sih.gov.in portal immediately, since it governs the whole schedule.

### 18.3 Key references (by theme)

**Core methods & tools**
- COLMAP — https://colmap.github.io/ · PyCOLMAP — https://colmap.github.io/pycolmap/pycolmap.html
- Hartley & Zisserman, *Multiple View Geometry in Computer Vision* (the standard text)
- VGGT — https://arxiv.org/abs/2503.11651 · https://github.com/facebookresearch/vggt · CVPR 2025 awards — https://cvpr.thecvf.com/Conferences/2025/News/Awards_Press
- MASt3R-SLAM — https://arxiv.org/abs/2412.12392 · https://edexheim.github.io/mast3r-slam/
- DROID-SLAM — https://arxiv.org/abs/2108.10869 · https://github.com/princeton-vl/DROID-SLAM
- DUSt3R — https://arxiv.org/abs/2312.14132 · MASt3R — https://arxiv.org/abs/2406.09756 · https://github.com/naver/dust3r
- 3D Gaussian Splatting — https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/ · Depth Anything V2 — https://github.com/DepthAnything/Depth-Anything-V2
- Open3D — https://www.open3d.org/ · pyproj — https://pyproj4.github.io/pyproj/ · FFmpeg — https://ffmpeg.org/ · ExifTool — https://exiftool.org/ · OpenCV — https://opencv.org/
- CesiumJS — https://cesium.com/platform/cesiumjs/ · Three.js — https://threejs.org/ · MapLibre — https://maplibre.org/

**Geodesy, alignment, evaluation**
- Umeyama (1991), *IEEE TPAMI* — https://dl.acm.org/doi/10.1109/34.476514
- Height datums (PSU GEOG 862) — http://www.e-education.psu.edu/geog862/node/1821 · NOAA NGS — https://www.ngs.noaa.gov/heightmod/HeightMod/Buttonwood/level.html
- ATE/RPE survey — https://arxiv.org/html/1811.09895v2
- Tanks and Temples (F-score protocol) — https://dl.acm.org/doi/10.1145/3072959.3073599 · https://tanksandtemples.org/tutorial/
- ETH3D — https://eth3d.ethz.ch/overview · TartanAir — https://arxiv.org/abs/2003.14338
- RTK/PPK accuracy — https://www.thedroneu.com/blog/drone-accuracy-gps-rtk-ppk/ · https://rtkdata.com/blog/rtk-vs-gps-accuracy-2026/
- GSD accuracy rule — https://www.mdpi.com/2072-4292/15/10/2700 · GCP vs no-GCP — https://www.skyebrowse.com/news/posts/ground-control-points-guide

**Program, customer, use cases**
- NTRO (public) — https://en.wikipedia.org/wiki/National_Technical_Research_Organisation
- Video-vs-photo 3D for disaster (NHESS 2018) — https://nhess.copernicus.org/articles/18/1583/2018/index.html
- SIH guides (reconfirm on official portal) — https://reskilll.com/blogs/smart-india-hackathon-2026-complete-guide-registration-themes-winning/
- Official SIH idea-selection guidelines — https://sih.gov.in/letters/Guidelines-College-SPOC.pdf
- SIH26158 problem mirror incl. 20 Sep 2026 deadline (verify on official portal) — https://sih2026.vuce.in/en/ps/SIH26158
- ASPRS Positional Accuracy Standards (Edition 2 v2, 2024; independent checkpoints, 30-checkpoint minimum) — https://old.asprs.org/archives/asprs-approves-edition-2-version-2-of-the-asprs-positional-accuracy-standards-for-digital-geospatial-data-2024.html

---

### Closing note

Read §4.5, §4.6, and §4.7 until they are second nature — the scale-ambiguity argument, the unobserved-surface argument, and the confidence/provenance model. They are the reason this project is scientifically honest, and honesty rendered *visible* (the green/amber/purple/red model) is the reason it wins. Everything else in this dossier is the scaffolding that lets you defend those three ideas under any question a jury can ask.

*Build the real thing. Show the real numbers. Colour the truth. Win.*

---

## Appendix A — MASt3R-SLAM (CVPR 2025) paper deep-dive

*Added 2026-08-27 after reading the primary source. Purpose: tighten our MASt3R-SLAM claims (§9, §10) against the paper itself and record the two facts that change how we should pitch and de-risk the optional AI/SLAM front-end.*

**Source of record.** Murai, Dexheimer, Davison (Imperial College London), *MASt3R-SLAM: Real-Time Dense SLAM with 3D Reconstruction Priors*, CVPR 2025 (Highlight). arXiv:2412.12392 (v2, Jun 2025) — https://arxiv.org/abs/2412.12392 · project page https://edexheim.github.io/mast3r-slam/ . The CVF page (openaccess.thecvf.com) blocks automated fetches; the arXiv v2 HTML is the same paper and is the copy these notes are drawn from. License remains **CC BY-NC-SA 4.0 (non-commercial)** — see §9.4/§10; unchanged by this appendix.

**A.1 What it actually is.** A full real-time monocular SLAM system built *bottom-up* on MASt3R's two-view reconstruction-and-matching prior. It outputs globally consistent camera poses **and** dense geometry from ordinary video. Four components: (1) fast **pointmap matching** by minimizing angular ray error; (2) **camera tracking + local pointmap fusion**; (3) **graph construction + loop closure**; (4) **second-order (Gauss–Newton) global optimisation**.

**A.2 The two facts worth pitching (new emphasis).**
- **Calibration-free / generic camera model.** It assumes nothing about the camera beyond a *single unique camera centre*, normalizing pointmaps into rays. It therefore tolerates **unknown and even time-varying intrinsics (including zoom)**. This is directly valuable for drone video where lens intrinsics are often unknown or uncalibrated — a stronger selling point for our AI adapter than the dossier currently states. With *known* calibration a small modification yields state-of-the-art results.
- **Ray-based matching is the efficiency win.** ~**2 ms vs ~2000 ms** against MASt3R's brute full-pixel matching — a claimed **1000× speedup** with no accuracy loss, and ~40× faster overall. This is why real-time is even possible.

**A.3 Performance reality on our hardware.** Paper reports **~14.6 FPS (they say "~15 FPS")** on an **RTX 4090** + i9-12900K (frames subsampled ×2): tracking 45.9 ms/frame, ~164.9 ms/keyframe, and the **encoder/decoder network is ~64% of runtime** ("using the decoder at full resolution is currently a bottleneck"). Our target is an **RTX 4060 Laptop, 8 GB** — expect materially lower FPS and real VRAM pressure. **Implication:** MASt3R-SLAM stays a Phase-4/5 *optional* front-end and a *fast-preview* path, never a live-demo dependency. Do not promise real-time on the laptop.

**A.4 Accuracy, briefly (ATE RMSE, m; "Ours" = calibrated, "Ours*" = uncalibrated).**
- TUM RGB-D: Ours 0.030 / Ours* 0.060 vs DROID-SLAM 0.038 (DROID* 0.158 — its uncalibrated robustness is far worse).
- 7-Scenes: Ours 0.047 / Ours* 0.066 vs DROID 0.049.
- EuRoC (11 seq): Ours 0.041 / Ours* **0.164** vs DROID **0.022** — DROID wins here, and the uncalibrated number degrades sharply.
- Reconstruction (Acc/Comp/Chamfer, m): more *accurate* than DROID (e.g. EuRoC 0.099/0.071/0.085 vs 0.173/0.061/0.117); DROID gets higher *completion* by emitting more, noisier points.

**A.5 Stated limitations (honest caveats — fold into §14 risks).**
- **Distortion sensitivity:** MASt3R is trained on *pinhole* images only, so "geometry predictions degrade with increasing distortion." Drone lenses carry real distortion → a genuine accuracy risk; undistort/calibrate before feeding frames.
- **Global geometry not fully refined:** "we do not currently refine all geometry in the full global optimisation."
- **Decoder-at-full-resolution bottleneck** limits low-latency tracking and loop-closure checks.

**A.6 Net for Drishti3D.** Confirms our existing §9.3/§10 claims (≈15 FPS on RTX 4090, CC BY-NC-SA). Adds one *strength* to lean on (calibration-free operation for uncalibrated drone footage) and two *caveats* to state up front (pinhole-distortion sensitivity; 8 GB VRAM ceiling). All consistent with our stance: measured geometry over inferred, and AI/SLAM priors as an optional, clearly-labelled fast path — not the accuracy backbone.





















