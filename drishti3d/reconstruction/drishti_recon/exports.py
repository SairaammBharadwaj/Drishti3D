"""Exporters: PLY, LAS/LAZ, GLB/OBJ, GeoJSON, CSV, JSON, HTML report.

Optional dependencies degrade gracefully (LAS needs laspy; GLB needs Open3D).
All exporters keep coordinate frame and units explicit.
"""
from __future__ import annotations

from pathlib import Path
import json
import numpy as np

from .geo import ENUFrame
from .provenance import Provenance


def export_ply(path, cloud) -> str:
    """Binary PLY with RGB, confidence, provenance and per-point sigma.

    ``sigma`` is the worst-axis 1-sigma positional uncertainty in metres, the
    same quantity measurements use. It was previously computed, written into
    ``cloud.npz`` and then dropped from every advertised export, so a cloud
    opened anywhere else lost the one field that says how much to trust it.
    Points with no uncertainty are written as NaN rather than a plausible
    number.

    Binary little-endian, coordinates as doubles. This was ASCII written one
    Python line per point -- 2.7 M lines on DJI_1003 -- at four decimals; the
    binary form is one array write, keeps full precision, and is about half
    the size. Every mainstream reader (CloudCompare, MeshLab, Open3D, PDAL)
    takes either.
    """
    path = Path(path)
    pts, cols, conf, prov = cloud.points, cloud.colors, cloud.confidence, cloud.provenance
    sig = getattr(cloud, "sigma_major", None)
    if sig is None:
        sig = getattr(cloud, "sigma", None)
    n = len(pts)
    sig = np.full(n, np.nan) if sig is None else np.asarray(sig, float)
    rec = np.empty(n, dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
                             ("red", "u1"), ("green", "u1"), ("blue", "u1"),
                             ("confidence", "<f4"), ("provenance", "u1"),
                             ("sigma", "<f4")])
    P = np.asarray(pts, float).reshape(-1, 3)
    C = np.asarray(cols).reshape(-1, 3)
    rec["x"], rec["y"], rec["z"] = P[:, 0], P[:, 1], P[:, 2]
    rec["red"], rec["green"], rec["blue"] = C[:, 0], C[:, 1], C[:, 2]
    rec["confidence"] = np.asarray(conf, float)
    rec["provenance"] = np.asarray(prov).astype(np.uint8)
    rec["sigma"] = sig
    header = ("ply\nformat binary_little_endian 1.0\n"
              "comment coordinates are local ENU metres; see the "
              "georeference sidecar for the origin and CRS\n"
              "comment sigma is worst-axis 1-sigma metres, uncalibrated\n"
              f"element vertex {n}\n"
              "property double x\nproperty double y\nproperty double z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "property float confidence\nproperty uchar provenance\n"
              "property float sigma\n"
              "end_header\n")
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(rec.tobytes())
    return str(path)


