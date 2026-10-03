# Raster products: DSM, DTM, orthophoto, sigma, land cover

Every georeferenced mission now produces map layers as GeoTIFFs in its UTM
zone, beside the point cloud (`drishti_recon/rasters.py`, DEC-045). They follow
the cloud's rules: only observed points go in, and a cell nothing was measured
in stays empty. Older missions get them with
`scripts/build_rasters.py --all`, without reprocessing.

| File | What it is | Status |
|---|---|---|
| `dsm.tif` | Surface: the highest observed point in each cell | **Validated** (below) |
| `ortho.tif` | Colour of that point; empty cells masked. From the cloud, not projected from the images | Visual check |
| `sigma.tif` | Mean worst-axis 1-sigma of the cell's points, uncalibrated like the cloud's | Derived |
| `dtm.tif` | Bare earth: the lowest point in cells a ground filter keeps; empty under buildings and trees | **Experimental** |
| `landcover.tif` | ASPRS classes: 1 unclassified, 2 ground, 5 high vegetation, 6 building | **Experimental** |

Heights are WGS84 ellipsoidal, as in the LAS export. They are not heights above
sea level. The LAS export now carries the same classes per point.

## Cell size

The smallest cell size, from 0.1 m to 2 m, at which at least 75% of the
surveyed footprint holds an observed point. A grid finer than the points is
mostly holes. The point spacing alone does not settle it: nearest-neighbour
spacing (5–27 cm) is set by dense textured patches, while points per area
(0.27–0.83 m) is diluted by empty space.

| Mission | Cell | Footprint with a point |
|---|---:|---:|
| UseGeo 1 | 0.25 m | 77% |
| HKisland02 | 0.35 m | 76% |
| HKisland03 | 0.5 m | 76% |
| DJI_1001 | 1.0 m | 79% |
| DJI_1003 | 1.5 m | 79% |
| AGZ dense | 2.0 m | 68% (facades from street level; never reaches 75%) |

## DSM accuracy

`scripts/score_raster_dsm.py` scores each DSM cell, as one point at its centre,
with the validated flat-cell vertical metric (`score_vertical_dsm.py`). The
cloud's own points are scored the same way for comparison. The antenna offsets
are DEC-044's, each calibrated on the other flight. Injected shifts of +0.30 /
+1.00 / -0.10 m were recovered within 0.3 mm on every DSM.

| Mission | Cloud RMSE | DSM RMSE | DSM bias | Cell |
|---|---:|---:|---:|---:|
| HKisland03 | 0.377 m | 0.407 m | +0.055 m | 0.5 m |
| HKisland02 | 0.418 m | 0.416 m | -0.026 m | 0.35 m |
| UseGeo 1 | 0.432 m | 0.444 m | +0.370 m | 0.25 m |

The cloud figures for both Hong Kong flights reproduce DEC-044 exactly, which
confirms the missions and metric are the published ones. **Rasterising costs at
most 3 cm.** UseGeo 1 has a +0.36 m vertical bias on flat ground under this
metric. It had not been measured this way before; DEC-038's 0.32 m was a
cloud-to-cloud figure, and the C2C metric is blind to vertical shifts
(DEC-042).

## Ground model and land cover: experimental

No reference LiDAR available to the project is classified (MARS-LVIG: all
class 0; UseGeo: unclassified plus some vegetation). The building class is
scored against OpenStreetMap footprints with `scripts/score_landcover_osm.py`.
That is an external reference, not survey truth: outlines can be off by metres,
and the scorer allows 1.5 m. Settings were tuned on DJI_1003 and checked on the
other missions.

| Mission | Precision | Recall | F1 | Roofs kept as ground |
|---|---:|---:|---:|---:|
| UseGeo 1 | 0.77 | 0.86 | **0.81** | 2% |
| DJI_1003 | 0.30 | 0.11 | 0.16 | 52% |
| DJI_1001 | 0.38 | 0.13 | 0.19 | 41% |
| HKisland03 | 0.14 | 0.95 | 0.25 | 0% |
| HKisland02 | 0.25 | 0.93 | 0.39 | 0% |

What goes wrong:

- **Large roofs pass as ground.** The ground filter (Zhang et al. 2003) needs a
  window wider than the widest roof; downtown Austin's exceed its 40 m.
- **Steep rock reads as building.** On the Hong Kong coast, the filter rejects
  cliffs as non-ground, and rock is neither green nor rough enough to be called
  vegetation. The low precision there is cliffs.
- A 120 m window was tried. It helped DJI_1003 (F1 0.16 to 0.24) and DJI_1001
  slightly (0.19 to 0.21), but multiplied false buildings on the cliffs
  (HKisland02 precision 0.25 to 0.06). **Rejected; the default stays 40 m.**
- The Austin scores are also confounded by placement, below.

## Austin placement is unverified

Correlating cells more than 5 m above their surroundings with OSM footprints
puts UseGeo exactly on OSM (0.0 m, a sharp peak): the method works. For the
Austin missions (GPS only, no RTK), the best offset differs by quadrant, from 0 m
to about 45 m (DJI_1001: 12–40 m south in every quadrant; DJI_1003: 0 m
downtown, larger in the south-east). That is not a clean shift, and the
indicator mixes trees with buildings. Austin's absolute placement should be
treated as unverified until a dedicated check. The planned one uses StratMap
2021 LiDAR for horizontal placement on unchanged buildings only.
