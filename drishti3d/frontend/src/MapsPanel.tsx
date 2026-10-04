import { useState } from 'react'
import { api, type RasterInfo } from './api'

// What each layer is, and -- for the two that have not been validated -- what
// it gets wrong. The wording follows docs/RASTERS.md; change both together.
const LAYERS: { key: string; label: string; caption: string; experimental?: boolean }[] = [
  { key: 'ortho', label: 'Orthophoto', caption: 'Colour of the highest observed point in each cell. Built from the point cloud, not projected from the camera images.' },
  { key: 'dsm', label: 'Surface', caption: 'DSM: the highest observed point in each cell. Checked against same-flight LiDAR on three missions, it stays within 3 cm of the cloud’s own accuracy.' },
  { key: 'dtm', label: 'Terrain', caption: 'DTM: bare earth where the ground filter finds it, empty under buildings and trees. Large roofs can pass as ground.', experimental: true },
  { key: 'landcover', label: 'Land cover', caption: 'Rule-based classes. Dependable for ordinary buildings on open ground; large roofs can read as ground and steep rock as building.', experimental: true },
]

const LEGEND: [string, string][] = [
  ['Ground', 'rgb(196,164,112)'], ['Building', 'rgb(200,70,60)'],
  ['Vegetation', 'rgb(46,139,87)'], ['Unclassified', 'rgb(160,160,160)'],
]

export default function MapsPanel({ id, maps }: { id: string; maps: RasterInfo }) {
  const available = LAYERS.filter((l) => maps.previews.includes(l.key))
  const [active, setActive] = useState(available[0]?.key ?? 'ortho')
  const layer = available.find((l) => l.key === active) ?? available[0]
  if (!layer) return <div className="muted">No map previews for this mission.</div>
  const s = maps.summary
  const url = api.rasterPreviewUrl(id, layer.key)
  return (
    <div className="maps">
      <div className="row maps-tabs" role="tablist" aria-label="Map layer">
        {available.map((l) => (
          <button key={l.key} role="tab" aria-selected={l.key === layer.key}
            className={l.key === layer.key ? 'active' : ''} onClick={() => setActive(l.key)}>
            {l.label}
          </button>
        ))}
      </div>
      <a href={url} target="_blank" rel="noreferrer" title="Open full size">
        <img src={url} alt={`${layer.label} map of this mission`} />
      </a>
      <p className="maps-caption">
        {layer.experimental && <span className="maps-flag">Experimental</span>} {layer.caption}
      </p>
      {layer.key === 'landcover' && (
        <div className="maps-legend">
          {LEGEND.map(([name, colour]) => (
            <span key={name}><i style={{ background: colour }} />{name}</span>
          ))}
        </div>
      )}
      <p className="muted maps-meta">
        {s.cell_size_m} m cells
        {s.footprint_coverage != null && ` · ${Math.round(s.footprint_coverage * 100)}% of the footprint measured`}
        {` · ${s.crs} · heights: ${s.vertical_reference} · empty cells are left empty`}
      </p>
    </div>
  )
}
