import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastProvider } from './components/Toast'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import WalletDetail from './pages/WalletDetail'
import Market from './pages/Market'
import Invest from './pages/Invest'
import Withdraw from './pages/Withdraw'
import Payouts from './pages/Payouts'
import Referrals from './pages/Referrals'
import Profile from './pages/Profile'
import AdminPage from './pages/AdminPage'
import Terms from './pages/Terms'
import Privacy from './pages/Privacy'
import KycPolicy from './pages/KycPolicy'
import { LoaderCircle } from 'lucide-react'

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <Loader />
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Loader />
  if (user) return <Navigate to="/dashboard" replace />
  return children
}

function StaffOnly() {
  const { user, loading } = useAuth()
  if (loading) return <Loader />
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_staff) return <Navigate to="/dashboard" replace />
  return <Outlet />
}

function Loader() {
  return (
    <div className="loader">
      <LoaderCircle size={36} className="spin" />
      <span>Loading…</span>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<PublicOnly><Landing /></PublicOnly>} />
            <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
            <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/kyc-policy" element={<KycPolicy />} />
            <Route element={<Protected />}>
              <Route element={<Layout />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/wallet/:coinId" element={<WalletDetail />} />
                <Route path="/market" element={<Market />} />
                <Route path="/invest" element={<Invest />} />
                <Route path="/withdraw" element={<Withdraw />} />
                <Route path="/payouts" element={<Payouts />} />
                <Route path="/referrals" element={<Referrals />} />
                <Route path="/profile" element={<Profile />} />
              </Route>
              <Route element={<StaffOnly />}>
                <Route element={<Layout />}>
                  <Route path="/admin" element={<AdminPage />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  )
}