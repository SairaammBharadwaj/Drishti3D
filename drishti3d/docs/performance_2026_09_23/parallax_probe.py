"""Read-only CPU microbenchmark of an equivalent dense-parallax calculation.

Uses a deterministic sample of a saved COLMAP fused cloud and visibility.
This is not a reconstruction benchmark or independent accuracy assessment.
Writes JSON to stdout; no mission artifacts are modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import time

import numpy as np

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / "reconstruction"))
from drishti_recon import mvs


def grouped_parallax(points, centres, views, chunk_size=2048):
    """Same maximum ray angle, batching equal-length valid tracks."""
    out = np.full(len(points), np.nan)
    groups = {}
    for row, indices in enumerate(views):
        ids = np.asarray(indices, int).ravel()
        ids = ids[(ids >= 0) & (ids < len(centres))]
        if len(ids) >= 2:
            groups.setdefault(len(ids), []).append((row, ids))
    for group in groups.values():
        for start in range(0, len(group), chunk_size):
            entries = group[start:start + chunk_size]
            rows = np.array([r for r, _ in entries], int)
            ids = np.stack([v for _, v in entries])
            rays = centres[ids] - points[rows, None, :]
            norms = np.linalg.norm(rays, axis=2)
            valid = norms > 1e-9
            unit = rays / np.where(valid, norms, 1.0)[..., None]
            dots = np.matmul(unit, unit.transpose(0, 2, 1))
            pairs = valid[:, :, None] & valid[:, None, :]
            dots = np.where(pairs, dots, 1.0)
            angles = np.degrees(np.arccos(np.clip(dots.min(axis=(1, 2)), -1, 1)))
            angles[valid.sum(axis=1) < 2] = np.nan
            out[rows] = angles
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=50000)
    args = parser.parse_args()
    if args.sample < 1:
        parser.error("--sample must be positive")
    import pycolmap
    dense = args.workspace / "dense"
    all_points, _ = mvs._read_ply(dense / "fused.ply")
    selection = np.linspace(0, len(all_points)-1,
                            min(args.sample, len(all_points)), dtype=int)
    points = all_points[selection].copy()
    total_points = len(all_points)
    del all_points
    views = []
    with (dense / "fused.ply.vis").open("rb") as stream:
        count = struct.unpack("<Q", stream.read(8))[0]
        assert count == total_points
        target = 0
        for index in range(count):
            k = struct.unpack("<I", stream.read(4))[0]
            if target < len(selection) and index == selection[target]:
                views.append(np.frombuffer(stream.read(4*k), dtype="<u4").astype(int))
                target += 1
            else:
                stream.seek(4*k, 1)
    rec = pycolmap.Reconstruction(str(dense / "sparse"))
    centres = np.array([rec.images[i].projection_center() for i in sorted(rec.images)])

    # Edge cases must preserve invalid-track and zero-ray semantics as well.
    edge_points = np.array([[0, 0, 0], [1, 0, 0], [2, 1, 0], [0, 0, 0]], float)
    edge_centres = np.array([[0, 0, 0], [0, 1, 0], [2, 2, 0]], float)
    edge_views = [[0, 1], [], [-1, 1, 2, 99], [0, 0]]
    np.testing.assert_allclose(
        grouped_parallax(edge_points, edge_centres, edge_views),
        mvs.contributing_parallax_deg(edge_points, edge_centres, edge_views),
        atol=1e-10, rtol=1e-10, equal_nan=True)

    timings = {"current": [], "grouped": []}
    outputs = {}
    for _ in range(3):
        for label, fn in [("current", mvs.contributing_parallax_deg),
                          ("grouped", grouped_parallax)]:
            started = time.perf_counter()
            outputs[label] = fn(points, centres, views)
            timings[label].append(time.perf_counter() - started)
    np.testing.assert_allclose(outputs["current"], outputs["grouped"],
                               atol=1e-10, rtol=1e-10, equal_nan=True)
    medians = {key: float(np.median(value)) for key, value in timings.items()}
    print(json.dumps({
        "kind": "CPU microbenchmark; not end-to-end or ground-truth accuracy",
        "workspace": str(args.workspace), "total_dense_points": total_points,
        "sampled_points": len(points), "sampling": "uniform indices over saved fused cloud",
        "median_track_length": float(np.median([len(v) for v in views])),
        "times_s": timings, "median_s": medians,
        "speedup": medians["current"] / medians["grouped"],
        "max_abs_difference_degrees": float(np.nanmax(np.abs(outputs["current"]-outputs["grouped"]))),
        "equivalence_tolerance": "atol=rtol=1e-10; NaN semantics checked",
        "production_code_changed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
