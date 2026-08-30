# Drishti3D Frontend

React + TypeScript + Vite operational UI for the Drishti3D reconstruction backend.
Runs fully offline (no external map tiles or CDNs). The 3D viewer uses Three.js;
the trajectory map is a self-drawn SVG.

## Prerequisites
- Node 18+ (tested on Node 24)
- The Drishti3D backend running on `http://127.0.0.1:8000`

## Development
```bash
npm install
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
```

## Production build
```bash
npm run build      # type-checks then emits ./dist
```
The FastAPI backend serves `dist/` at `/` automatically when it exists
(`DRISHTI_FRONTEND_DIST` overrides the path).

## Configuration
- `VITE_API_BASE` — optional API base URL prefix (default `''`, i.e. same origin / dev proxy).

## Views
- `/` Mission dashboard (+ live capability probe)
- `/new` Reconstruction wizard (upload video + telemetry, options)
- `/projects/:id/monitor?job=…` Processing monitor (SSE progress)
- `/projects/:id` Analysis workspace (3D viewer, provenance layers, measurement, exports)
- `/projects/:id/report` Evidence report
