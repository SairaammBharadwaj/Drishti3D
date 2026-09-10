"""AGZ surveyed-truth evaluation of the dense (MASt3R) + pose-graph path.

Reproduces the Intelligence Edition stage 3+4 result recorded in BENCHMARK.md.
Requires: data/real_drone/agz_undist (undistorted via the factory calibration
-- raw AGZ frames carry k1=-0.281 and feeding them to the dense model breaks
its geometry: 90 m median error distorted vs 7.6 m undistorted), the MASt3R
checkpoint under models/, and the ground-truth pick file passed as argv[1]
directory (agz_pick.npy).
"""
import sys, time, json, numpy as np
sys.path.insert(0, "/home/naveen/Drishti3D/drishti3d/reconstruction")
from drishti_recon import dense3d, pose_graph as pg
from drishti_recon.geo import robust_sim3

SP = sys.argv[1]  # directory holding agz_pick.npy; outputs land beside it
SRC = "/home/naveen/Drishti3D/drishti3d/data/real_drone/agz_undist"
GT = np.load(f"{SP}/agz_pick.npy")
gmap = {int(r[0]): r for r in GT}

t0 = time.time()
edges, names, diag = dense3d.pairwise_edges_dir(SRC, allow_noncommercial=True)
t_pairs = time.time() - t0
ids = [int(x.split(".")[0]) for x in names]
tru = np.array([gmap[i][1:4] for i in ids]); gps = np.array([gmap[i][7:10] for i in ids])
off = gps.mean(0); tru_c, gps_c = tru - off, gps - off
res_arr = np.array([d["resid"] for d in diag])
print(f"{len(edges)} edges in {t_pairs:.0f}s | procrustes resid med {np.median(res_arr):.3f} p90 {np.percentile(res_arr,90):.3f}", flush=True)

n = len(names)
# chain init from sequential edges, then Sim3 onto GPS
Rs_c, cs_c = pg.chain_initialization(edges, n)
step = np.linalg.norm(np.diff(cs_c, axis=0), axis=1)
print(f"chain: step med {np.median(step):.2f} m  max/med {step.max()/max(np.median(step),1e-9):.1f}", flush=True)
fit = robust_sim3(cs_c, gps_c)
m_ = fit.transform
print(f"Sim3: scale {m_.scale:.3f} inliers {fit.n_inliers}/{fit.n_total} rmse {fit.rmse:.2f}", flush=True)
cs0 = (m_.scale * (m_.R @ cs_c.T)).T + m_.t
Rs0 = np.einsum("ab,nbc->nac", m_.R, Rs_c)
# rescale edge translations into geo scale
for e in edges:
    e.t_ij = e.t_ij * m_.scale

def score(est, label):
    d = est - tru_c
    e3 = np.linalg.norm(d, axis=1); eh = np.linalg.norm(d[:, :2], axis=1); ev = np.abs(d[:, 2])
    print(f"  {label:24s} 3D med {np.median(e3):6.2f} p90 {np.percentile(e3,90):6.2f} | horiz {np.median(eh):5.2f} | vert {np.median(ev):5.2f}", flush=True)
    return dict(med3=float(np.median(e3)), p90=float(np.percentile(e3,90)),
                horiz=float(np.median(eh)), vert=float(np.median(ev)), max3=float(e3.max()))

print("direct UTM error vs surveyed truth:", flush=True)
out = {"gps": score(gps_c, "onboard GPS"),
       "chain_sim3": score(cs0, "dense chain + Sim3")}

g = pg.PoseGraph(n); g.edges = edges
for k in range(n):
    g.add_prior(k, gps_c[k], 5.5)
t0 = time.time()
# edge noise from cycle consistency — no truth, no GPS involved
cc = pg.cycle_consistency(edges)
step_m = float(np.median(np.linalg.norm(np.diff(cs0, axis=0), axis=1)))
ts = max(0.05, cc["rel_trans_err"] * step_m)
rs = max(0.002, cc["rot_err_rad"])
print(f"cycles: {cc['n_cycles']} rel_trans {cc['rel_trans_err']:.3f} rot {np.degrees(cc['rot_err_rad']):.2f} deg -> trans_sigma {ts:.2f} m rot_sigma {rs:.4f}", flush=True)
# per-edge anisotropic sigmas, both scaled by edge length:
#   parallel  (magnitude): rel_trans_err * L
#   perpendicular (direction): rot_err_rad * L
Ls = np.array([np.linalg.norm(e.t_ij) for e in edges])
sig_par = np.maximum(0.05, cc["rel_trans_err"] * Ls)
sig_perp = np.maximum(0.05, cc["rot_err_rad"] * Ls)
Rs_o, cs_o, info = pg.optimize(g, Rs0, cs0, rot_sigma_rad=rs,
                               trans_sigma_m=sig_perp, trans_sigma_par_m=sig_par)
print(f"aniso per-edge: par med {np.median(sig_par):.2f} perp med {np.median(sig_perp):.2f}", flush=True)
print(f"PGO {time.time()-t0:.1f}s", flush=True)
out["dense_pgo"] = score(cs_o, "dense pairs + PGO(GPS)")
json.dump(out, open(f"{SP}/dense_pgo_result.json", "w"), indent=2)
np.savez(f"{SP}/dense_pgo_poses.npz", cs0=cs0, cs_o=cs_o, tru=tru_c, gps=gps_c)
