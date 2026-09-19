import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'

export default function Login() {
  const { login, apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ email: '', password: '' })
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await login(form.email, form.password)
      toast(t('auth.welcomeBack'), 'success')
      navigate('/dashboard')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const v = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <img src="/logo.png" alt="Miyar Trading" className="brand-mark" />
          <h1>{t('auth.login.title')}</h1>
        </div>
        {params.get('invite') && (
          <div className="notice">{t('auth.login.invited')}</div>
        )}
        <label>
          {t('auth.login.emailOrPhone')}
          <input type="text" value={form.email} onChange={v('email')} autoComplete="username" placeholder="you@example.com or +1 555 000 1234" required />
        </label>
        <label>
          {t('auth.login.password')}
          <input type="password" value={form.password} onChange={v('password')} autoComplete="current-password" required />
        </label>
        <button className="btn primary lg block" disabled={busy}>
          {busy ? t('auth.login.busy') : t('auth.login.button')}
        </button>
        <p className="muted center">
          {t('auth.login.noAccount')} <Link to="/register">{t('auth.login.createOne')}</Link>
        </p>
      </form>
    </div>
  )
}