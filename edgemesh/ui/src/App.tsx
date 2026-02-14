import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useNodesRealtime } from './hooks/useNodesRealtime'
import DashboardPage from './pages/DashboardPage'
import DeviceDetailPage from './pages/DeviceDetailPage'
import DevicesPage from './pages/DevicesPage'
import JobsPage from './pages/JobsPage'
import SettingsPage from './pages/SettingsPage'

function Layout() {
  const { connectionMode } = useNodesRealtime()

  return (
    <div className="app-shell">
      <header className="top-nav">
        <nav>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/devices">Devices</NavLink>
          <NavLink to="/jobs">Jobs</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <small>Data channel: {connectionMode}</small>
      </header>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/devices/:nodeId" element={<DeviceDetailPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
