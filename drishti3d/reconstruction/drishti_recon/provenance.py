"""Provenance / confidence classes for reconstructed geometry.

The scientific invariant of Drishti3D: never present hallucinated or unobserved
geometry as measured truth.  Every point and surface carries one of these
classes.  Measurements default to OBSERVED_* geometry only.
"""
from __future__ import annotations

from enum import IntEnum


class Provenance(IntEnum):
    """Integer-coded provenance so it can live in point-cloud attributes."""

    OBSERVED_HIGH_CONFIDENCE = 0
    OBSERVED_LOW_CONFIDENCE = 1
    AI_ASSISTED = 2
    DYNAMIC_EXCLUDED = 3
    UNOBSERVED = 4
    #: Inferred geometry that then *passed* an independent multi-view test:
    #: reprojected into neighbouring views and found consistent in depth and
    #: colour. Kept distinct from AI_ASSISTED because "a model produced it" and
    #: "several real cameras agree with it" are different claims -- and only the
    #: second is evidence. Still not measurable by default; it is corroborated,
    #: not triangulated.
    AI_GEOMETRICALLY_VERIFIED = 5

    @property
    def measurable(self) -> bool:
        """Whether points of this class are used in measurements by default."""
        return self in (Provenance.OBSERVED_HIGH_CONFIDENCE,)

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def color(self) -> tuple[int, int, int]:
        """Suggested RGB (0-255) for viewer/exports."""
        return _COLORS[self]


_LABELS = {
    Provenance.OBSERVED_HIGH_CONFIDENCE: "Observed (high confidence)",
    Provenance.OBSERVED_LOW_CONFIDENCE: "Observed (low confidence)",
    Provenance.AI_ASSISTED: "AI-assisted / inferred",
    Provenance.DYNAMIC_EXCLUDED: "Dynamic (excluded)",
    Provenance.UNOBSERVED: "Unobserved",
    Provenance.AI_GEOMETRICALLY_VERIFIED: "AI-inferred, multi-view verified",
}

# Green / Amber / Purple / Red per the brief's suggested legend.
_COLORS = {
    Provenance.OBSERVED_HIGH_CONFIDENCE: (46, 204, 113),
    Provenance.OBSERVED_LOW_CONFIDENCE: (241, 196, 15),
    Provenance.AI_ASSISTED: (155, 89, 182),
    Provenance.DYNAMIC_EXCLUDED: (231, 76, 60),
    Provenance.UNOBSERVED: (127, 140, 141),
    # Teal: visibly related to the observed green, visibly not the same thing.
    Provenance.AI_GEOMETRICALLY_VERIFIED: (26, 188, 156),
}


def classify(confidence: float) -> Provenance:
    """Map a scalar [0,1] confidence to an observed provenance class."""
    if confidence >= 0.6:
        return Provenance.OBSERVED_HIGH_CONFIDENCE
    return Provenance.OBSERVED_LOW_CONFIDENCE
