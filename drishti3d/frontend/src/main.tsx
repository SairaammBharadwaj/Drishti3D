import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './styles.css'
import App from './App'
import Dashboard from './views/Dashboard'
import Wizard from './views/Wizard'
import Monitor from './views/Monitor'
import Workspace from './views/Workspace'
import Report from './views/Report'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'new', element: <Wizard /> },
      { path: 'projects/:id', element: <Workspace /> },
      { path: 'projects/:id/monitor', element: <Monitor /> },
      { path: 'projects/:id/report', element: <Report /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
