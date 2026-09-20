"""Package the saved Gymnasium prototype geometry for the web viewer.

Usage: .venv/bin/python scripts/prepare_prototype.py /path/to/experiment
The experiment must contain gym_dense.npz, gym_dense_aligned.npz, gym_measured.npz.
"""
from pathlib import Path
import json
import shutil
import sys
import numpy as np

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
out = root / 'frontend/public/prototype'
out.mkdir(parents=True, exist_ok=True)
dense = np.load(source / 'gym_dense.npz')
aligned = np.load(source / 'gym_dense_aligned.npz')
measured = np.load(source / 'gym_measured.npz')
# The saved aligned dense cloud establishes the mapping to the measured frame.
# Invert it so both layers use the exact original prototype camera coordinates.
x = np.c_[dense['pts'][::100], np.ones(len(dense['pts'][::100]))]
transform = np.linalg.lstsq(x, aligned['pts'][::100], rcond=None)[0]
measured_pts = (measured['pts'] - transform[3]) @ np.linalg.inv(transform[:3])

def ply(name, points, colors):
    if not np.isfinite(points).all():
        raise ValueError('Non-finite geometry')
    data = np.empty(len(points), dtype=[('x', '<f4'), ('y', '<f4'), ('z', '<f4'),
                                       ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')])
    for i, k in enumerate(('x', 'y', 'z')):
        data[k] = points[:, i]
    for i, k in enumerate(('red', 'green', 'blue')):
        data[k] = colors[:, i]
    header = (f'ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n'
              'property float x\nproperty float y\nproperty float z\n'
              'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
    with (out / name).open('wb') as f:
        f.write(header.encode()); f.write(data.tobytes())

ply('dense.ply', dense['pts'], dense['col'])
ply('measured.ply', measured_pts, measured['col'])
metadata = dict(title='Gymnasium · original dense prototype',
                dense_points=len(dense['pts']), measured_points=len(measured_pts),
                camera_count=len(dense['cam2w']),
                bounds=np.percentile(dense['pts'], [1, 99], axis=0).tolist(),
                cameras=dense['cam2w'].tolist(), focals=dense['focals'].tolist(),
                image_names=dense['names'].tolist(),
                scale='relative',
                source_files=['gym_dense.npz', 'gym_dense_aligned.npz', 'gym_measured.npz'],
                alignment_residual=float(np.max(np.abs(x @ transform - aligned['pts'][::100]))))
(out / 'scene.json').write_text(json.dumps(metadata))
shutil.copy2(root / 'data/demo/drone_vs_3d_full.mp4', out / 'reference.mp4')
print(json.dumps({k:metadata[k] for k in ['dense_points','measured_points','camera_count','alignment_residual']}))
