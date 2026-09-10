"""Can this capture meet the accuracy someone asked for — and if not, what to refly?

This is the difference between post-processing software and an operational tool.
Everything else in this pipeline answers "what did this flight produce?". This
module answers the two questions a pilot actually has:

* **Before trusting the result:** was this capture geometrically capable of the
  accuracy required, or is the answer limited by how it was flown?
* **When it was not:** what is the smallest additional flying that would fix it?

The distinction that makes this useful is between *fixable* and *unfixable*
limits. A scene that is unobserved can be flown again. A scene photographed with
no parallax cannot be rescued by processing at all, and saying so before someone
builds a decision on the number is worth more than any amount of extra
computation.

Nothing here is a learned model. Every factor is a geometric or photometric
quantity already measured elsewhere in the pipeline, combined explicitly so a
report can say *which* factor limited the capture rather than emitting an opaque
score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


#: Factor -> (weight, human explanation of what a low score means).
_FACTORS = {
    "parallax": (0.30, "triangulation angles too small; depth is weakly observed"),
    "coverage": (0.25, "much of the scene was never established by any camera"),
    "registration": (0.20, "frames failed to register; the model is incomplete"),
    "redundancy": (0.15, "surfaces seen by too few views to cross-check"),
    "image_quality": (0.10, "frames too blurred or poorly exposed for reliable matching"),
}


@dataclass
class CaptureAssessment:
    """A verdict on what this capture was geometrically capable of."""

    score: float                       # [0,1], weighted across factors
    grade: str                         # excellent | good | marginal | inadequate
    factors: dict = field(default_factory=dict)      # name -> [0,1]
    limiting_factor: str | None = None
    achievable_sigma_m: float | None = None          # expected 1-sigma, metres
    meets_requirement: bool | None = None
    messages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "grade": self.grade,
                "factors": self.factors,
                "limiting_factor": self.limiting_factor,
                "achievable_sigma_m": self.achievable_sigma_m,
                "meets_requirement": self.meets_requirement,
                "messages": self.messages}


def _clip01(x) -> float:
    return float(np.clip(x, 0.0, 1.0))


def assess(*, recon_stats: dict | None = None, coverage_summary: dict | None = None,
           uncertainty_summary: dict | None = None,
           frame_metrics: list | None = None,
           required_sigma_m: float | None = None) -> CaptureAssessment:
    """Score a completed capture, and say what limited it.

    Deliberately built from quantities the pipeline already measured, rather than
    a separate model: a score a report cannot explain is not actionable, and the
    point of this is to tell someone what to do differently.
    """
    rec = recon_stats or {}
    cov = coverage_summary or {}
    unc = uncertainty_summary or {}
    factors: dict = {}
    messages: list = []

    # Parallax: mean triangulation angle. ~10 deg is comfortable for a single
    # pass; below ~2 deg depth is essentially unobserved.
    tri = rec.get("mean_tri_angle")
    if tri is not None:
        factors["parallax"] = _clip01((float(tri) - 1.0) / 9.0)

    # Coverage: how much of the scene volume the flight actually established.
    if cov.get("fraction_explained") is not None:
        factors["coverage"] = _clip01(float(cov["fraction_explained"]) / 0.6)

    # Registration: frames that failed to solve are missing evidence.
    if rec.get("registered_fraction") is not None:
        factors["registration"] = _clip01(float(rec["registered_fraction"]))

    # Redundancy: measurable surface, i.e. seen by enough views to cross-check.
    if cov.get("measurable_surface_fraction") is not None:
        factors["redundancy"] = _clip01(float(cov["measurable_surface_fraction"]))
    elif rec.get("mean_track_length") is not None:
        factors["redundancy"] = _clip01((float(rec["mean_track_length"]) - 2.0) / 4.0)

    # Image quality: the accepted fraction from frame scoring.
    if frame_metrics:
        acc = [bool(getattr(m, "accepted", True)) for m in frame_metrics]
        if acc:
            factors["image_quality"] = _clip01(sum(acc) / len(acc))

    if not factors:
        return CaptureAssessment(0.0, "unknown", {}, None, None, None,
                                 ["no capture statistics available to assess"])

    # Renormalise over the factors we could actually measure, so a missing input
    # is not silently scored as zero.
    total_w = sum(_FACTORS[k][0] for k in factors)
    score = sum(_FACTORS[k][0] * v for k, v in factors.items()) / total_w
    limiting = min(factors, key=lambda k: factors[k])

    if score >= 0.8:
        grade = "excellent"
    elif score >= 0.6:
        grade = "good"
    elif score >= 0.35:
        grade = "marginal"
    else:
        grade = "inadequate"

    if factors[limiting] < 0.6:
        messages.append(f"limited by {limiting}: {_FACTORS[limiting][1]}")

    # Expected achievable uncertainty, taken from the propagated per-point sigma
    # rather than invented: this is what the capture actually delivered.
    sigma = None
    smaj = (unc.get("sigma_major_m") or {})
    if smaj.get("median") is not None:
        sigma = float(smaj["median"])
    meets = None
    if required_sigma_m is not None and sigma is not None:
        meets = bool(sigma <= required_sigma_m)
        if not meets:
            messages.append(
                f"typical positional uncertainty {sigma:.3f} m exceeds the "
                f"required {required_sigma_m:.3f} m")

    return CaptureAssessment(float(score), grade, factors, limiting, sigma,
                             meets, messages)


# --------------------------------------------------------------------------- #
# recapture planning
# --------------------------------------------------------------------------- #
@dataclass
class RecapturePlan:
    """The smallest additional flying that would materially improve the result."""

    actions: list = field(default_factory=list)
    waypoints: list = field(default_factory=list)      # ENU positions to revisit
    expected_gain: str = ""
    unfixable: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"actions": self.actions, "waypoints": self.waypoints,
                "expected_gain": self.expected_gain, "unfixable": self.unfixable}


def plan_recapture(assessment: CaptureAssessment, *, coverage_grid=None,
                   max_waypoints: int = 5) -> RecapturePlan:
    """Turn a diagnosis into flying instructions.

    Ordered by the limiting factor, because advice that does not address the
    binding constraint wastes a flight. Anything that *cannot* be fixed by
    reflying is listed separately rather than dressed up as an action — telling
    someone to fly again when the problem is their sensor or their subject is
    worse than telling them nothing.
    """
    actions: list = []
    unfixable: list = []
    waypoints: list = []
    lim = assessment.limiting_factor
    f = assessment.factors

    # Advice is triggered by a factor being *deficient*, never by it merely being
    # the lowest. Every assessment has a lowest factor, including a perfect one,
    # so keying off `limiting_factor` alone tells an excellent capture to refly.
    # `lim` is used for prioritisation in the summary, not as a trigger.
    if f.get("parallax", 1.0) < 0.5:
        actions.append(
            "Fly a second pass at a different angle -- ideally an orbit around "
            "the subject, or a pass perpendicular to the first. Triangulation "
            "angle, not image count, is what fixes depth.")
    if f.get("coverage", 1.0) < 0.5:
        actions.append(
            "Extend coverage over the unestablished regions listed below; much "
            "of the scene volume was never seen by any camera.")
    if f.get("registration", 1.0) < 0.8:
        actions.append(
            "Increase overlap between consecutive frames (slower flight or "
            "higher frame rate); frames failed to register into the model.")
    if f.get("redundancy", 1.0) < 0.5:
        actions.append(
            "Add a repeat pass so surfaces are seen from several viewpoints; "
            "single-view surface cannot be cross-checked and is not measurable.")
    if f.get("image_quality", 1.0) < 0.6:
        unfixable.append(
            "Image quality limited the result (blur or exposure). Reflying helps "
            "only if the capture settings change -- slower flight, shorter "
            "exposure, or better light.")

    # Waypoints are only worth emitting when there is something to act on;
    # a well-covered scene always has *some* lowest-coverage column.
    if coverage_grid is not None and actions:
        try:
            from . import coverage as covmod
            hints = covmod.recapture_hints(coverage_grid, top=max_waypoints)
            waypoints = [h["enu"] for h in hints]
            if hints:
                actions.append(
                    f"{len(hints)} unestablished region(s) identified; the "
                    "waypoints give their horizontal centres.")
        except Exception:
            pass

    if not actions:
        gain = "capture is adequate; a repeat flight is unlikely to help materially"
    else:
        gain = (f"addressing '{lim}' is the highest-value change; the capture "
                f"currently grades '{assessment.grade}' "
                f"({assessment.score:.2f}/1.00)")

    return RecapturePlan(actions, waypoints, gain, unfixable)
