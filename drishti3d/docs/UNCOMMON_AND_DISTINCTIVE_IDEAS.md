# Drishti3D uncommon and distinctive ideas

These are hypotheses for differentiation, not pre-validated features. Each idea is
written so it can be disproved cheaply. “Unique” here means an uncommon product or
technical combination for this prototype; it is not a patent or market-novelty claim.

## 1. Measurement passport

Every user measurement gets a machine-readable passport containing the source
pixels in every supporting frame, camera poses, ray intersection geometry,
triangulation angles, calibration/version hashes, point provenance, scale source,
uncertainty interval and all transforms. Clicking a distance highlights the exact
image evidence that created it.

**Why it matters:** most 3D tools expose a number; this exposes an auditable chain
from pixels to number. **Proof test:** a third party can reproduce the measurement
from the passport without the Drishti3D database.

## 2. Counterfactual recapture planner

For a requested measurement, simulate candidate extra viewpoints and estimate
which shortest safe mini-flight would reduce its uncertainty below target. Return
an instruction such as “12 m lateral move, 20° oblique view of the east wall,” not
the generic advice “capture more overlap.”

**Why it matters:** it closes the loop between reconstruction failure and action.
**Proof test:** on held-out scenes, execute the suggested view and compare uncertainty
and actual error with a random equal-length recapture.

## 3. Geometry challenge protocol

Treat AI geometry as a hypothesis that must answer challenges: does it reproject
consistently into unused frames, preserve occlusion ordering, agree with silhouettes,
and survive leave-one-view-out reconstruction? Promote only the passing patches from
`AI_ONLY` to `AI_GEOMETRICALLY_VERIFIED`; retain failures as visual-only context.

**Proof test:** measure precision/recall of promoted patches against GT and compare
with raw AI confidence. Promotion must predict actual geometric correctness.

## 4. Evidence escrow and tamper-evident mission bundle

Hash each input chunk and artifact into a Merkle-style mission manifest. Optionally
sign the final root locally. Reports can prove which video, telemetry, parameters,
models and manual edits produced a scene—even in an air-gapped deployment.

**Proof test:** changing one telemetry row, point, model hash or measurement must
invalidate verification and identify the affected lineage.

## 5. Leave-one-view-out fragility map

Reconstruct or locally re-optimize while withholding each supporting view in turn.
Color a surface by how much its position changes. This empirically catches geometry
that looks confident from reprojection error yet depends dangerously on one frame.

**Proof test:** fragility should correlate with held-out spatial error more strongly
than the current hand-weighted confidence score.

## 6. Scale-consensus court

Represent GNSS trajectory, barometric altitude, RTK/PPK, known object dimensions,
GCPs and IMU as independent “witnesses” for scale/orientation. Show agreement and
conflict explicitly rather than collapsing them immediately to one transform. A
robust solver returns a consensus plus which witness appears inconsistent.

**Proof test:** inject a 10% wrong known dimension or altitude bias; the system must
flag the conflicting witness instead of silently deforming the scene.

## 7. Honest negative-space twin

Alongside the point cloud, maintain an observation-space volume with `seen free`,
`seen surface`, `occluded`, `outside all frusta`, and `dynamic-contaminated` cells.
This makes “unknown” a first-class deliverable and permits questions such as “which
side of this building has no defensible measurement?”

**Proof test:** synthetic hidden surfaces must remain unknown; the model must never
turn lack of evidence into high-confidence empty or solid space.

## 8. Mission difficulty fingerprint

Before expensive reconstruction, summarize a pass as a fingerprint: texture entropy,
blur distribution, pairwise overlap graph connectivity, parallax spectrum, repeated-
pattern risk, rolling-shutter risk, GNSS observability and dynamic fraction. Match it
to historical missions to predict failure mode and choose a pipeline automatically.

**Proof test:** cross-validated prediction of registration failure and error bucket;
compare with a simple duration/frame-count baseline.

## 9. Dual-reconstructor disagreement alarm

Run a classical sparse engine and a learned geometry engine independently. After
gauge alignment, map where their camera poses/depths disagree. Agreement does not
prove truth, but concentrated disagreement is a powerful abstention signal and can
route only uncertain regions for extra processing or recapture.

**Proof test:** disagreement must predict GT error on held-out scenes; if it does not,
do not expose it as confidence.

## 10. Measurement-first reconstruction budget

Let the operator mark the object or question before processing. Allocate matching,
BA, dense inference and recapture effort to rays that influence that measurement,
while retaining a coarse context cloud elsewhere. The output is optimized for the
decision, not for uniformly pretty geometry.

**Proof test:** under the same time/VRAM budget, targeted processing must reduce the
selected measurement's error or uncertainty more than uniform processing.

## 11. Temporal-change evidence without full remapping

Register a later single pass to the prior evidence twin, then distinguish supported
change from alignment uncertainty, new occlusion and dynamic objects. Every detected
change receives before/after source rays and a minimum detectable change threshold.

**Proof test:** use controlled moved objects and unchanged checkpoints; report change
precision/recall as a function of size, not merely a colored difference cloud.

## 12. Adversarial self-audit mode

Automatically perturb plausible nuisance variables—time offset, focal length,
distortion, GPS vertical bias, match threshold and frame subset—and report which
measurements remain stable. A number that changes drastically under plausible input
uncertainty is blocked or labeled fragile.

**Proof test:** perturbation envelopes should contain actual error at the advertised
rate on held-out data. This converts hidden assumptions into visible risk.

## Suggested uniqueness stack

The most defensible combination is: **measurement passport + negative-space twin +
counterfactual recapture planner + geometry challenge protocol**. Together they form
a coherent promise: Drishti3D shows what supports a measurement, what is missing,
how inferred geometry was tested, and the smallest action needed to improve it.

