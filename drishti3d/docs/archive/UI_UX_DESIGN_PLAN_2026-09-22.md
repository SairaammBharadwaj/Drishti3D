# Drishti3D — UI/UX direction and implementation handoff

Date: 22 September 2026

Direction: **A spatial analysis studio that turns visual curiosity into inspectable evidence.**

Implemented previews: [desktop overview](ui-ux/home-desktop.png), [phone overview](ui-ux/home-mobile.png), [workflow and evidence](ui-ux/home-workflow.png), [mission library](ui-ux/library-desktop.png), and [setup](ui-ux/setup-desktop.png). Mission names in these screenshots are isolated browser fixtures.

## 1. The experience we want

Within ten seconds, a visitor should understand that Drishti3D takes a drone video, reconstructs a scene, and helps a person inspect and measure it. Within a minute, they should understand the differentiator: the interface shows where geometry and measurement support come from, including what remains uncertain.

The site needs two distinct rhythms. The introduction can be spacious, expressive, and memorable. The working application must be compact, predictable, and precise. They share typography, colours, navigation, and language, but a measurement panel must never behave like a promotional landing page.

For a technical competition, the strongest impression is an attractive interface that leads naturally into real evidence. Decorative accuracy numbers, invented mission activity, endorsements, fake processing, and universal performance claims would weaken that impression.

### Primary audiences

| Visitor | Main question | Best path |
| --- | --- | --- |
| First-time visitor or judge | What does this do, and why is it interesting? | Overview → workflow → saved example → interactive scene |
| Presenter | How do I explain the result without losing the audience? | Showcase → source footage → saved result → evidence |
| Operator | How do I process my capture and find a result again? | Mission library → setup → processing → analysis |
| Technical reviewer | What supports this measurement? | Analysis → Tolerance Lens → evidence → quality report |

## 2. What has been implemented

This document accompanies a working first implementation. Items in this section exist in the frontend; later roadmap sections describe further work.

| Surface | Implemented change |
| --- | --- |
| Application shell | Geometric brand mark, clearer navigation, responsive menu, skip link, visible focus styles, shared dark/lime visual system |
| `/` — Overview | New introduction, actual sampled reconstruction, appearance/evidence controls, workflow explanation, provenance concept diagram, recorded example, and project creation calls to action |
| `/missions` — Mission library | Live project counts, search, status filters, meaningful empty/error/loading states, explicit card actions, real capability disclosure, and refresh while projects are processing |
| `/new` — Setup | Numbered sidebar, clearer upload presentation, labelled fields, busy state, optional telemetry explanation, and resumable drafts via `?project=<id>` |
| Analysis workspace | Compact navigation strip, coordinated surfaces, responsive viewer/sidebar layout, clearer soft-point-rendering label, and WebGL failure fallback |
| Tolerance Lens | “Improve this measurement” now reads “Try targeted refinement,” with an explanation that additional processing may not improve the result |
| Existing showcase/report/lab | Existing functionality retained; shared visual tokens and navigation updated. These are not complete screen-by-screen redesigns yet. |
| Loading performance | Heavy analysis and Three.js routes load separately from the homepage. Its preview uses a small sampled binary asset and draws only on load, resize, or user interaction. |

Reconstruction algorithms and backend processing have not been changed by this UI pass. No saved mission or running reconstruction is modified by visiting the introduction.

## 3. Visual identity

### Design language

Use a restrained instrument-like aesthetic: warm charcoal, soft off-white, a pale lime accent, subtle grids, thin dividers, generous whitespace, and small monospaced annotations. The geometry is the centrepiece. Avoid turning every panel into a glowing cockpit widget.

| Token | Value / rule | Purpose |
| --- | --- | --- |
| Base | `#101411` | Main application background |
| Surface | `#171d18` | Cards and tool panels |
| Raised surface | `#202821` | Controls and secondary information |
| Divider | `#303a31` | Quiet structural separation |
| Main text | `#eef0e7` | Headings and important values |
| Secondary text | `#a1ada1` | Explanation and metadata |
| Brand accent | `#c4ed86` | Primary actions and selected navigation |
| Evidence colours | Existing green / amber / purple / red / grey | Preserve backend provenance and result semantics |
| Typeface | Local sans-serif stack; monospace for IDs and numeric metadata | Works without an external font service |
| Radius | Approximately 4–8 px | Controls and panels, without oversized rounded cards |
| Main spacing | 8 / 16 / 24 / 32 / 48 / 76 px | Dense product controls; spacious explanatory sections |

Headings should feel editorial: short, specific, and sentence case. Large text belongs on the overview; numbers and tool names should remain compact in the workspace. Do not style ordinary completion status as proof that a measurement satisfies a requirement.

