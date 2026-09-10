# Demo assets

Generated from the real 63-second single drone pass over Gymnasium Neubiberg
(Wikimedia Commons, CC-BY-SA). Regenerate with `eval/render_pov.py` (`pov_dense` for the densified layer,
`pov_colmap` for the measured one) driven by `drishti_recon.dense3d`.

| File | What it shows |
|---|---|
| `drone_vs_3d.mp4` | Side by side: the drone video, and the reconstruction rendered **through that same frame's recovered camera pose**. 32 frames, 838,658 dense points. |
| `drone_vs_3d_stills.jpg` | Three frames from the above. |
| `measured_only_sparse.jpg` | The same viewpoints rendered from *measured* geometry alone (33,624 triangulated points). Deliberately included: this is what the honest layer looks like without densification, and why the two are kept separable. |
| `masking_roof_false_positive.jpg` | The failure that motivated D-035 — a school roof detected as a "train" at score 0.74, masking 48.7 % of the frame before matching. |

The interactive version carries both layers in one cloud, with the AI-densified
points toggleable against the triangulated ones.

**No GPS on this footage.** The reconstruction is correct in shape and
internally scaled, but carries no metres and no map position. Georeferenced
accuracy is measured separately on the AGZ surveyed dataset.
