"""Render a reconstruction through a real frame's own recovered camera pose.

This is the comparison behind `docs/demo/`: rather than showing the cloud from
some arbitrary viewpoint, project it through the pose the pipeline solved for a
given frame and put it beside that frame. Anything that lines up did so because
the pose and geometry are right, which an arbitrary view cannot demonstrate.

Two sources are supported:

* a COLMAP model (``pov_colmap``) -- the *measured* layer, triangulated points
  only. It looks sparse, and that is the honest picture of measured geometry.
* a MASt3R dense pointmap set (``pov_dense``) -- the densified layer.

Both use a painter's-algorithm z-buffer (far points drawn first, near ones
overwrite), which is enough for point splatting and avoids a depth pass.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:                                    # pragma: no cover
    cv2 = None


def _tone(img, gamma=0.85, gain=1.1):
    f = img.astype(np.float32) / 255.0
    return np.clip((f ** gamma) * gain * 255, 0, 255).astype(np.uint8)


def _splat(ui, vi, col, W, H, splat):
    img = np.zeros((H, W, 3), np.uint8)
    for dy in range(-splat, splat + 1):
        for dx in range(-splat, splat + 1):
            if dx * dx + dy * dy > splat * splat:
                continue
            yy = np.clip(vi + dy, 0, H - 1)
            xx = np.clip(ui + dx, 0, W - 1)
            img[yy, xx] = col
    return img


def _project(Xc, fx, fy, cx, cy, sx, sy, W, H, col, splat):
    z = Xc[:, 2]
    fwd = z > 1e-6
    Xc, col, z = Xc[fwd], col[fwd], z[fwd]
    u = (fx * Xc[:, 0] / z + cx) * sx
    v = (fy * Xc[:, 1] / z + cy) * sy
    ui = np.round(u).astype(int)
    vi = np.round(v).astype(int)
    ok = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
    ui, vi, z, col = ui[ok], vi[ok], z[ok], col[ok]
    o = np.argsort(-z)                                # far first; near overwrite
    return _splat(ui[o], vi[o], col[o], W, H, splat)


def pov_colmap(rec, xyz, rgb, image, out_wh, splat=2):
    """Render a COLMAP reconstruction through one of its own images."""
    W, H = out_wh
    cam = rec.cameras[image.camera_id]
    sx, sy = W / cam.width, H / cam.height
    T = image.cam_from_world()
    Xc = (T.rotation.matrix() @ np.asarray(xyz).T).T + T.translation
    p = cam.params
    if cam.model.name.startswith(("PINHOLE", "OPENCV")):
        fx, fy, cx, cy = p[0], p[1], p[2], p[3]
    else:                                             # SIMPLE_* : one focal
        fx = fy = p[0]
        cx, cy = p[1], p[2]
    return _tone(_project(Xc, fx, fy, cx, cy, sx, sy, W, H,
                          np.asarray(rgb), splat), gamma=0.75, gain=1.25)


def pov_dense(pts, col, cam2w, focal, out_wh, proc_wh, splat=2,
              conf=None, conf_min=None):
    """Render a dense pointmap set through one recovered pose.

    ``cam2w`` is world-from-camera; ``focal`` and ``proc_wh`` are in the
    model's processed image space (MASt3R at ``size=512`` gives 512x288 for
    16:9 input), and the principal point is its centre.
    """
    W, H = out_wh
    pw, ph = proc_wh
    if conf is not None and conf_min is not None:
        k = np.asarray(conf) >= conf_min
        pts, col = np.asarray(pts)[k], np.asarray(col)[k]
    T = np.linalg.inv(np.asarray(cam2w, float))
    Xc = (T[:3, :3] @ np.asarray(pts).T).T + T[:3, 3]
    return _tone(_project(Xc, focal, focal, pw / 2, ph / 2,
                          W / pw, H / ph, W, H, np.asarray(col), splat))


def side_by_side(src_bgr, render_bgr, left="DRONE VIDEO", right="RECONSTRUCTED 3D",
                 left_sub="", right_sub="", bar=46, pad=8):
    """Stack a frame and its render into one labelled comparison image."""
    H, W = src_bgr.shape[:2]

    def _panel(img, title, sub):
        out = np.zeros((H + bar, W, 3), np.uint8)
        out[:] = (18, 15, 12)
        out[bar:] = img
        cv2.putText(out, title, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                    (235, 235, 235), 1, cv2.LINE_AA)
        if sub:
            cv2.putText(out, sub, (12, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (150, 190, 210), 1, cv2.LINE_AA)
        return out

    gap = np.full((H + bar, pad, 3), 40, np.uint8)
    return np.hstack([_panel(src_bgr, left, left_sub), gap,
                      _panel(render_bgr, right, right_sub)])