### Imagery and diagrams

1. Use actual reconstructed geometry as the principal visual.
2. Keep the source, capture name, scale limitation, and inferred content identifiable.
3. Clearly label explanatory diagrams as diagrams.
4. Use real captured thumbnails only when they can be linked to a saved mission. Do not generate fictional mission imagery.
5. Do not fetch full research clouds or autoplay large videos merely to decorate the homepage.

The implemented hero samples the bundled Gymnasium Neubiberg PLYs, preserving coordinates and colours. Its appearance/evidence toggle changes rendering only. This preview is never used for measurements. `frontend/scripts/build-preview.py` regenerates it, and `frontend/public/showcase/README.md` records the asset lineage.

## 4. Information architecture

```text
Overview /
  ├── Explain the workflow
  ├── Explore the saved research scene → /prototype
  ├── Open mission library → /missions
  └── Start reconstruction → /new

Mission library /missions
  ├── Draft → /new?project=<id>
  ├── Processing / needs attention → /projects/:id/demo
  ├── Reconstructed → /projects/:id
  ├── Presentation → /projects/:id/demo
  └── Quality report → /projects/:id/report

Setup → /projects/:id/monitor?job=<job-id>
  └── Analysis → questions, evidence, available exports
```

Keep “Research lab” distinct from the normal mission workflow. It is valuable for demonstrating experimental geometry but should not imply that every production reconstruction follows the same experimental pipeline.

## 5. Screen-by-screen design

### Overview: curiosity → explanation → evidence → action

**First viewport:** place the product statement on the left and an inspectable saved scene on the right. The primary action starts a mission; a quieter action moves to the workflow. A visitor must understand the input and output before scrolling. On phones, the statement and action appear first, followed by the scene.

**Workflow:** use three steps: capture, reconstruct, inspect. Each step needs one short explanation and one simple geometric illustration. Detailed engine names belong in the application, not in this first explanation.

**Evidence section:** explain the difference between observed, inferred, and unknown. Use text as well as colour. The three meaningful actions are inspecting source support, asking a question with a requirement, and understanding a limitation.

**Saved example:** show the recorded footage/reconstruction comparison and link to the complete interactive scene. State that this example has relative scale and AI-assisted content. A saved example must not masquerade as a live run.

**Closing action:** invite the visitor to bring footage. Keep one clear primary action; avoid a collection of unrelated feature buttons.

Acceptance: the visitor can explain the idea after the first viewport, can reach a real example without the backend, and can start a mission from either end of the page.

### Mission library: a reliable place to return

Each card should answer: What capture is this? What state is it in? What can I do next? What inputs exist?

The implementation maps internal states to readable labels: Draft, Processing, Reconstructed, and Needs attention. “Reconstructed” describes a completed pipeline, not validated measurement quality. Search operates on mission names and descriptions; filters keep the available actions predictable.

Empty states must distinguish an empty library from an empty search result. Network failure must offer retry rather than pretending there are no missions. Delete has an explicit confirmation and is disabled for processing missions in this interface.

Next improvement: add actual saved capture thumbnails and a compact quality summary only when backed by the relevant project artifacts. Keep input readiness, processing completion, and measurement acceptance separate.

### Setup: four understandable decisions

1. **Your mission:** name and optional description.
2. **Drone footage:** upload one capture and confirm the received filename.
3. **Telemetry:** optional upload with a clear explanation of video-only limitations.
4. **Camera and options:** calibration and processing choices, followed by a clear start action.

Draft links persist the server project ID, so returning to setup does not create a second project. Going back from the upload step leads to the library; it does not offer an apparent edit that secretly creates a duplicate. Browser navigation to “New reconstruction” resets the wizard to a new mission.

Next improvement: actual transfer progress, cancel/retry, capture diagnostics, and a final input summary. Do not add a percentage until there is a real upload progress source. Expose processing engines only after checking backend capabilities and request compatibility. Explain tradeoffs in operator language beside advanced settings.

Acceptance: interrupted setup can resume; controls cannot submit twice while busy; missing telemetry is explained before processing; errors preserve the current project.

### Processing: make time and uncertainty understandable

The existing monitor remains functional and inherits the visual system. A full redesign should group backend stages into four readable phases: preparing capture, recovering geometry, aligning/fusing, and preparing results. Expand a phase to see engine stages and diagnostics.

Show elapsed processing time when its origin is known. Session viewing time must be labelled separately. Never simulate an ETA, reset a resumed mission to an apparent new start, or make 100% progress mean “usable reconstruction.”

Connection loss needs a reconnecting state and recurring recovery checks. After reconnect, show the latest persisted job state. A failed run should retain its capture and provide a useful next action. Cancellation requires backend support and a defined artifact cleanup policy before adding a button.

