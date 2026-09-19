import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastProvider } from './components/Toast'
import { I18nProvider, useI18n } from './i18n'
import ErrorBoundary from './components/ErrorBoundary'
import Seo from './components/Seo'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import { LoaderCircle } from 'lucide-react'

const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const WalletDetail = lazy(() => import('./pages/WalletDetail'))
const Market = lazy(() => import('./pages/Market'))
const Invest = lazy(() => import('./pages/Invest'))
const Withdraw = lazy(() => import('./pages/Withdraw'))
const Payouts = lazy(() => import('./pages/Payouts'))
const Referrals = lazy(() => import('./pages/Referrals'))
const Profile = lazy(() => import('./pages/Profile'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const Terms = lazy(() => import('./pages/Terms'))
const Privacy = lazy(() => import('./pages/Privacy'))
const KycPolicy = lazy(() => import('./pages/KycPolicy'))

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
  const { t } = useI18n()
  return (
    <div className="loader">
      <LoaderCircle size={36} className="spin" />
      <span>{t('common.loading')}</span>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <I18nProvider>
        <AuthProvider>
          <ToastProvider>
            <BrowserRouter>
              <Seo />
              <Suspense fallback={<Loader />}>
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
              </Suspense>
            </BrowserRouter>
          </ToastProvider>
        </AuthProvider>
      </I18nProvider>
    </ErrorBoundary>
  )
}
