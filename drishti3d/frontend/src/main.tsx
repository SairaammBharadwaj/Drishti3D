import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './styles.css'
import './design.css'
import Overview from './views/Overview'
import App from './App'
const Dashboard = lazy(() => import('./views/Dashboard'))
const Wizard = lazy(() => import('./views/Wizard'))
const Monitor = lazy(() => import('./views/Monitor'))
const Workspace = lazy(() => import('./views/Workspace'))
const Report = lazy(() => import('./views/Report'))
const Presentation = lazy(() => import('./views/Presentation'))
const Prototype = lazy(() => import('./views/Prototype'))

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Overview /> },
      { path: 'missions', element: <Dashboard /> },
      { path: 'new', element: <Wizard /> },
      { path: 'demo', element: <Presentation /> },
      { path: 'prototype', element: <Prototype /> },
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