def utm_epsg(lat: float, lon: float) -> int:
    """EPSG code of the WGS84 UTM zone containing a geodetic position."""
    zone = int((float(lon) + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if float(lat) >= 0 else 32700) + zone


def enu_to_utm(frame: ENUFrame, points) -> tuple[np.ndarray, int]:
    """Project local ENU metres into the WGS84 UTM zone of the frame origin.

    Returns ``(points_utm, epsg)``. The third column is **ellipsoidal height**
    (WGS84), because that is what the ENU up axis is measured against; it is
    not an orthometric elevation and must not be read as one.
    """
    import pyproj
    pts = np.asarray(points, float).reshape(-1, 3)
    geo = frame.enu_to_geodetic(pts)                  # (lat, lon, alt)
    epsg = utm_epsg(frame.lat0, frame.lon0)
    tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = tr.transform(geo[:, 1], geo[:, 0])
    return np.column_stack([x, y, geo[:, 2]]), epsg


def export_las(path, cloud, frame: ENUFrame | None = None, *,
               classification=None) -> str:
    """LAS point cloud (requires laspy), georeferenced when a frame is given.

    ``frame`` used to be accepted and ignored: the file held local ENU metres
    with no CRS at all, so ``header.parse_crs()`` returned ``None`` and an
    analyst opening it in GIS had to be told the origin out of band, or guess.
    Provenance and uncertainty were dropped entirely, while the overview said
    exported clouds carried sigma.

    With a frame, points are projected into the WGS84 UTM zone of the frame
    origin and that CRS is written into the header. Without one, the file stays
    in local metres and says so -- an unreferenced local file is a legitimate
    output, silently unreferenced is not.

    Per-point ``provenance``, ``confidence`` and ``sigma`` (worst-axis, metres)
    are written as LAS extra dimensions under those names, so the trust
    information survives the trip into another tool.

    ``classification``, when given, is one ASPRS code per point
    (``rasters.classify_points``: 1 unclassified, 2 ground, 5 high
    vegetation, 6 building). Without it every point stays 0, "never
    classified", which is what the file says rather than a guess.
    """
    import laspy
    path = Path(path)

    pts = np.asarray(cloud.points, float)
    epsg = None
    if frame is not None:
        pts, epsg = enu_to_utm(frame, pts)

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.offsets = pts.min(0)
    header.scales = np.array([0.001, 0.001, 0.001])
    header.add_extra_dims([
        laspy.ExtraBytesParams(name="provenance", type=np.uint8),
        laspy.ExtraBytesParams(name="confidence", type=np.float32),
        laspy.ExtraBytesParams(name="sigma", type=np.float32),
    ])
    if epsg is not None:
        import pyproj
        header.add_crs(pyproj.CRS.from_epsg(epsg))

    las = laspy.LasData(header)
    las.x, las.y, las.z = pts[:, 0], pts[:, 1], pts[:, 2]
    las.red = (cloud.colors[:, 0].astype(np.uint16)) * 257
    las.green = (cloud.colors[:, 1].astype(np.uint16)) * 257
    las.blue = (cloud.colors[:, 2].astype(np.uint16)) * 257
    las.intensity = (np.asarray(cloud.confidence, float) * 65535).astype(np.uint16)
    las.provenance = np.asarray(cloud.provenance, np.uint8)
    las.confidence = np.asarray(cloud.confidence, np.float32)
    # sigma_major, not sigma: measurements use the worst-constrained axis, and
    # an export that reported the optimistic one would disagree with them.
    sig = getattr(cloud, "sigma_major", None)
    if sig is None:
        sig = getattr(cloud, "sigma", None)
    las.sigma = (np.full(len(pts), np.nan, np.float32) if sig is None
                 else np.asarray(sig, np.float32))
    if classification is not None:
        las.classification = np.asarray(classification, np.uint8)
    las.write(str(path))
    return str(path)


def export_georeference_sidecar(path, cloud, frame: ENUFrame | None,
                                *, extra: dict | None = None) -> str:
    """JSON describing how to place a local-coordinate export on the earth.

    Written beside every cloud export so a local file is still usable: it
    carries the ENU origin, the projected CRS the georeferenced exports use,
    the vertical reference, and the field meanings that LAS extra dimensions
    and PLY scalars abbreviate.
    """
    path = Path(path)
    doc = {
        "coordinate_frame": "local ENU metres" if frame is None else "local ENU metres, with a georeferenced twin",
        "units": "metres",
        "local_origin_wgs84": None if frame is None else {
            "lat": frame.lat0, "lon": frame.lon0, "alt_ellipsoidal_m": frame.alt0},
        "projected_crs": None if frame is None else f"EPSG:{utm_epsg(frame.lat0, frame.lon0)}",
        "vertical_reference": (
            "WGS84 ellipsoidal height; NOT an orthometric/MSL elevation"),
        "fields": {
            "provenance": "Provenance enum: "
                          + ", ".join(f"{int(p)}={p.name}" for p in Provenance),
            "confidence": "0-1 fusion confidence, not a probability of correctness",
            "sigma": "worst-axis 1-sigma positional uncertainty, metres; "
                     "NaN where the reconstruction carried none",
        },
        "caveat": (
            "Uncertainty here is the propagated geometric estimate. It is not "
            "a calibrated interval: no validated calibration profile has been "
            "fitted for this capture."),
    }
    if extra:
        doc.update(extra)
    path.write_text(json.dumps(doc, indent=2))
    return str(path)


def export_glb(path, verts, faces, colors) -> str:
    """GLB/OBJ mesh export via Open3D."""
    import open3d as o3d
    path = Path(path)
    m = o3d.geometry.TriangleMesh()
    m.vertices = o3d.utility.Vector3dVector(np.asarray(verts, float))
    m.triangles = o3d.utility.Vector3iVector(np.asarray(faces, np.int32))
    if colors is not None:
        m.vertex_colors = o3d.utility.Vector3dVector(np.asarray(colors, float) / 255.0)
    m.compute_vertex_normals()
    ok = o3d.io.write_triangle_mesh(str(path), m)
    if not ok:
        raise RuntimeError(f"failed to write mesh {path}")
    return str(path)


def export_trajectory_csv(path, cameras_enu) -> str:
    """cameras_enu: list of dict {frame_index, C:[e,n,u]}."""
    path = Path(path)
    with open(path, "w") as f:
        f.write("frame_index,east_m,north_m,up_m\n")
        for c in cameras_enu:
            e, n, u = c["C"]
            f.write(f"{c['frame_index']},{e:.4f},{n:.4f},{u:.4f}\n")
    return str(path)


def export_geojson(path, cameras_enu, frame: ENUFrame, measurements=None) -> str:
    """Trajectory (+ optional measurements) as WGS84 GeoJSON."""
    path = Path(path)
    coords_enu = np.array([c["C"] for c in cameras_enu])
    geo = frame.enu_to_geodetic(coords_enu)  # (N,3) lat,lon,alt
    features = [{
        "type": "Feature",
        "properties": {"name": "uav_trajectory"},
        "geometry": {"type": "LineString",
                     "coordinates": [[float(lo), float(la), float(al)]
                                     for la, lo, al in geo]},
    }]
    for m in (measurements or []):
        enu = np.array(m.get("points_enu", []))
        if len(enu) == 0:
            continue
        g = frame.enu_to_geodetic(enu)
        features.append({
            "type": "Feature",
            "properties": {"kind": m.get("kind"), "value": m.get("value"),
                           "unit": m.get("unit")},
            "geometry": {"type": "LineString" if len(g) > 1 else "Point",
                         "coordinates": ([[float(lo), float(la), float(al)]
                                          for la, lo, al in g]
                                         if len(g) > 1
                                         else [float(g[0][1]), float(g[0][0]),
                                               float(g[0][2])])},
        })
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, indent=2))
    return str(path)