Acceptance: reconnecting cannot look like processing success; a terminal result stops the timer; sparse or unusable results lead to a limitations message rather than celebration.

### Analysis: the model is the main working surface

Desktop layout: compact mission navigation above three regions. Left: measurement tools, requirement questions, and display layers. Centre: geometry and direct manipulation. Right: reconstruction quality, source context, saved results, and exports.

The current responsive implementation stacks the viewer before panels on phones and moves secondary evidence below the main view on narrower desktops. A future iteration should add explicit Scene / Tools / Evidence navigation on mobile, preserve selections between panels, and provide keyboard alternatives to point picking.

Keep scale and coordinate system visible near the measurement tools. A relative-scale scene must not acquire believable metres or map coordinates simply because a shared viewer component formats its values that way. That is a correctness dependency for the next measurement-focused pass.

Next improvement: selected-question highlighting, source-frame thumbnails with endpoint overlays, direct navigation from an evidence frame to the footage, and a compact “what limits this answer?” summary. These should consume persisted evidence; the browser must not infer acceptance from visible point density.

Acceptance: the operator can trace a displayed result to its supporting data; inferred geometry is visibly distinct; low confidence cannot be hidden by switching to appearance mode; lack of WebGL leaves a useful explanation and the surrounding evidence available.

### Tolerance Lens and targeted refinement

The old wording “Improve this measurement” sounds like a guaranteed upgrade that should already have happened. The implemented wording is **“Try targeted refinement.”** Supporting text explains that it checks additional frames and may not produce a better answer.

Conceptually, reconstruction produces the scene first. Targeted refinement is an additional attempt focused on a particular selected measurement. It has a processing cost, needs a target, and can fail to find useful additional support. This is why it is a separate action; it must not suggest that a free, guaranteed accuracy improvement was deliberately withheld.

The frontend currently asks the existing API to refine the selected question with a frame budget of four. This UI pass changes wording, not that algorithm or budget. It does not establish that refinement is correct on every dataset.

The ideal result card should present, in order:

1. The question, value, and unit.
2. The requirement and backend decision.
3. Whether an interval is calibrated or only an uncalibrated sensitivity estimate.
4. The dominant limitation, in plain language.
5. Evidence and the next supported action.

After refinement, show separate facts: did the value move, did the reported interval change, did support increase, did the acceptance decision change? A narrower interval alone is not proof of improved accuracy. “No useful frames found” is a valid outcome.

An optional automatic refinement mode is future work. It needs validated behavior, bounded resource use, progress/cancellation, and evidence that automatic work helps enough to justify its cost. Do not turn it on merely to remove a confusing button.

### Showcase and report

Give presentations a concise narrative: source → recovered scene → one representative measurement → supporting frames → limitations. Presentation mode should minimise controls without removing uncertainty labels. Allow a presenter to explain a saved run without implying live inference.

The report should become a shareable, print-friendly evidence document: capture metadata, method, available quality metrics, measurement questions, source support, limitations, and artifact/version identifiers. The next report redesign should prioritise reading order and clear units over more charts.

## 6. Interaction, accessibility, and performance rules

- Every interactive item must be a real link, button, or input with a discernible name. Avoid clickable generic cards with hidden keyboard behavior.
- Preserve visible keyboard focus. Use status text alongside colour, and associate explanations with the controls they describe.
- Use a 44 px target for major touch actions where practical; compact analysis controls need a deliberate spacing audit. The current implementation is a foundation, not a claim of full accessibility conformance.
- Respect reduced motion. The homepage has no perpetual animation, forced orbit, or autoplaying video.
- Keep the homepage independent of mission API availability. Explain backend failures inside the product surfaces that need it.
- Lazy-load the heavy 3D routes. Avoid sending the full dense research cloud on the overview route.
- Prefer drawing only when needed for the preview. For analysis viewers, future work should pause rendering when hidden and handle graphics-context loss after initialisation.
- Test 390 px phone, 768 px tablet, and 1440 px desktop layouts, plus very narrow devices and 200% zoom before a public release.
- Keep claims tied to available evidence. Telemetry upload is not the same as successful georeferencing; processing completion is not the same as accepted accuracy.

## 7. Prioritised next work

Effort estimates are relative engineering effort, not a delivery promise.

