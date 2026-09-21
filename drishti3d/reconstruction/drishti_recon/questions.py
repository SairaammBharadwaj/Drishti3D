"""Measurement questions, tolerance acceptance, and refusal reasons.

This module is the gate described in plan features F2 (Tolerance Lens) and F5
(missing-evidence cards).  A *question* is what the operator asked -- a geometry
type, the entities selected, and the tolerance the answer must meet.  A
*verdict* is what this module decides about the answer: whether it can be
accepted, and if not, precisely which piece of evidence is missing.

Three rules shape everything here.

**Acceptance is a property of the whole measurement, not of the cloud.**  A
green voxel under an endpoint does not make a width accepted.  Scale, endpoint
localisation, view geometry and provenance all enter the same verdict.

**"Meets requirement" is a calibrated claim, and an uncalibrated system may not
make it.**  Predicted sigmas are a sensitivity model until held-out missions
show their intervals actually contain the truth at the stated rate.  Until a
:class:`CalibrationProfile` covering this capture regime exists and has enough
samples, the best available verdict is ``ESTIMATED_ONLY`` -- even when the
predicted interval is comfortably inside the tolerance.  Relaxing this is how a
system starts reporting confidence it has not earned.

**A refusal must name the missing evidence.**  ``NOT_OBSERVABLE`` with a reason
code is a useful answer; a silent failure or an invented number is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace
from enum import Enum

import numpy as np

from . import uncertainty as unc


class Status(str, Enum):
    """The four verdicts a measurement can carry (plan F2)."""

    MEETS_REQUIREMENT = "meets_requirement"
    ESTIMATED_ONLY = "estimated_only"
    NEEDS_REFINEMENT = "needs_refinement"
    NOT_OBSERVABLE = "not_observable"

    @property
    def exportable_as_accepted(self) -> bool:
        """Only an accepted measurement may leave the system as one."""
        return self is Status.MEETS_REQUIREMENT


class Reason(str, Enum):
    """Why a measurement is not accepted. Each maps to a concrete next action."""

    #: An endpoint snapped to geometry that was never triangulated.
    ENDPOINT_NOT_OBSERVED = "endpoint_not_observed"
    #: The propagated uncertainty is infinite or undefined.
    UNCERTAINTY_UNDEFINED = "uncertainty_undefined"
    #: The measurement touches AI-proposed geometry that no independent view
    #: has corroborated.
    TOUCHES_INFERRED_GEOMETRY = "touches_inferred_geometry"
    #: Endpoint supported by too few distinct views to triangulate reliably.
    INSUFFICIENT_VIEWS = "insufficient_views"
    #: The views that see the endpoint share almost the same ray direction, so
    #: depth is weakly observable however many of them there are.
    DEGENERATE_VIEW_GEOMETRY = "degenerate_view_geometry"
    #: No accepted metric scale source, so the number has no units to be wrong in.
    SCALE_NOT_ESTABLISHED = "scale_not_established"
    #: Scale exists but its own relative uncertainty already exceeds tolerance.
    SCALE_UNCERTAINTY_DOMINATES = "scale_uncertainty_dominates"
    #: The interval is finite and honest, but wider than what was asked for.
    INTERVAL_EXCEEDS_TOLERANCE = "interval_exceeds_tolerance"
    #: No validated calibration profile covers this capture, so the interval is
    #: a sensitivity estimate rather than a coverage-checked one.
    INTERVAL_NOT_CALIBRATED = "interval_not_calibrated"
    #: A calibration profile exists but was fitted on too few missions.
    CALIBRATION_SAMPLE_TOO_SMALL = "calibration_sample_too_small"
    #: An endpoint lies in space the capture never established.
    OUTSIDE_ESTABLISHED_COVERAGE = "outside_established_coverage"
    #: View support was inferred from camera frustums rather than from the
    #: observations that actually produced the geometry. The parallax figure is
    #: an upper bound, so it cannot license acceptance.
    VIEW_GEOMETRY_UNVERIFIED = "view_geometry_unverified"
    #: Supporting pixels were masked as dynamic.
    DYNAMIC_CONTAMINATION = "dynamic_contamination"


#: Operator-facing text and the action that would actually change the verdict.
REASON_GUIDANCE = {
    Reason.ENDPOINT_NOT_OBSERVED: (
        "An endpoint is not on reconstructed surface.",
        "Move the endpoint onto observed geometry, or accept that this surface "
        "was never seen in this pass."),
    Reason.UNCERTAINTY_UNDEFINED: (
        "The uncertainty of this measurement could not be propagated.",
        "Check that the endpoints carry positional covariance; a point added "
        "without triangulation has none."),
    Reason.TOUCHES_INFERRED_GEOMETRY: (
        "This measurement rests on AI-proposed geometry, not on triangulated "
        "observations.",
        "Restrict the endpoints to observed geometry, or corroborate the "
        "proposed surface against held-out views first."),
    Reason.INSUFFICIENT_VIEWS: (
        "Too few distinct views see this location.",
        "Run 'Improve this measurement' to pull unused frames from the same "
        "pass that also see it."),
    Reason.DEGENERATE_VIEW_GEOMETRY: (
        "The views that see this location look along nearly the same "
        "direction, so its depth is weakly constrained.",
        "Retrieve frames from a wider baseline in the same pass. If the flight "
        "never separated in that direction, no amount of compute recovers it."),
    Reason.SCALE_NOT_ESTABLISHED: (
        "This reconstruction has no accepted metric scale source.",
        "Supply telemetry, a calibrated camera, or a known reference length. "
        "Until then the model is shape-only, in arbitrary units."),
    Reason.SCALE_UNCERTAINTY_DOMINATES: (
        "The uncertainty of the metric scale alone is larger than the "
        "requested tolerance.",
        "A better scale source is required; refining local geometry cannot fix "
        "a scale error that multiplies the whole model."),
    Reason.INTERVAL_EXCEEDS_TOLERANCE: (
        "The measurement's interval is wider than the tolerance requested.",
        "Run 'Improve this measurement', or relax the tolerance."),
    Reason.INTERVAL_NOT_CALIBRATED: (
        "No validated calibration covers this capture, so the interval is a "
        "sensitivity estimate, not a coverage-checked one.",
        "Evaluate on held-out missions of this capture regime to fit and "
        "validate a calibration profile."),
    Reason.CALIBRATION_SAMPLE_TOO_SMALL: (
        "The calibration profile for this regime was fitted on too few "
        "samples to support a tail probability.",
        "Collect more independent missions in this regime before enabling "
        "calibrated acceptance."),
    Reason.OUTSIDE_ESTABLISHED_COVERAGE: (
        "An endpoint lies in space this flight never established.",
        "Unknown space cannot be measured. Another observation is required."),
    Reason.DYNAMIC_CONTAMINATION: (
        "Supporting pixels were excluded as moving objects.",
        "Use frames in which the surface is static and unobstructed."),
    Reason.VIEW_GEOMETRY_UNVERIFIED: (
        "Which frames actually produced this geometry is not recorded, so the "
        "view support shown is an upper bound from camera frustums.",
        "Per-point observation lineage must be persisted through the "
        "reconstruction before a measurement can be accepted on view support."),
}

#: Minimum independent calibration samples before a calibrated 95% interval is
#: allowed to drive acceptance.  Twenty is not a statistical guarantee -- it is
#: the point below which a 95% claim is obviously unsupportable, since a
#: distribution-free 95% bound needs at least 19 samples to exist at all.
MIN_CALIBRATION_SAMPLES = 20


class CalibrationState:
    """Lifecycle of an interval calibration, in order.

    Kept as three explicit states because collapsing them is exactly the error
    the review identified: a profile with enough samples to fit is not a
    profile anyone has checked, and a profile someone has checked is not one
    anyone has approved for use.
    """

    FITTED = "fitted"          # numbers exist, measured on the fitting set
    EVALUATED = "evaluated"    # checked against held-out missions
    RELEASED = "released"      # a person approved it for operational use


@dataclass
class CalibrationProfile:
    """A fitted, regime-scoped interval calibration.

    ``regime`` names what the profile is valid for (camera, capture pattern and
    metric source).  Applying a profile outside its regime is the failure mode
    this field exists to prevent; the caller must match it, because a profile
    cannot know where it is being used.
    """

    regime: str
    n_samples: int
    conformal_factors: dict = field(default_factory=dict)   # level -> k
    scale_factor: float = 1.0
    coverage_observed: dict = field(default_factory=dict)   # level -> fraction
    source: str = ""
    #: Where this profile is in its lifecycle. ``FITTED`` means numbers exist;
    #: ``EVALUATED`` means they were checked on data not used to fit them;
    #: ``RELEASED`` means a person approved it for operational use. Only the
    #: last licenses acceptance -- see :data:`CalibrationState`.
    state: str = "fitted"
    #: Missions whose measurements were used to fit. Held so a later evaluation
    #: can be checked for disjointness rather than asserted to be independent.
    fit_missions: tuple = ()
    #: Missions used for held-out evaluation. Must not intersect fit_missions.
    eval_missions: tuple = ()
    #: Coverage measured on the held-out set, level -> fraction. Distinct from
    #: coverage_observed, which is in-sample and always flattering.
    coverage_heldout: dict = field(default_factory=dict)
    #: 1-sigma of the reference instrument the errors were measured against.
    #: Without it a calibration cannot distinguish its own error from the
    #: tape measure's.
    reference_sigma_m: float | None = None
    approved_by: str = ""

    @classmethod
    def from_calibration(cls, result: unc.CalibrationResult, *, regime: str,
                         source: str = "",
                         fit_missions: tuple = ()) -> "CalibrationProfile":
        """Fit a profile. The result is FITTED -- never validated.

        ``validated`` used to be set here from the sample count alone, so
        reaching twenty measurements made a profile claim it had been
        validated. Sample count is a precondition for a meaningful fit, not
        evidence that the fit predicts anything: the samples it was measured on
        are the samples it was tuned to. Promotion now requires held-out
        evaluation (:meth:`evaluated`) and then a person (:meth:`released`).
        """
        return cls(regime=regime, n_samples=result.n,
                   conformal_factors={int(k): float(v) for k, v
                                      in result.conformal_factors.items()},
                   scale_factor=float(result.scale_factor),
                   coverage_observed={int(k): float(v) for k, v
                                      in result.coverage_conformal.items()},
                   source=source, state=CalibrationState.FITTED,
                   fit_missions=tuple(fit_missions))

    def evaluated(self, *, coverage_heldout: dict, eval_missions: tuple,
                  reference_sigma_m: float | None = None) -> "CalibrationProfile":
        """Record a held-out evaluation, refusing overlapping missions."""
        overlap = set(self.fit_missions) & set(eval_missions)
        if overlap:
            raise ValueError(
                "evaluation missions overlap the fitting set "
                f"({sorted(overlap)}); a profile cannot be evaluated on data "
                "it was fitted to")
        if not eval_missions:
            raise ValueError("held-out evaluation needs at least one mission")
        return replace(self, state=CalibrationState.EVALUATED,
                       eval_missions=tuple(eval_missions),
                       coverage_heldout={int(k): float(v)
                                         for k, v in coverage_heldout.items()},
                       reference_sigma_m=reference_sigma_m)

    def released(self, *, approved_by: str) -> "CalibrationProfile":
        """Approve an evaluated profile for operational use."""
        if self.state != CalibrationState.EVALUATED:
            raise ValueError(
                f"only an evaluated profile can be released (state={self.state})")
        if not approved_by:
            raise ValueError("release requires a named approver")
        return replace(self, state=CalibrationState.RELEASED,
                       approved_by=approved_by)

    @property
    def validated(self) -> bool:
        """Kept for callers that ask the old question; now means RELEASED."""
        return self.state == CalibrationState.RELEASED

    def usable(self) -> bool:
        return bool(self.state == CalibrationState.RELEASED
                    and self.n_samples >= MIN_CALIBRATION_SAMPLES
                    and self.conformal_factors)

    def applies_to(self, regime: str) -> bool:
        """Whether this profile may be used for a capture in ``regime``.

        Regime matching was left entirely to callers, which is how a profile
        fitted for one camera and capture pattern gets applied to another
        without anything objecting.
        """
        return bool(regime) and str(regime) == str(self.regime)

    def interval(self, sigma: float, level: int = 95) -> float:
        """Calibrated half-width for a predicted sigma, or ``inf`` if unknown.

        An unsupported level is refused rather than quietly answered with a
        95%-shaped factor: substituting one confidence level for another is
        the kind of silent approximation this whole subsystem exists to stop.
        """
        if sigma is None or not np.isfinite(sigma):
            return float("inf")
        k = self.conformal_factors.get(int(level))
        if k is None:
            return float("inf")
        return float(k) * float(sigma)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MeasurementQuestion:
    """What the operator asked, independent of any answer.

    Stored separately from the result so a tolerance change re-evaluates the
    same question against the same measurement rather than silently creating a
    new one -- the distinction the Tolerance Lens depends on.
    """

    kind: str                            # distance | height | area | point
    tolerance_m: float | None = None     # absolute, in the measurement's unit
    level: int = 95
    threshold_m: float | None = None     # for "is it at least X" queries
    threshold_direction: str = "at_least"   # at_least | at_most
    label: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Verdict:
    """The acceptance decision for one measurement against one question."""

    status: Status
    reasons: list = field(default_factory=list)          # list[Reason]
    interval_half_width: float | None = None
    interval_level: int = 95
    interval_basis: str = "uncalibrated_sensitivity"      # or "calibrated"
    threshold_result: str | None = None   # above | below | indeterminate
    dominant_limitation: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["reasons"] = [r.value for r in self.reasons]
        d["guidance"] = [{"reason": r.value,
                          "explanation": REASON_GUIDANCE[r][0],
                          "next_action": REASON_GUIDANCE[r][1]}
                         for r in self.reasons if r in REASON_GUIDANCE]
        hw = self.interval_half_width
        d["interval_half_width"] = (None if hw is None or not np.isfinite(hw)
                                    else float(hw))
        d["interval_half_width_is_infinite"] = bool(
            hw is not None and not np.isfinite(hw))
        return d


@dataclass
class Evidence:
    """What supports a measurement, as facts the verdict can be derived from.

    Every field defaults to the pessimistic reading, so a caller that has not
    yet wired a source of evidence gets a refusal rather than an accidental
    acceptance.
    """

    n_supporting_views: int = 0
    #: Largest angle, in degrees, between any two view rays to the endpoints.
    #: This is the parallax that makes depth observable; view *count* does not.
    max_ray_separation_deg: float = 0.0
    #: How ``n_supporting_views`` and ``max_ray_separation_deg`` were obtained.
    #: ``"triangulated_observations"`` means they come from the image
    #: observations that actually produced the point. ``"frustum_upper_bound"``
    #: means they were inferred from camera geometry, which can only overstate
    #: support, and therefore cannot license acceptance.
    view_support_basis: str = "frustum_upper_bound"
    touches_inferred: bool = False
    endpoints_observed: bool = False
    endpoints_within_coverage: bool = True
    dynamic_contamination: bool = False
    scale_source: str = "none"           # gps | control | known_length | none
    scale_sigma_rel: float = float("nan")

    def to_dict(self) -> dict:
        return asdict(self)


#: Below this ray separation, depth is weakly observable regardless of how many
#: views exist. Chosen to match the triangulation angle the SfM front end
#: already refuses to triangulate below (``min_tri_angle`` default 1.0 deg),
#: with a margin, so the two stages cannot disagree about what is measurable.
MIN_RAY_SEPARATION_DEG = 2.0

#: Fewer than this many views and a point is a two-view intersection with no
#: redundancy: one bad match moves it and nothing detects that.
MIN_SUPPORTING_VIEWS = 3


def evaluate(question: MeasurementQuestion, *, value: float | None,
             sigma: float | None, evidence: Evidence,
             profile: CalibrationProfile | None = None) -> Verdict:
    """Decide a measurement's status against a question.

    ``sigma`` is the propagated 1-sigma of ``value`` from :mod:`uncertainty`.
    ``profile`` is the calibration for *this capture regime*; passing a profile
    fitted elsewhere is the caller's error and cannot be detected here.
    """
    reasons: list = []

    # ---- hard refusals: no number should be reported at all --------------
    if value is None:
        return Verdict(Status.NOT_OBSERVABLE, [Reason.ENDPOINT_NOT_OBSERVED],
                       detail={"value": None})
    if not evidence.endpoints_observed:
        reasons.append(Reason.ENDPOINT_NOT_OBSERVED)
    if not evidence.endpoints_within_coverage:
        reasons.append(Reason.OUTSIDE_ESTABLISHED_COVERAGE)
    if evidence.touches_inferred:
        reasons.append(Reason.TOUCHES_INFERRED_GEOMETRY)
    if sigma is None or not np.isfinite(sigma):
        reasons.append(Reason.UNCERTAINTY_UNDEFINED)
    if reasons:
        return Verdict(Status.NOT_OBSERVABLE, reasons,
                       interval_half_width=float("inf"),
                       interval_level=question.level,
                       dominant_limitation=_dominant(reasons),
                       detail=_detail(value, sigma, evidence, profile))

    # ---- soft limitations: a number exists, its standing is the question --
    if evidence.dynamic_contamination:
        reasons.append(Reason.DYNAMIC_CONTAMINATION)
    if evidence.max_ray_separation_deg < MIN_RAY_SEPARATION_DEG:
        reasons.append(Reason.DEGENERATE_VIEW_GEOMETRY)
    if evidence.n_supporting_views < MIN_SUPPORTING_VIEWS:
        reasons.append(Reason.INSUFFICIENT_VIEWS)
    if evidence.view_support_basis != "triangulated_observations":
        reasons.append(Reason.VIEW_GEOMETRY_UNVERIFIED)
    if evidence.scale_source in ("none", "", None):
        reasons.append(Reason.SCALE_NOT_ESTABLISHED)

    calibrated = profile is not None and profile.usable()
    if profile is None:
        reasons.append(Reason.INTERVAL_NOT_CALIBRATED)
    elif not profile.usable():
        reasons.append(Reason.CALIBRATION_SAMPLE_TOO_SMALL
                       if profile.n_samples < MIN_CALIBRATION_SAMPLES
                       else Reason.INTERVAL_NOT_CALIBRATED)

    half = (profile.interval(sigma, question.level) if calibrated
            else _Z(question.level) * float(sigma))
    basis = "calibrated" if calibrated else "uncalibrated_sensitivity"

    # Scale uncertainty that already exceeds the tolerance is a distinct
    # failure: no local refinement can repair a multiplier on the whole model,
    # so the suggested action has to differ.
    tol = question.tolerance_m
    if (tol is not None and np.isfinite(evidence.scale_sigma_rel)
            and evidence.scale_sigma_rel * abs(value) * _Z(question.level) > tol):
        reasons.append(Reason.SCALE_UNCERTAINTY_DOMINATES)

    threshold = _threshold(value, half, question)

    if tol is None:
        status = Status.ESTIMATED_ONLY
    elif half > tol:
        reasons.append(Reason.INTERVAL_EXCEEDS_TOLERANCE)
        status = Status.NEEDS_REFINEMENT
    elif calibrated and not _blocking(reasons):
        status = Status.MEETS_REQUIREMENT
    else:
        # The interval fits, but the claim behind it is not yet supportable.
        status = Status.ESTIMATED_ONLY

    return Verdict(status, reasons, interval_half_width=float(half),
                   interval_level=question.level, interval_basis=basis,
                   threshold_result=threshold,
                   dominant_limitation=_dominant(reasons),
                   detail=_detail(value, sigma, evidence, profile))


#: Reasons that block acceptance even when the interval fits the tolerance.
#: Dynamic contamination is deliberately *not* here: a masked pixel excluded
#: from the fit degrades support, which the view count and ray separation
#: already capture, and double-counting it would refuse measurements that are
#: genuinely well supported by the remaining views.
_BLOCKING = {
    Reason.INTERVAL_NOT_CALIBRATED, Reason.CALIBRATION_SAMPLE_TOO_SMALL,
    Reason.SCALE_NOT_ESTABLISHED, Reason.SCALE_UNCERTAINTY_DOMINATES,
    Reason.DEGENERATE_VIEW_GEOMETRY, Reason.INSUFFICIENT_VIEWS,
    Reason.TOUCHES_INFERRED_GEOMETRY, Reason.ENDPOINT_NOT_OBSERVED,
    Reason.OUTSIDE_ESTABLISHED_COVERAGE, Reason.UNCERTAINTY_UNDEFINED,
    Reason.VIEW_GEOMETRY_UNVERIFIED,
}


def _blocking(reasons) -> bool:
    return any(r in _BLOCKING for r in reasons)


#: Ordered worst-first: the limitation reported to the operator is the one that
#: would have to be fixed first for the verdict to change.
_PRIORITY = [
    Reason.ENDPOINT_NOT_OBSERVED, Reason.OUTSIDE_ESTABLISHED_COVERAGE,
    Reason.UNCERTAINTY_UNDEFINED, Reason.TOUCHES_INFERRED_GEOMETRY,
    Reason.SCALE_NOT_ESTABLISHED, Reason.SCALE_UNCERTAINTY_DOMINATES,
    Reason.DEGENERATE_VIEW_GEOMETRY, Reason.INSUFFICIENT_VIEWS,
    Reason.VIEW_GEOMETRY_UNVERIFIED,
    Reason.DYNAMIC_CONTAMINATION, Reason.INTERVAL_EXCEEDS_TOLERANCE,
    Reason.CALIBRATION_SAMPLE_TOO_SMALL, Reason.INTERVAL_NOT_CALIBRATED,
]


def _dominant(reasons):
    for r in _PRIORITY:
        if r in reasons:
            return r.value
    return None


#: Confidence levels with a defined normal factor. Anything else has to be
#: refused: quietly answering a 97% request with a 95%-shaped number is the
#: same substitution CalibrationProfile.interval refuses for calibrated
#: intervals, and it would be no better here.
SUPPORTED_INTERVAL_LEVELS = (50, 68, 80, 90, 95, 99)

_Z_TABLE = {50: 0.6745, 68: 1.0, 80: 1.2816, 90: 1.6449, 95: 1.96, 99: 2.5758}


def _Z(level: int) -> float:
    try:
        return _Z_TABLE[int(level)]
    except KeyError:
        raise ValueError(
            f"interval level {level} is not supported; "
            f"choose one of {list(SUPPORTED_INTERVAL_LEVELS)}") from None


def _threshold(value, half, q: MeasurementQuestion):
    """Compare an interval against a threshold without collapsing it to a point.

    Returning "above" because the point estimate is above the threshold is the
    error this exists to prevent: it discards exactly the uncertainty the
    operator asked the system to carry.
    """
    if q.threshold_m is None:
        return None
    if not np.isfinite(half):
        return "indeterminate"
    lo, hi = value - half, value + half
    if q.threshold_direction == "at_least":
        if lo >= q.threshold_m:
            return "above"
        if hi < q.threshold_m:
            return "below"
    else:
        if hi <= q.threshold_m:
            return "below"
        if lo > q.threshold_m:
            return "above"
    return "indeterminate"


def _detail(value, sigma, evidence: Evidence, profile) -> dict:
    return {
        "value": None if value is None else float(value),
        "sigma": (None if sigma is None or not np.isfinite(sigma)
                  else float(sigma)),
        "sigma_is_infinite": bool(sigma is not None and not np.isfinite(sigma)),
        "evidence": evidence.to_dict(),
        "calibration_profile": profile.to_dict() if profile else None,
    }
