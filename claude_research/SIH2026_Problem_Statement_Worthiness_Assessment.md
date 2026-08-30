# SIH 2026 — Problem-Statement Worthiness Assessment (Win Analysis)

*Prepared 2026-08-27. Purpose: pull the full official detail of all twelve shortlisted problem statements and judge each one honestly on how winnable it is **for our team specifically** — a web + ML student team, already deep in the 3D-reconstruction/geospatial domain, working on a single RTX 4060 Laptop (8 GB) machine. This is written in plain prose, not tables or data dumps, so it can be read straight through before a decision is made.*

*Source of record: the official portal `sih.gov.in/sih2026PS`, read through the machine-readable scrape at the `vedantchalke36/sih-2026-problem-statements` GitHub repository (CC-BY-4.0, scraped 2026-08-21) and the `sih2026.vuce.in` community mirror. All twelve share a 20 September 2026 idea-submission deadline and all were at 0/500 submissions on the scrape date, so today's live counts will be higher — verify on the official portal before locking a choice. A few themes on the mirror are mis-scraped (flagged where relevant); the GitHub scrape is treated as more reliable for theme labels.*

---

## How I am judging "worthiness to win"

A problem statement is not worth chasing just because it is important or impressive — it is worth chasing if *this* team can build something that beats the room in the time available. I score each statement across six dimensions, and the verdict is a judgement about their balance, not a raw sum. The six are:

**Buildability in the SIH window** — can a genuinely working prototype (not a slide deck) be produced by six students by the grand finale, given the dependencies the statement forces on you? A statement that mandates a specific heavy tool or a research-grade result loses here.

**Team and hardware fit** — does it play to what we already have: Python/ML, web visualisation, geospatial reasoning, and the provenance/uncertainty framework we built for the drone project — and does it fit inside 8 GB of laptop VRAM? Statements needing large-model training, MATLAB depth, or specialist physics score lower.

**Data availability** — is there open, legal, sufficient data to train and, above all, to *demonstrate* convincingly? This is the single most common silent killer at SIH: a beautiful method with nothing real to run on.

**Demo "wow"** — will a live demo produce something a judge can see and immediately believe? Maps, reconstructions, heatmaps and animations win rooms; abstract dashboards on synthetic data do not.

**Differentiation headroom** — can we build something defensibly better than the obvious baseline, or is the space so crowded/near-solved that every team shows the same thing?

**Impact and sponsor appeal** — national relevance and the prestige/scrutiny of the sponsoring body. Defence-adjacent sponsors (NTRO, DRDO, MHA) carry prestige but also expert scrutiny and data-sensitivity; MoES and MathWorks are high-impact and more forgiving to demo.

Each statement below gets a short factual recap, an honest read against these six, and a verdict on a 10-point worthiness scale with a tier label. The consolidated ranking — and where I disagree with the F/G/M/S/W scorecard you pasted — is at the end.

---

## The twelve, one by one

### 1. SIH26158 — Single-Pass Drone Video to Accurate 3D Model Generation System (NTRO)

*Software · Theme: Robotics and Drones · Dataset "will be provided real-time".* The statement asks for a georeferenced, metrically accurate, textured 3D model — terrain, façades, roads, vegetation — from a **single** UAV pass, and it explicitly lists the hard parts itself: limited viewing angles, motion blur, dynamic objects, GPS noise, occluded surfaces, and metric accuracy without extensive GCPs. Notably the published text has an unfilled placeholder where "Desired Output" and "Evaluation Criteria" tables should be, meaning the sponsor has left the accuracy bar partly undefined — which we can turn to our advantage by *defining and proving* it ourselves.

This is our prepared flagship and it remains the right primary bet — not out of sunk cost, but because it scores well on its own terms and we have a decisive preparation lead. It is the strongest possible fit for our stack and, more importantly, for the provenance/measurement-safety wedge we have already built: single-pass reconstruction is exactly where "which parts of this model are measured versus inferred" becomes a life-or-death honesty question, and no competitor tool packages that. The demo is as visual as it gets. The real risks are that it is genuinely a research-hard problem (metric accuracy from monocular single-pass video), it is glamorous enough to attract many strong teams, and the sponsor controls the evaluation data. Our dossier already neutralises most of that. **Verdict: 9/10 — Tier 1, keep as primary.**

