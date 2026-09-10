"""The ablation registry: one named variant == one recorded parameter set.

A benchmark row must be reproducible from its name alone.  Encoding each
ablation as pipeline *parameters* (rather than an edited source tree or a
commented-out block) is what makes "baseline vs. +BA" a controlled comparison:
every variant in a run shares the same code, the same inputs and the same seeds,
and differs only in the dictionary recorded beside its numbers.

Add a variant here when you add a component; never change an existing variant's
meaning, because published numbers are keyed by its name.
"""
from __future__ import annotations

#: name -> (human description, PipelineParams overrides)
VARIANTS: dict[str, tuple[str, dict]] = {
    "baseline": (
        "OpenCV incremental SfM as shipped: sequential+GPS-proximity matching, "
        "essential-matrix init, PnP registration, no bundle adjustment.",
        {"bundle_adjust": False},
    ),
    "ba": (
        "Baseline + sparse bundle adjustment (interim solves every 8 registered "
        "cameras, then one global solve). Intrinsics held fixed.",
        {"bundle_adjust": True, "ba_every": 8},
    ),
    "ba_focal": (
        "BA with focal-length refinement in the final global solve. Isolates "
        "whether a self-calibrated focal helps or absorbs geometric error.",
        {"bundle_adjust": True, "ba_every": 8, "refine_focal": True},
    ),
    "ba_focal_dist": (
        "BA refining focal length and Brown-Conrady distortion (k1,k2,p1,p2). "
        "The full self-calibration arm of the camera-model ablation.",
        {"bundle_adjust": True, "ba_every": 8, "refine_focal": True,
         "refine_distortion": True},
    ),
    # --- feature-matcher ablation (roadmap phase 5) ----------------------- #
    # These share the pair graph, geometric verification and every downstream
    # threshold with `baseline`; only detection and descriptor matching differ,
    # which is what makes the comparison attributable to the matcher.
    "orb": (
        "Baseline with ORB binary features instead of SIFT. A classical control "
        "for the matcher adapter -- different descriptor type and distance "
        "metric, no download required.",
        {"bundle_adjust": False, "matcher": "orb"},
    ),
    "lightglue": (
        "Baseline with learned features (DISK) matched by LightGlue. "
        "Permissively licensed weights only; SuperPoint is refused by default.",
        {"bundle_adjust": False, "matcher": "lightglue"},
    ),
    "ba_lightglue": (
        "Bundle-adjusted reconstruction on LightGlue matches, for the case where "
        "better correspondences change what BA can recover.",
        {"bundle_adjust": True, "matcher": "lightglue"},
    ),
}


def resolve(name: str) -> dict:
    """Return the pipeline-parameter overrides for a variant name."""
    if name not in VARIANTS:
        raise KeyError(f"unknown variant {name!r}; known: {sorted(VARIANTS)}")
    return dict(VARIANTS[name][1])


def describe(name: str) -> str:
    return VARIANTS[name][0]
