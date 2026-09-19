import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, Link, useNavigate } from 'react-router-dom'
import { LineChart, TrendingUp, ArrowDownToLine, Users, UserCircle, LogOut, Home, Shield, Bell, Globe } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n'
import { client } from '../api/client'

function useNavLabels(t) {
  return [
    { to: '/dashboard', label: t('nav.dashboard'), icon: Home },
    { to: '/market', label: t('nav.market'), icon: LineChart },
    { to: '/invest', label: t('nav.invest'), icon: TrendingUp },
    { to: '/withdraw', label: t('nav.withdraw'), icon: ArrowDownToLine },
    { to: '/referrals', label: t('nav.referrals'), icon: Users },
    { to: '/profile', label: t('nav.profile'), icon: UserCircle },
  ]
}

function NotificationBell() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const [items, setItems] = useState([])
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef(null)

  const load = () => {
    Promise.all([
      client.get('/notifications/', { params: { limit: 20 } }),
      client.get('/notifications/unread-count/'),
    ])
      .then(([list, cnt]) => {
        setItems(list.data ?? [])
        setCount(cnt.data?.count ?? 0)
      })
      .catch(() => {})
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!open) return
    setLoading(true)
    client
      .post('/notifications/read/', {})
      .then(() => {
        setCount(0)
        setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const clickTarget = (n) => {
    setOpen(false)
    if (n.link) navigate(n.link)
  }

  return (
    <div className="notif-wrap" ref={boxRef}>
      <button className="icon-btn" title={t('nav.notifications')} onClick={() => setOpen((v) => !v)}>
        <Bell size={18} />
        {count > 0 && <span className="notif-badge">{count > 99 ? '99+' : count}</span>}
      </button>
      {open && (
        <div className="notif-panel">
          <div className="notif-head">
            <strong>{t('nav.notifications')}</strong>
            {loading && <span className="muted small">…</span>}
          </div>
          <div className="notif-list">
            {items.length === 0 ? (
              <p className="muted small pad">{t('nav.noNotifications')}</p>
            ) : (
              items.map((n) => (
                <button key={n.id} type="button" className="notif-item" onClick={() => clickTarget(n)}>
                  <span className={`notif-dot ${n.is_read ? 'read' : ''}`} />
                  <div>
                    <b>{n.title}</b>
                    {n.body && <p>{n.body}</p>}
                    <span className="muted small">
                      {new Date(n.created_at).toLocaleString()}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
          <Link to="/profile" className="notif-foot" onClick={() => setOpen(false)}>
            <Users size={14} /> {t('nav.notifFoot')}
          </Link>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { lang, t, changeLang } = useI18n()
  const links = useNavLabels(t)

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/dashboard" className="brand">
          <img src="/logo.png" alt="Miyar Trading" className="brand-mark" />
          <span className="brand-name">Miyar Trading</span>
        </NavLink>
        <nav className="topnav">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? 'navlink active' : 'navlink')}>
              {l.label}
            </NavLink>
          ))}
          {user?.is_staff && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? 'navlink active' : 'navlink')}>
              {t('nav.admin')}
            </NavLink>
          )}
        </nav>
        <div className="topbar-right">
          <button className="icon-btn lang-btn" title={t('nav.language')} onClick={() => changeLang(lang === 'ar' ? 'en' : 'ar')}>
            <Globe size={18} />
            <span className="lang-label">{lang === 'ar' ? 'EN' : 'عربي'}</span>
          </button>
          <NotificationBell />
          <NavLink to="/profile" className="avatar-chip">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="avatar" />
            ) : (
              <span className="avatar-fallback">{user?.email?.[0]?.toUpperCase() || 'U'}</span>
            )}
            <span className="uname">{user?.full_name || user?.email}</span>
          </NavLink>
          <button className="icon-btn" title={t('nav.logout')} onClick={() => logout()}>
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
            <span>{t('nav.admin')}</span>
          </NavLink>
        )}
      </nav>

      <footer className="footer">
        <NavLink to="/terms">{t('nav.terms')}</NavLink>
        <span>·</span>
        <NavLink to="/privacy">{t('nav.privacy')}</NavLink>
        <span>·</span>
        <NavLink to="/kyc-policy">{t('nav.kycPolicy')}</NavLink>
      </footer>
    </div>
  )
}