import { Link } from 'react-router-dom'
import ScenePreview from '../ScenePreview'

const steps = [
  { n: '01', title: 'Start with a single pass.', text: 'Bring your drone footage. Add telemetry and camera information when available to support scale and alignment.', tag: 'VIDEO + OPTIONAL TELEMETRY' },
  { n: '02', title: 'Recover the scene.', text: 'Select useful frames, recover camera positions, and reconstruct geometry. Keep observed and inferred surfaces distinguishable.', tag: 'FRAMES → CAMERAS → GEOMETRY' },
  { n: '03', title: 'Interrogate the evidence.', text: 'Explore the model, ask measurement questions, inspect their support, and export the available results.', tag: 'INSPECT + MEASURE + EXPORT' },
]

export default function Overview() {
  return <div className="overview">
    <section className="landing-hero">
      <div className="hero-copy"><div className="eyebrow"><span className="tiny-cross">+</span> FROM AERIAL FOOTAGE TO SPATIAL UNDERSTANDING</div>
        <h1>A new dimension<br />of <em>perspective.</em></h1>
        <p>One drone pass. A scene you can explore.<br className="desktop-break" /> Turn video into 3D geometry, then see the evidence behind every measurement.</p>
        <div className="hero-actions"><Link className="action primary-action" to="/new">Start a reconstruction <span aria-hidden="true">↗</span></Link><a className="text-action" href="#how-it-works">Explore the workflow <span aria-hidden="true">↓</span></a></div>
        <div className="hero-note"><span className="outline-cube" aria-hidden="true">◇</span><span>Built for a closer look.<br /><strong>Designed to make uncertainty visible.</strong></span></div>
      </div>
      <div className="hero-visual"><ScenePreview /><div className="visual-footnote"><span>REAL GEOMETRY. RESEARCH EXAMPLE.</span><Link to="/prototype">Explore full scene ↗</Link></div></div>
    </section>
    <div className="principles-strip"><span className="eyebrow">A DIFFERENT VIEW OF THE GROUND</span><span>Single-pass input</span><span>Traceable geometry</span><span>Evidence-aware measurements</span></div>
    <section className="story-section" id="how-it-works">
      <div className="section-heading"><div><div className="eyebrow">01 / THE WORKFLOW</div><h2>From seeing a place<br />to understanding its shape.</h2></div><p>Footage is the starting point.<br />The real value is what you can ask of it.</p></div>
      <div className="workflow-grid">{steps.map(s => <article key={s.n} className="workflow-card"><span className="step-number">{s.n}</span><div className={`step-art art-${s.n}`} aria-hidden="true">{Array.from({length: 5}, (_, i) => <i key={i} />)}</div><h3>{s.title}</h3><p>{s.text}</p><span className="eyebrow">{s.tag}</span></article>)}</div>
    </section>
    <section className="evidence-section">
      <div className="evidence-visual" aria-hidden="true"><span className="eyebrow">THE EVIDENCE LAYER / CONCEPT DIAGRAM</span><svg viewBox="0 0 420 285" fill="none"><defs><pattern id="evidence-grid" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#384239" /></pattern></defs><rect width="420" height="285" fill="url(#evidence-grid)"/><path d="m75 175 130-72 140 70-132 75Z" fill="#172b20" stroke="#b7e773"/><path d="M75 175v-55l130-73v56M75 120l138 72 132-74v55M213 192v56M205 47l140 71" stroke="#b7e773"/><path d="m205 47 0 56 140 70v-55Z" fill="#a391c1" fillOpacity=".15" stroke="#a391c1" strokeDasharray="5 5"/><path d="m110 209 103 54 97-52" stroke="#8a978a"/><circle cx="110" cy="209" r="4" fill="#b7e773"/><circle cx="310" cy="211" r="4" fill="#b7e773"/></svg><div className="evidence-key"><span><i className="key-measured" /> Observed</span><span><i className="key-inferred" /> AI-assisted</span><span><i className="key-unknown" /> Unknown</span></div></div>
      <div className="evidence-copy"><div className="eyebrow">02 / BEYOND A GOOD-LOOKING MODEL</div><h2>A model should show<br />what it <em>knows.</em></h2><p>A convincing surface is only part of the story. Drishti3D separates observed geometry from AI-assisted estimates, so you can inspect where a result comes from.</p><ul className="evidence-list"><li><span>01</span><div><strong>Inspect the source</strong><p>Review frames, camera coverage, and reconstruction quality.</p></div></li><li><span>02</span><div><strong>Ask with a requirement</strong><p>Use the Tolerance Lens to compare a measurement with the precision you need.</p></div></li><li><span>03</span><div><strong>Keep the limits in view</strong><p>Relative scale, inferred geometry, and missing observations remain visible.</p></div></li></ul><Link className="text-action" to="/missions">Open the mission library <span aria-hidden="true">↗</span></Link></div>
    </section>
    <section className="story-section example-section"><div className="section-heading"><div><div className="eyebrow">03 / INSIDE A RECONSTRUCTION</div><h2>See the source.<br />Explore the result.</h2></div><div><p>Gymnasium Neubiberg · saved research example.<br />Video-only input, with relative scale.</p><Link className="text-action" to="/prototype">Open interactive reconstruction ↗</Link></div></div><div className="example-video"><video controls playsInline preload="none" poster="/showcase/comparison.jpg" aria-label="Recorded drone footage and reconstruction comparison"><source src="/prototype/reference.mp4" type="video/mp4" /><a href="/prototype/reference.mp4">Download the recorded example</a></video><div className="example-caption"><strong>A research result you can inspect.</strong><span>Includes AI-assisted densification. This example does not establish distances in metres or geographic position.</span></div></div><p className="asset-credit">Source footage: Gymnasium Neubiberg, Wikimedia Commons (CC BY-SA). Reconstruction and comparison generated by Drishti3D. Counts and appearance in this example are not a performance guarantee.</p></section>
    <section className="landing-cta"><div><div className="eyebrow">YOUR NEXT PERSPECTIVE STARTS HERE</div><h2>Bring the footage.<br /><em>Ask more of it.</em></h2></div><Link className="action primary-action" to="/new">Create your first mission <span aria-hidden="true">↗</span></Link></section>
    <footer className="site-footer"><Link to="/">drishti<span>3D</span></Link><span>Single-pass 3D reconstruction · SIH26158</span><span>Research preview</span><a href="#main-content">Back to top ↑</a></footer>
  </div>
}
