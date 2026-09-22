"""Rebuild the lightweight homepage scene from the existing prototype PLYs.

Run from any directory. Each output record is XYZ float32 + RGB uint8 +
provenance uint8 (1 = triangulated, 0 = AI-assisted), all little endian.
The original geometry and RGB values are preserved; only rows are sampled.
"""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
out = root / 'public/showcase'
out.mkdir(exist_ok=True)
with (out / 'preview.bin').open('wb') as target:
    for filename, limit, provenance in [('dense.ply', 24000, 0), ('measured.ply', 8000, 1)]:
        data = (root / 'public/prototype' / filename).read_bytes()
        end = data.index(b'end_header\n') + len(b'end_header\n')
        header = data[:end].decode()
        assert 'format binary_little_endian 1.0' in header
        rows = int(header.split('element vertex ')[1].splitlines()[0])
        assert len(data) - end == rows * 15
        for i in range(0, rows, max(1, (rows + limit - 1) // limit)):
            target.write(data[end + i * 15:end + (i + 1) * 15] + bytes([provenance]))
shutil.copyfile(root.parent / 'docs/demo/drone_vs_3d_stills.jpg', out / 'comparison.jpg')
print(f'Wrote {out / "preview.bin"} ({(out / "preview.bin").stat().st_size:,} bytes)')
