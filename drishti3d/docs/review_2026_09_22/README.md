# Drishti3D — review and SIH report pack

**Prepared:** 22 September 2026. **Reviewed revision:** `9506a31e41f2550652e38fce33914788602ee5ee`.

Start with [the critical review](CRITICAL_REVIEW.md) for what to fix, [the project report](PROJECT_REPORT.md) for the current architecture and presentation material, and [the six-slide handoff](SIH_SLIDE_HANDOFF.md) for the official submission structure. [The combined PDF](DRISHTI3D_REVIEW_AND_PROJECT_REPORT.pdf) and [HTML edition](DRISHTI3D_REVIEW_AND_PROJECT_REPORT.html) collect all three.

This is a dated assessment, not a certification or an organiser-issued verdict. Existing saved mission artifacts were inspected; new full reconstruction jobs were not run. Production code and mission data were not changed for this review.

## Verification performed

| Check | Fresh result |
|---|---|
| `cd drishti3d && .venv/bin/python -m pytest tests -q` | 444 passed; 49 warnings; 111.10 seconds |
| `.venv/bin/python -m pytest docs/review_checks/test_followup_2026_09_21.py -q` from `drishti3d` | 15 passed; 6 warnings; 1.91 seconds |
| `npm run build` from `drishti3d/frontend` | TypeScript and production build passed; Vite 5.4.21 |
| Measurement-method counterexamples | All three assertions passed; [JSON output](measurement_validity_probe.json) |

The second check supersedes the old report's nine failing follow-up checks. Passing unit and regression tests demonstrates implementation consistency; it does not establish metric accuracy on unseen flights. Previous frontend browser checks belong to the earlier UI work, not a fresh browser walkthrough in this audit.

The [artifact snapshot](artifact_snapshot.json) preserves the inspected saved-result values and SHA-256 hashes. The original mission artifacts were read without modification.

Reproduce the measurement counterexamples from the repository root:

```bash
drishti3d/.venv/bin/python drishti3d/docs/review_checks/measurement_validity_probe_2026_09_22.py
```

## Official source trail

1. Open the [official SIH 2026 problem-statement listing](https://www.sih.gov.in/sih2026PS).
2. Find **SIH26158**, **Single-Pass Drone Video to Accurate 3D Model Generation System**, NTRO, Software, Robotics and Drones.
3. Follow that entry's **Additional Information** link to the [Google Drive attachment](https://drive.google.com/file/d/119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD/view?usp=drive_link).
4. Its three scanned pages are numbered 37–39 in the source document. **Attachment page 2 / printed page 38 contains the output and scoring tables.** The attachment labels this internally as Problem Statement 17; the portal identifies it as SIH26158.

A byte-for-byte [local copy of the attachment](sources/SIH26158_official_attachment.pdf) is included for convenient checking. It is an organiser document, not a Drishti3D-generated PDF. The scan has no useful extractable text, so all three pages were inspected as images. Download URL: [Drive download](https://drive.google.com/uc?export=download&id=119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD).

**SHA-256:** `02e2a9fa37f129059546e6d302fe567f56226226c14f9038d1ad0fbd1279edd6`.

The listing was successfully retrieved during research. A subsequent web-tool fetch returned HTTP 403; that intermittent restriction does not change the already retrieved entry and linked attachment. No numerical requirement here was inferred from a search snippet.

## Presentation sources and a date discrepancy

The [official 2026 presentation template](https://www.sih.gov.in/letters/2026/SIH2026-IDEA-Presentation-Format.pptx) contains six content slides and a seventh instruction slide to remove. Its instructions specify at most six slides including the title, use of the supplied template, and PDF submission. The slide handoff follows that structure; the long report is supporting material, not the submission deck.

Template SHA-256: `ce3e5deebec2741f3383cb2dd21269cad8d9930f7c747c9903d7d4b27db14de6`.

The [2026 College SPOC guidelines](https://www.sih.gov.in/letters/2026/SIH2026-Guidelines-College-SPOC-updated.pdf) describe general evaluation considerations including novelty, feasibility, clarity, impact and user experience. The PDF still mentions 15 September, whereas the live problem-statement page displayed **30 September 2026** when inspected. Confirm the applicable submission window in the actual team/SPOC portal; do not rely on the stale PDF date or an unofficial mirror.

Guidelines SHA-256: `16c46ab530716847b1a8191d8975c2a52fc3f62c1532cedfaaf97c67531dfab4`.

Do not import the adjacent SIH26157 statement's specialised presentation or deployment instructions into SIH26158. Requirements in this pack are traced to this project's own entry and attachment.