def export_report_json(path, report: dict) -> str:
    path = Path(path)
    path.write_text(json.dumps(report, indent=2))
    return str(path)


def export_report_html(path, report: dict) -> str:
    """Printable HTML evidence report (self-contained, no external assets)."""
    path = Path(path)
    r = report
    cloud = r.get("cloud", {})
    frames = r.get("frames", {})
    align = r.get("alignment") or {}
    perf = r.get("performance", {})
    gte = r.get("ground_truth_evaluation")
    # Every section is read defensively. This is the last stage of artifact
    # writing, so a KeyError here aborts the run *after* the cloud, PLY and LAS
    # are on disk -- leaving a partial artifact set that looks complete. A
    # missing section should render as "not available", which is also the
    # honest thing to show.
    inp = r.get("input") or {}
    video = inp.get("video") or {}
    telem = inp.get("telemetry") or {}
    recon = r.get("reconstruction") or {}

    def num(v, spec=""):
        if v is None:
            return "not available"
        try:
            return format(float(v), spec) if spec else v
        except (TypeError, ValueError):
            return v

    def text(v):
        return "not available" if v is None else v

    def row(k, v):
        return f"<tr><th>{k}</th><td>{v}</td></tr>"

    dim_rows = ""
    if gte and gte.get("dimensional_accuracy"):
        dim_rows = "".join(
            f"<tr><td>{d['name']}</td><td>{d['truth_m']:.3f}</td>"
            f"<td>{'' if d['measured_m'] is None else format(d['measured_m'],'.3f')}</td>"
            f"<td>{'' if d['pct_error'] is None else format(d['pct_error'],'.2f')+'%'}</td></tr>"
            for d in gte["dimensional_accuracy"])
    warn_html = "".join(f"<li>{w}</li>" for w in r.get("warnings", []))
    lim_html = "".join(f"<li>{w}</li>" for w in r.get("limitations", []))
    classes = cloud.get("class_fractions", {})
    class_html = "".join(
        f"<tr><td>{k}</td><td>{v*100:.1f}%</td></tr>" for k, v in classes.items())

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Drishti3D Evidence Report</title>
<style>
body{{font-family:system-ui,Segoe UI,sans-serif;margin:2rem;color:#111;background:#fff}}
h1{{border-bottom:3px solid #2c3e50}} h2{{margin-top:1.6rem;color:#2c3e50}}
table{{border-collapse:collapse;margin:.5rem 0;width:100%;max-width:720px}}
th,td{{border:1px solid #ccc;padding:.35rem .6rem;text-align:left;font-size:14px}}
th{{background:#f4f6f8;width:40%}} .warn{{color:#b8860b}} code{{background:#f4f4f4}}
</style></head><body>
<h1>Drishti3D — Reconstruction Evidence Report</h1>
<p>Single-pass drone video to georeferenced 3D. Scale source:
<b>{text(inp.get('scale_source'))}</b></p>

<h2>Input</h2><table>
{row('Video duration (s)', num(video.get('duration'), '.2f'))}
{row('Resolution', f"{text(video.get('width'))}x{text(video.get('height'))}")}
{row('FPS', num(video.get('fps'), '.2f'))}
{row('Video SHA-256', '<code>' + (video.get('sha256') or 'not available')[:16] + '…</code>')}
{row('Telemetry valid samples', text(telem.get('n_valid')))}
{row('RTK present', text(telem.get('has_rtk')))}
</table>

<h2>Frames</h2><table>
{row('Analyzed', frames.get('total_analyzed'))}
{row('Accepted', frames.get('accepted'))}
{row('Rejected', frames.get('rejected'))}
{row('Keyframes', frames.get('keyframes'))}
</table>

<h2>Reconstruction</h2><table>
{row('Registered keyframes', f"{text(recon.get('n_registered'))}/{text(recon.get('n_keyframes'))}")}
{row('Points', text(cloud.get('n_points')))}
{row('Median reprojection error (px)', text(recon.get('median_reproj_err')))}
{row('Mean track length', text(recon.get('mean_track_length')))}
{row('Mean triangulation angle (deg)', text(recon.get('mean_tri_angle')))}
{row('Model dimensions (m)', cloud.get('dimensions_m'))}
{row('Median point spacing (m)', cloud.get('median_point_spacing_m'))}
</table>

<h2>Provenance distribution</h2><table><tr><th>Class</th><th>Share</th></tr>{class_html}</table>

<h2>GPS Alignment</h2><table>
{row('Scale', align.get('scale'))}
{row('Inliers', f"{align.get('n_inliers')}/{align.get('n_total')}")}
{row('Horizontal RMSE (m)', align.get('alignment_rmse_horizontal_m'))}
{row('Vertical RMSE (m)', align.get('alignment_rmse_vertical_m'))}
</table>
<p class="warn">{align.get('note','')}</p>

{'<h2>Independent accuracy (ground truth)</h2><table><tr><th>Reference</th><th>Truth (m)</th><th>Measured (m)</th><th>Error</th></tr>'+dim_rows+'</table>' if dim_rows else ''}

<h2>Performance</h2><table>
{row('Processing time (s)', f"{perf.get('processing_time_s',0):.1f}")}
{row('Processing / video ratio', f"{perf.get('processing_to_video_ratio')}")}
</table>

<h2>Warnings</h2><ul>{warn_html or '<li>None</li>'}</ul>
<h2>Known limitations</h2><ul>{lim_html}</ul>
<hr><p style="font-size:12px;color:#888">Generated by Drishti3D. Not an official
NTRO product. Accuracy figures reflect this run's inputs only.</p>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return str(path)
