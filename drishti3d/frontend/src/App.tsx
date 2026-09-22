import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

export default function App() {
  const [menu, setMenu] = useState(false)
  const location = useLocation()
  const main = useRef<HTMLElement>(null)
  useEffect(() => { setMenu(false); main.current?.scrollTo(0, 0) }, [location.pathname])
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="Drishti3D home">
          <svg className="brand-mark" viewBox="0 0 32 36" fill="none" aria-hidden="true"><path d="M16 2 30 10v16L16 34 2 26V10L16 2Z" stroke="currentColor" strokeWidth="1.5"/><path d="m2 10 14 8 14-8M16 18v16M9 14v8l7 4 7-4v-8" stroke="currentColor" strokeWidth="1.5"/></svg>
          <span className="brand-word">drishti<span>3D</span><small>SPATIAL INTELLIGENCE</small></span>
        </Link>
        <button className="menu-toggle" aria-expanded={menu} aria-controls="main-nav" onClick={() => setMenu(!menu)}>{menu ? 'Close' : 'Menu'}</button>
        <nav id="main-nav" className={menu ? 'nav-open' : ''} aria-label="Main navigation">
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/missions">Missions</NavLink>
          <NavLink to="/demo">Showcase</NavLink>
          <NavLink to="/prototype">Research lab <span aria-hidden="true">↗</span></NavLink>
          <NavLink to="/new" className="nav-create">New reconstruction <span aria-hidden="true">+</span></NavLink>
        </nav>
      </header>
      <main ref={main} id="main-content" className="content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