### 2. SIH26059 — AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory & Navigation Decision Support (MoES / NCPOR)

*Software · Theme officially tagged "Smart Education" (a mis-tag — the content is polar/geospatial) · no dataset attached.* The published statement is a single short paragraph: forecast Antarctic sea-ice concentration, predict iceberg trajectories, and recommend safe, fuel-efficient routes for research vessels from satellite, oceanographic and meteorological data. That brevity is an opportunity — it hands you enormous freedom to define the winning scope.

This is my top *sleeper* pick and I rate it almost level with the drone project. The data it needs is all openly available and rich (NSIDC passive-microwave sea-ice concentration, the BYU/Antarctic iceberg tracking databases, Copernicus Marine and ERA5 for ocean/met), so the demo runs on real data, not synthetic. The method — a forecasting model feeding a cost-field routing search — is squarely in our ML-plus-visualisation wheelhouse and fits comfortably on the laptop. The demo is beautiful and legible: animated sea-ice fields, predicted iceberg drift, and a highlighted safe route line over the Southern Ocean. Competition is likely thin because the topic sounds intimidating and niche, and national polar-programme relevance gives it real impact. The routing layer is where most teams will be weak and we can be strong. **Verdict: 8.5/10 — Tier 1, strongest alternative to the drone PS.**

### 3. SIH26143 — Satellite Oil-Spill Detection + AIS Vessel Attribution (NTRO)

*Software · Theme: Space Technology · Dataset: marinecadastre.gov AIS portal.* The task is an intelligent pipeline that detects and characterises an oil slick from SAR/EO satellite imagery, hindcasts its drift backward to an origin point and time using ocean/met data (and forecasts it forward), then reconstructs vessel traffic from historic AIS to score and rank the suspect vessel by proximity, trajectory and behavioural anomalies.

This is the alternative I would push hardest if we ever reconsidered the drone PS, because it *reuses almost all of our existing research* — geospatial reasoning, uncertainty/provenance, and honest confidence scoring — on a problem with excellent open data. Sentinel-1 SAR is free and there are labelled oil-spill SAR datasets to train on; AIS is public and the sponsor even points to a source. The pipeline tells a gripping, multi-stage forensic story that demos superbly: raw SAR → detected slick mask → backward drift arrows to an origin box → a ranked list of suspect ships on a map. That attribution narrative is a natural differentiator; most teams will stop at "detect the slick." NTRO sponsorship adds prestige, and the confidence-scoring requirement is exactly the kind of thing our provenance framework was built for. **Verdict: 8.5/10 — Tier 1.**

### 4. SIH26054 — Real-Time Digital Twin for Health Monitoring & RUL of MALE-UAV Aero Piston Engines (DRDO)

*Software · Theme: Robotics and Drones · no dataset attached.* The statement wants a continuously synchronised virtual replica of an aero piston engine that fuses live sensor telemetry (RPM, cylinder-head and exhaust-gas temperatures, oil pressure, fuel flow, vibration signatures) with thermodynamic models and AI to do anomaly detection, fault prediction, and Remaining-Useful-Life estimation, plus mission-profile simulation and an operator dashboard — with a wishlist that runs to physics-informed AI, edge inference, federated learning and explainable AI.

I rate this well below where your pasted scorecard puts it (you have it at 83, near the top; I have it near the bottom), and the reason is data and domain, not ambition. There is **no public telemetry for a specific MALE-UAV piston engine** — that data is defence-held — so a student team is forced to fabricate it with a simulator, and a DRDO propulsion expert on the jury will see straight through a digital twin whose "physical" side is itself synthetic. The demo reduces to a dashboard animating made-up numbers, which is exactly the kind of unconvincing result our own research warns against. Winning here really needs a mechanical/propulsion background and, ideally, a data-sharing arrangement we do not have. High prestige, high scrutiny, low buildability-with-credible-data. **Verdict: 5/10 — Tier 4, avoid unless the team has genuine propulsion expertise.**

### 5. SIH26037 — Adaptive Path Planning & Collision Avoidance for Unstructured Indian Roads (MathWorks)

*Software · Theme: Robotics and Drones · dataset attached.* A MATLAB/Simulink simulation of a self-driving vehicle on Indian roads: perceive via camera/LiDAR/radar, detect mixed traffic (auto-rickshaws, pushcarts, pedestrians, animals), predict short-term motion, and generate a collision-free, continuously replanned path, validated across five prescribed scenarios (village road, unsignalled intersection, highway merge, dense market, sudden cattle crossing), with at least two hand-built RoadRunner scenes.

