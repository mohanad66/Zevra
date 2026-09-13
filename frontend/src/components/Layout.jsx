import { NavLink, Outlet } from 'react-router-dom'
import { LineChart, TrendingUp, ArrowDownToLine, Users, UserCircle, LogOut, Home, Shield } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: Home },
  { to: '/market', label: 'Market', icon: LineChart },
  { to: '/invest', label: 'Invest', icon: TrendingUp },
  { to: '/withdraw', label: 'Withdraw', icon: ArrowDownToLine },
  { to: '/referrals', label: 'Referrals', icon: Users },
  { to: '/profile', label: 'Profile', icon: UserCircle },
]

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/dashboard" className="brand">
          <img src="/logo.png" alt="Zevra" className="brand-mark" />
          <span className="brand-name">zevra</span>
        </NavLink>
        <nav className="topnav">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? 'navlink active' : 'navlink')}>
              {l.label}
            </NavLink>
          ))}
          {user?.is_staff && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? 'navlink active' : 'navlink')}>
              Admin
            </NavLink>
          )}
        </nav>
        <div className="topbar-right">
          <NavLink to="/profile" className="avatar-chip">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="avatar" />
            ) : (
              <span className="avatar-fallback">{user?.email?.[0]?.toUpperCase() || 'U'}</span>
            )}
            <span className="uname">{user?.full_name || user?.email}</span>
          </NavLink>
          <button className="icon-btn" title="Logout" onClick={() => logout()}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>

      <nav className="bottomnav">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? 'bn-link active' : 'bn-link')}>
            <l.icon size={20} />
            <span>{l.label}</span>
          </NavLink>
        ))}
        {user?.is_staff && (
          <NavLink to="/admin" className={({ isActive }) => (isActive ? 'bn-link active' : 'bn-link')}>
            <Shield size={20} />
            <span>Admin</span>
          </NavLink>
        )}
      </nav>

      <footer className="footer">
        <NavLink to="/terms">Terms of Service</NavLink>
        <span>·</span>
        <NavLink to="/privacy">Privacy Policy</NavLink>
        <span>·</span>
        <NavLink to="/kyc-policy">AML / KYC Policy</NavLink>
      </footer>
    </div>
  )
}