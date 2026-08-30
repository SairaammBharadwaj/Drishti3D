"""Drishti3D reconstruction package.

A modular, CPU-capable monocular reconstruction pipeline that turns a
single-pass drone video plus GPS/telemetry into a georeferenced, metrically
scaled point cloud with explicit per-point provenance and confidence.

The verified path (feature matching -> essential-matrix SfM -> triangulation ->
robust Sim(3) GPS alignment) runs without COLMAP, CUDA, or downloaded model
weights.  COLMAP and learned models (MASt3R-SLAM / VGGT) are optional adapters.
"""

__version__ = "0.1.0"

from .provenance import Provenance  # noqa: F401