MathWorks provides free MATLAB/Simulink/RoadRunner licences for its SIH statements, so tooling cost is not the barrier — but three things hold this down for us. It is **simulation-only**, so the "wow" ceiling is a tidy simulated drive rather than something tangible; autonomous driving is one of the most crowded topics at any hackathon, so differentiation is genuinely hard; and building two-plus realistic RoadRunner scenes plus the closed-loop stack is a real time sink inside the finale window. It is buildable and the scenarios are vivid, but it is a commodity space where many capable teams converge and our particular strengths (geospatial, uncertainty) do not transfer. **Verdict: 6.5/10 — Tier 3, viable but crowded and demo-capped.**

### 6. SIH26161 — Dam-Break Inundation Modelling via Hydrodynamic Simulation (NTRO)

*Software · Theme: Disaster Management · dataset attached.* The statement asks for a tool that automatically runs dam-break/river-blockage simulations and maps downstream inundation using DEM and satellite data, and it is unusually prescriptive about method: it names **Smooth Particle Hydrodynamics and Delft3D** and asks you to compare the two, wants near-real-time analysis through Google Earth Engine, a dashboard, and export to .shp/.kml.

The disaster impact is high, the visuals (propagating flood front, inundation polygons) are strong, and NTRO adds prestige — but the prescribed toolchain is the catch. Delft3D has a serious learning curve and SPH is compute-heavy, and being asked to run *both* and compare them, plus a GEE pipeline and a dashboard, is a lot to stand up credibly in the window on an 8 GB machine. DEM data is available (Copernicus DEM, Bhoonidhi), so data is not the problem; execution risk is. Doable for a hydrology-comfortable team, heavier than it looks for us. **Verdict: 6.5/10 — Tier 2/3 borderline, good impact but tool-dependency risk.**

### 7. SIH26189 — AI-Powered Criminal Network Analysis System (MHA / NCRB)

*Software · Theme: Blockchain & Cybersecurity · no dataset attached.* The task is to ingest fragmented, unstructured crime data (FIRs, call-detail records, financial transactions, surveillance, social-media intelligence), extract entities (people, locations, vehicles, phone numbers, organisations), build relationship graphs, surface key influencers, and flag suspicious patterns for investigators.

The technique here is entirely within reach — entity extraction with NLP, graph construction, centrality measures for "key influencers," anomaly detection — and MHA sponsorship carries weight. The problem is that **real criminal data is, correctly, unavailable**, so the entire demo runs on synthetic or mock networks, which caps how convincing it can be and invites the "you've built a generic graph dashboard" critique. Graph visualisations look busy but read as generic to a jury that has seen many of them. It is safe to *build* but hard to *win* with, because the differentiation and the impact-proof both depend on data you cannot get. **Verdict: 6/10 — Tier 3.**

### 8. SIH26057 — Automated Underwater Marine-Debris Detection from Side-Scan Sonar (MoES / NIOT)

*Software · Theme mis-tagged "Renewable/Sustainable Energy" (content is ocean/CV) · no dataset attached.* An end-to-end pipeline that ingests side-scan sonar imagery, separates man-made debris and ghost nets from natural seafloor, handles heavy speckle noise / acoustic shadows / data dropouts, scores confidence (0–100 %), geotags detections to structured JSON/CSV, and shows them on a dashboard map.

The method is standard and buildable (segmentation/detection models plus a confidence and geotagging layer), the topic is niche enough that competition should be light, and the confidence-scoring requirement again suits our provenance instincts. The decisive weakness is **data**: labelled side-scan sonar imagery of debris and ghost nets is scarce in the open, and without a solid dataset the model cannot be trained or demoed convincingly, pushing the team toward thin or synthetic sonar that undermines credibility. If — and only if — NIOT or a public source supplies real labelled sonar, this jumps a tier; on current information the data risk dominates. **Verdict: 5.5/10 — Tier 3/4, gated entirely on data access.**

### 9. SIH26085 — Urban Flood Nowcasting via Drainage–Rainfall Coupling (MoES / NCMRWF)