| Priority | Improvement | Why it matters | Dependency / acceptance | Effort |
| --- | --- | --- | --- | --- |
| P0 | Audit metric/relative units throughout viewer, question cards, and exports | Prevents a polished UI from presenting unsupported measurements | Unit and scale semantics must match artifacts and API results | Medium |
| P0 | Source-frame evidence with endpoint overlays | Makes the project's differentiator tangible to judges | Actual recorded observations; identify dense contributors separately from sparse feature observations | Medium–large |
| P0 | Complete monitor reconnect/resume/failure UX | A long real run must remain understandable | Reliable persisted job status; distinguish job time from session time | Medium |
| P1 | Input readiness and final setup review | Catches avoidable capture problems before expensive processing | Real diagnostics and available-engine checks | Medium |
| P1 | Presentation narrative and comparison controls | Makes a short demonstration coherent and convincing | Source video and saved output; preserve scale/provenance labels | Medium |
| P1 | Report reading order and print stylesheet | Gives reviewers a useful artifact after the demonstration | Accurate backend quality/evidence fields | Medium |
| P1 | Keyboard and touch measurement workflow | Makes the core tool accessible beyond mouse precision | Selection model, camera controls, and panel focus behavior | Medium–large |
| P2 | Capture thumbnails and compact mission health | Speeds up navigation across a growing library | Stored thumbnails and honest quality summary | Medium |
| P2 | Before/after refinement evidence view | Explains whether extra work was actually useful | Stable question/artifact versions and comparable measurements | Medium |
| P2 | Optional bounded automatic refinement | Can reduce operator effort if validated | Demonstrated benefit, budget controls, cancellation, correctness tests | Large |

## 8. Suggested competition demonstration

This is a presentation plan, not a claim about current processing speed.

| Approximate time | Show | What the audience should learn |
| --- | --- | --- |
| 0:00–0:20 | Overview and actual preview | One drone pass becomes inspectable geometry |
| 0:20–0:45 | Original footage and saved result | The reconstruction has a concrete input and lineage |
| 0:45–1:15 | Appearance vs provenance | Visually complete and directly observed are different |
| 1:15–1:55 | One prepared measurement question | The system answers a requirement, with limitations |
| 1:55–2:25 | Supporting frames and quality report | A reviewer can inspect the evidence |
| 2:25–3:00 | Validated refinement outcome or a clearly explained failure | The system is honest about what more processing can achieve |

Prepare a saved mission in advance. Label live processing and saved results explicitly. If a dataset has no valid metric scale, demonstrate geometry and evidence rather than presenting metres.

## 9. Implementation map and verification

| File | Responsibility |
| --- | --- |
| `frontend/src/design.css` | Shared visual tokens, overview, library, setup, and responsive workspace styling |
| `frontend/src/App.tsx` | Navigation, brand, skip link, and route scroll reset |
| `frontend/src/views/Overview.tsx` | Product narrative and saved-example presentation |
| `frontend/src/ScenePreview.tsx` | Lightweight actual-geometry preview and evidence colouring |
| `frontend/src/views/Dashboard.tsx` | Live mission library and its states/actions |
| `frontend/src/views/Wizard.tsx` | Setup and draft restoration |
| `frontend/src/views/Workspace.tsx` | Analysis navigation and layout integration |
| `frontend/src/PointCloudViewer.tsx` | Existing 3D viewer, with initial WebGL failure fallback |
| `frontend/src/ToleranceLens.tsx` | Existing measurement UI, with clearer refinement language |
| `frontend/src/main.tsx` | Overview/library routes and lazy-loaded product screens |

Verification performed for this pass: production TypeScript/Vite build; browser interaction checks for preview controls, workflow anchor, mission search/filters, draft restoration, new-mission form, responsive navigation, workspace rendering, and API failure/retry. Layouts were inspected at desktop and phone sizes, with horizontal overflow checks at phone/tablet/desktop widths. Browser mission requests used isolated fixtures; no real projects were created, deleted, or processed by the checks.

The browser checks exercise the frontend, not reconstruction accuracy, all optional engines, every evidence status, a full screen-reader journey, or all export formats. Continue dataset validation separately. Use the priorities above to deepen the evidence workflow after the visual foundation is accepted.

### Reproduce the frontend checks

The browser script is `frontend/scripts/ui-smoke.cjs`. Start Vite on port 5174 (or supply `UI_BASE_URL`), install Playwright in a separate test environment, and make its module available to Node. For example, from `frontend`:

```bash
npm run build
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

In a second terminal:

```bash
npm install --prefix /tmp/drishti-ui-check playwright
# Install a browser with Playwright, or use CHROMIUM_PATH for an existing one.
NODE_PATH=/tmp/drishti-ui-check/node_modules node scripts/ui-smoke.cjs
```

The test launches a headless browser with software graphics, intercepts every mission API request, and writes screenshots under `/tmp/drishti-ui-check`. It also checks that starting a fresh mission clears a resumed draft, and that a browser without WebGL retains access to the surrounding workspace and report link. To use an existing Chromium executable, set `CHROMIUM_PATH` to its absolute path. The script does not install dependencies into the application package.
