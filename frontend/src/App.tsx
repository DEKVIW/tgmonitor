/**
 * 主应用组件
 */

import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'
import GuestRoute from './components/GuestRoute'
import AnalyticsBootstrap from './components/analytics/AnalyticsBootstrap'
import PublicDashboardToolbar from './components/messages/PublicDashboardToolbar'
import Login from './pages/LoginRuntime'
import LoginLinuxDoCallback from './pages/LoginLinuxDoCallback'
import Dashboard from './pages/Dashboard'
import Statistics from './pages/Statistics'
import Analytics from './pages/AnalyticsDashboardModern'
import Admin from './pages/AdminRuntime'
import Backups from './pages/BackupsRuntime'
import ResourceOperations from './pages/ResourceOperationsAdmin'
import { LOGIN_LINUXDO_CALLBACK_PATH, LOGIN_PATH } from './utils/routes'

function App() {
  // Zustand persist会自动处理localStorage，无需手动恢复

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AnalyticsBootstrap />
      <Routes>
        <Route path={LOGIN_PATH} element={<Login />} />
        <Route path={LOGIN_LINUXDO_CALLBACK_PATH} element={<LoginLinuxDoCallback />} />
        {/* 根路径：根据系统配置决定是否允许游客访问 */}
        <Route
          path="/"
          element={
            <GuestRoute toolbar={<PublicDashboardToolbar />}>
              <Dashboard />
            </GuestRoute>
          }
        />
        {/* 登录用户的dashboard路径 */}
        <Route
          element={
            <ProtectedRoute>
              <Layout>
                <Outlet />
              </Layout>
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/statistics" element={<Statistics />} />
          <Route
            path="/analytics"
            element={
              <AdminRoute>
                <Analytics />
              </AdminRoute>
            }
          />
          <Route
            path="/resource-ops"
            element={
              <AdminRoute>
                <ResourceOperations />
              </AdminRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <Admin />
              </AdminRoute>
            }
          />
          <Route
            path="/backups"
            element={
              <AdminRoute>
                <Backups />
              </AdminRoute>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