*Software · Theme: Disaster Management · no dataset attached.* Build a coupled high-resolution nowcasting system with a 0–3 hour lead time that fuses radar rainfall nowcasts, high-resolution DEMs and a **graph model of the storm-drain network** (nodes as manholes/inlets, edges as pipes) to predict street-level inundation depth in centimetres, shown on a web-GIS dashboard, with an API that recommends flood-safe alternative routes.

This is one of the cleaner, more winnable builds in the list for us. The architecture is well-defined and modular, it maps neatly onto our web-GIS and graph skills, and the demo is excellent: a street-level flood map updating ahead of the rain, plus live flood-safe rerouting — a judge grasps the value in seconds. Rainfall (IMD/GPM) and DEM data are available, and the one genuinely private input, the municipal drainage graph, can be represented synthetically without hurting the demo's credibility because the *method* is the point. Disaster relevance is high and the drainage-coupling angle differentiates it from generic rainfall prediction. **Verdict: 7.5/10 — Tier 2, strong and buildable.**

### 10. SIH26192 — Flash-Flood Prediction for Hilly Regions from Multi-Source Data (MHA / NDRF)

*Software · Theme: Disaster Management · no dataset attached.* Integrate rainfall, soil-moisture sensors, slope-stability models, historical landslide inventories and real-time IoT inputs to generate hyper-local, village/ward-level flash-flood forecasts with enough lead time to evacuate.

The impact is about as high as it gets — NDRF sponsorship, direct loss-of-life relevance — and the data mostly exists in the open (IMD/GPM rainfall, free DEM-derived slope, SMAP soil moisture, GSI and NASA global landslide catalogues), with the IoT layer safely simulated. It is a feasible multi-source fusion-plus-risk-mapping build that demos well as hyper-local risk maps and alerts. What holds it a notch below the leaders is differentiation: flood/landslide prediction is a common SIH theme, so several teams will arrive with similar fusion pipelines, and the hyper-local claim is hard to *prove* convincingly in a demo. Strong, worthy, but crowded. **Verdict: 7/10 — Tier 2.**

### 11. SIH26142 — Deep-Learning Super-Resolution of Medium-Resolution Satellite Imagery (NTRO)

*Software · Theme mis-tagged "Smart Education" (content is Space/remote-sensing) · Dataset: Copernicus Data Space.* Turn 10 m Sentinel-2 imagery into sub-4 m products using a model of the team's choice (transformer/GAN/diffusion/CNN), preserving geospatial and spectral consistency, with pre-processing, paired-data training, accuracy assessment and validation against high-resolution references — and, crucially, the statement itself insists on **managing uncertainty** because reconstructed detail is inferred, not observed.

That last clause is the reason this is a better fit for us than it looks: the sponsor is explicitly asking for the measured-versus-inferred honesty we have already made our signature, so our provenance/uncertainty framework transfers almost verbatim, and "we don't just sharpen, we tell you which pixels are trustworthy" is a ready-made differentiator in a crowded CV space. Data is excellent and provided. Two real cautions: super-resolution is well-trodden, so plain results won't stand out, and diffusion/large-transformer training is VRAM-hungry — 8 GB is tight, so we would lean on lighter architectures or heavy patch-based training. The uncertainty angle is what lifts it. **Verdict: 7.5/10 — Tier 2, and the closest thematic cousin to our drone work.**

### 12. SIH26038 — Explainable AI for Diabetic-Retinopathy Screening in Rural India (MathWorks)

*Software · Theme mis-tagged "Clean & Green" (content is MedTech) · Datasets: APTOS 2019, IDRiD, DRIVE, Messidor-2 — all public and provided.* A MATLAB pipeline that assesses fundus-image quality with recapture feedback, segments retinal structures, grades DR on the 0–4 clinical scale at >90 % sensitivity / >85 % specificity for referable DR, explains itself with Grad-CAM and calibrated confidence, and models the district-scale telemedicine workflow in Simulink.

This is the **safest statement to get a polished, working result** and I rate it clearly higher than your scorecard's last place (74). The data is the best in the whole list — four canonical public datasets — the metrics are crisply defined, MATLAB licences are free, and the demo is genuinely moving: a fundus photo, a heatmap over the lesions, a grade, and an auto-generated report, wrapped in a rural-blindness-prevention story that judges respond to. The catch is the flip side of that maturity: DR classification is close to solved on these datasets and thousands of teams worldwide have done it, so a plain classifier will not win. The victory has to come from the parts most teams skip — rigorous explainability rated *clinically useful*, calibrated confidence with image-quality gating, and the Simulink resource-allocation model. High floor, capped ceiling unless the XAI and workflow rigour are exceptional. **Verdict: 7/10 — Tier 2, safest build, differentiation is the whole game.**

