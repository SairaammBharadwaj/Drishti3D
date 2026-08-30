import { NavLink, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Drishti<span>3D</span>
          <small>Single-pass drone video → georeferenced 3D · SIH26158</small>
        </div>
        <nav>
          <NavLink to="/" end>Missions</NavLink>
          <NavLink to="/new">New reconstruction</NavLink>
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
