/**
 * 主应用组件
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'
import GuestRoute from './components/GuestRoute'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Statistics from './pages/Statistics'
import Admin from './pages/Admin'

function App() {
  // Zustand persist会自动处理localStorage，无需手动恢复

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<Login />} />
        {/* 根路径：根据系统配置决定是否允许游客访问 */}
        <Route
          path="/"
          element={
            <GuestRoute>
              <Dashboard />
            </GuestRoute>
          }
        />
        {/* 登录用户的dashboard路径 */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Layout>
                <Dashboard />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/statistics"
          element={
            <ProtectedRoute>
              <Layout>
                <Statistics />
              </Layout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <Layout>
                <Admin />
              </Layout>
            </AdminRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