---

## Consolidated ranking for our team

Reading the six dimensions together rather than adding them up, this is how I would rank the twelve for *our* team's chance of actually winning, best first:

**Tier 1 — go for it.** SIH26158 (Drone-to-3D, 9/10) stays the primary bet: it is genuinely strong on its own terms and we hold a commanding preparation lead and a real differentiator no competitor packages. SIH26143 (oil-spill + AIS attribution, 8.5/10) and SIH26059 (Antarctic navigation, 8.5/10) are the two standouts behind it — and both are worth naming because each reuses our geospatial-plus-uncertainty research almost directly, runs on excellent open data, demos vividly, and sits in less-crowded territory than the drone problem.

**Tier 2 — strong, buildable alternatives.** SIH26085 (urban flood nowcasting, 7.5/10) and SIH26142 (satellite super-resolution, 7.5/10) — the latter is the closest thematic cousin to the drone work because the sponsor itself demands measured-vs-inferred honesty. Then SIH26192 (hilly flash-flood, 7/10) and SIH26038 (XAI diabetic retinopathy, 7/10): the retinopathy statement is the single safest way to guarantee a polished working demo, if we accept that its differentiation must come entirely from explainability and workflow rigour.

**Tier 3 — viable but harder.** SIH26161 (dam-break, 6.5/10, tool-dependency risk from the mandated Delft3D + SPH), SIH26037 (Indian-roads path planning, 6.5/10, crowded and simulation-capped), SIH26189 (criminal-network analysis, 6/10, generic demo on synthetic data).

**Tier 4 — high risk for us.** SIH26057 (side-scan-sonar debris, 5.5/10, gated on scarce labelled data) and SIH26054 (UAV-engine digital twin, 5/10, no public engine telemetry and a domain barrier we don't clear).

## Where I disagree with the F/G/M/S/W scorecard you pasted

Our rankings agree at the very top — that scorecard also puts SIH26158, SIH26059 and SIH26143 in its leading group, which is reassuring. The three disagreements worth flagging:

- **SIH26054 (UAV engine digital twin)** — the scorecard ranks it joint-third (83); I rank it near the bottom. The scorecard appears to reward its ambition and sponsor prestige, but it doesn't price in that there is no obtainable real engine telemetry, which for a *digital twin* is disqualifying for a credible demo. This is the biggest gap between the two views and the one I'd most urge you not to ignore.
- **SIH26038 (diabetic retinopathy)** — the scorecard puts it last (74); I put it mid-pack. It undervalues how much a guaranteed-working, data-rich, emotionally resonant demo is worth at a hackathon. Its ceiling is capped by how solved the problem is, but its floor is the highest in the list.
- **SIH26037 (path planning)** — the scorecard has it at 82; I have it lower, because "simulation-only in a crowded field" hurts winnability more than a rubric that rewards feasibility and impact tends to show.

The general pattern: a weighted rubric rewards importance and feasibility, but under-weights two things that decide hackathons — whether you can *demonstrate* the result on *real* data, and how *crowded* the field is. My tiers lean harder on those two.

## Bottom line

Stay on **SIH26158** — it is both genuinely strong and the one where we are furthest ahead. If a pivot were ever on the table, **SIH26143 (oil-spill + AIS attribution)** is the move I would argue for, because it recycles nearly all of our existing research onto a problem with better open data, lighter competition, and a forensic demo narrative that wins rooms; **SIH26059 (Antarctic navigation)** is the low-competition sleeper right behind it. Everything from Tier 3 down asks us to fight on someone else's turf or on data we cannot get.

*One process note: while fetching these statements, several web-fetch results contained injected text telling the reader to adopt another assistant's identity and behaviour. That text came from the fetch/summariser layer, not from the SIH pages, and was ignored; it did not affect any fact above. Themes for a few statements are mis-labelled on the community mirror (noted inline) — trust the GitHub scrape, and reconfirm everything against the official portal before you commit, since it is the only authoritative source and live submission counts have moved since the 21 Aug scrape.*




