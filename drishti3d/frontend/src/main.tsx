import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './styles.css'
import './design.css'
import Overview from './views/Overview'
import App from './App'
import { useReadOnly } from './deployment'
const Dashboard = lazy(() => import('./views/Dashboard'))
const Wizard = lazy(() => import('./views/Wizard'))
const Monitor = lazy(() => import('./views/Monitor'))
const Workspace = lazy(() => import('./views/Workspace'))
const Report = lazy(() => import('./views/Report'))
const Presentation = lazy(() => import('./views/Presentation'))
const Prototype = lazy(() => import('./views/Prototype'))

// The research lab is built from the Gymnasium footage (Wikimedia Commons,
// CC BY-SA, author not recorded), which a public showcase cannot credit yet;
// its assets are left out of the showcase image (deploy/showcase/Dockerfile).
function ResearchLab() {
  const readOnly = useReadOnly()
  if (readOnly === null) return null
  if (readOnly) return <div className="library"><div className="empty-state"><h2>The research lab is not part of this showcase.</h2><p>It is built from footage that can't be credited here yet.</p></div></div>
  return <Prototype />
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Overview /> },
      { path: 'missions', element: <Dashboard /> },
      { path: 'new', element: <Wizard /> },
      { path: 'demo', element: <Presentation /> },
      { path: 'prototype', element: <ResearchLab /> },
      { path: 'projects/:id/demo', element: <Presentation /> },
      { path: 'projects/:id', element: <Workspace /> },
      { path: 'projects/:id/monitor', element: <Monitor /> },
      { path: 'projects/:id/report', element: <Report /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Suspense fallback={<div className="container" role="status">Opening your workspace…</div>}><RouterProvider router={router} /></Suspense>
  </React.StrictMode>,
)
