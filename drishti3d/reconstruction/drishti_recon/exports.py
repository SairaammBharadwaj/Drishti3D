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
    """ASCII PLY with RGB and a confidence + provenance scalar per point."""
    path = Path(path)
    pts, cols, conf, prov = cloud.points, cloud.colors, cloud.confidence, cloud.provenance
    n = len(pts)
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {n}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("property float confidence\nproperty uchar provenance\n")
        f.write("end_header\n")
        for i in range(n):
            x, y, z = pts[i]
            r, g, b = cols[i]
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)} "
                    f"{conf[i]:.4f} {int(prov[i])}\n")
    return str(path)


def export_las(path, cloud, frame: ENUFrame | None = None) -> str:
    """LAS point cloud (requires laspy). Stores confidence in intensity."""
    import laspy
    path = Path(path)
    pts = cloud.points.astype(np.float64)
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.offsets = pts.min(0)
    header.scales = np.array([0.001, 0.001, 0.001])
    las = laspy.LasData(header)
    las.x, las.y, las.z = pts[:, 0], pts[:, 1], pts[:, 2]
    las.red = (cloud.colors[:, 0].astype(np.uint16)) * 257
    las.green = (cloud.colors[:, 1].astype(np.uint16)) * 257
    las.blue = (cloud.colors[:, 2].astype(np.uint16)) * 257
    las.intensity = (cloud.confidence * 65535).astype(np.uint16)
    las.write(str(path))
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
<b>{r.get('input',{}).get('scale_source','?')}</b></p>

<h2>Input</h2><table>
{row('Video duration (s)', f"{r['input']['video']['duration']:.2f}")}
{row('Resolution', f"{r['input']['video']['width']}x{r['input']['video']['height']}")}
{row('FPS', f"{r['input']['video']['fps']:.2f}")}
{row('Video SHA-256', '<code>'+r['input']['video']['sha256'][:16]+'…</code>')}
{row('Telemetry valid samples', r['input']['telemetry']['n_valid'])}
{row('RTK present', r['input']['telemetry']['has_rtk'])}
</table>

<h2>Frames</h2><table>
{row('Analyzed', frames.get('total_analyzed'))}
{row('Accepted', frames.get('accepted'))}
{row('Rejected', frames.get('rejected'))}
{row('Keyframes', frames.get('keyframes'))}
</table>

<h2>Reconstruction</h2><table>
{row('Registered keyframes', f"{r['reconstruction'].get('n_registered')}/{r['reconstruction'].get('n_keyframes')}")}
{row('Points', cloud.get('n_points'))}
{row('Median reprojection error (px)', r['reconstruction'].get('median_reproj_err'))}
{row('Mean track length', r['reconstruction'].get('mean_track_length'))}
{row('Mean triangulation angle (deg)', r['reconstruction'].get('mean_tri_angle'))}
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
