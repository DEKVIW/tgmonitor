/**
 * 主应用组件
 */

import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'
import GuestRoute from './components/GuestRoute'
import AnalyticsBootstrap from './components/analytics/AnalyticsBootstrap'
import { LOGIN_LINUXDO_CALLBACK_PATH, LOGIN_PATH } from './utils/routes'

const Login = lazy(() => import('./pages/LoginRuntime'))
const LoginLinuxDoCallback = lazy(() => import('./pages/LoginLinuxDoCallback'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const MediaWallPage = lazy(() => import('./pages/MediaWallPage'))
const Statistics = lazy(() => import('./pages/Statistics'))
const Analytics = lazy(() => import('./pages/AnalyticsDashboardModern'))
const Admin = lazy(() => import('./pages/AdminRuntime'))
const AiCenterAdminRuntime = lazy(() => import('./pages/AiCenterAdminRuntime'))
const Backups = lazy(() => import('./pages/BackupsRuntime'))
const ResourceOperations = lazy(() => import('./pages/ResourceOperationsAdminRuntime'))

function App() {
  // Zustand persist会自动处理localStorage，无需手动恢复

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AnalyticsBootstrap />
      <Suspense fallback={<div className="app-route-loading" role="status">加载中...</div>}>
        <Routes>
          <Route path={LOGIN_PATH} element={<Login />} />
          <Route path={LOGIN_LINUXDO_CALLBACK_PATH} element={<LoginLinuxDoCallback />} />
          {/* 根路径：根据系统配置决定是否允许游客访问 */}
          <Route
            path="/"
            element={
              <GuestRoute>
                <Dashboard />
              </GuestRoute>
            }
          />
          <Route
            path="/popular"
            element={
              <GuestRoute redirectAuthenticated={false}>
                <MediaWallPage />
              </GuestRoute>
            }
          />
          <Route
            path="/popular/category/:categorySlug"
            element={
              <GuestRoute redirectAuthenticated={false}>
                <MediaWallPage />
              </GuestRoute>
            }
          />
          <Route
            path="/popular/item/:itemId"
            element={
              <GuestRoute redirectAuthenticated={false}>
                <MediaWallPage />
              </GuestRoute>
            }
          />
          <Route
            path="/statistics"
            element={
              <GuestRoute redirectAuthenticated={false}>
                <Statistics />
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
            <Route
              path="/analytics"
              element={
                <AdminRoute>
                  <Analytics />
                </AdminRoute>
              }
            />
            <Route
              path="/ai-center"
              element={
                <AdminRoute>
                  <AiCenterAdminRuntime />
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
      </Suspense>
    </BrowserRouter>
  )
}

export default App

