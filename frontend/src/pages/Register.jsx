import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'

export default function Register() {
  const { register, login, apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    invite_code: params.get('invite') || '',
    password: '',
  })
  const [busy, setBusy] = useState(false)

  const v = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    if (!form.email.trim() && !form.phone.trim()) {
      toast(t('auth.register.needLogin'), 'error')
      return
    }
    if (form.password.trim().length < 8) {
      toast(t('auth.register.tooShort'), 'error')
      return
    }
    setBusy(true)
    try {
      await register(form)
      await login(form.email.trim() || form.phone.trim(), form.password)
      toast(t('auth.register.success'), 'success')
      navigate('/dashboard')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <img src="/logo.png" alt="Miyar Trading" className="brand-mark" />
          <h1>{t('auth.register.title')}</h1>
        </div>
        {params.get('invite') && (
          <div className="notice">{t('auth.register.invited')} <b>{params.get('invite')}</b>.</div>
        )}
        <div className="row2">
          <label>
            {t('auth.register.firstName')}
            <input value={form.first_name} onChange={v('first_name')} autoComplete="given-name" />
          </label>
          <label>
            {t('auth.register.lastName')}
            <input value={form.last_name} onChange={v('last_name')} autoComplete="family-name" />
          </label>
        </div>
        <label>
          <span className="opt">{t('auth.register.email')}</span>
          <input type="email" value={form.email} onChange={v('email')} autoComplete="email" />
        </label>
        <div className="row2">
          <label>
            <span className="opt">{t('auth.register.phone')}</span>
            <input value={form.phone} onChange={v('phone')} autoComplete="tel" />
          </label>
          <label>
            <span className="opt">{t('auth.register.inviteCode')}</span>
            <input value={form.invite_code} onChange={v('invite_code')} />
          </label>
        </div>
        <p className="small muted" style={{ margin: '-0.2rem 0 0' }}>
          {t('auth.register.hint')}
        </p>
        <label>
          {t('auth.register.password')}
          <input type="password" value={form.password} onChange={v('password')} autoComplete="new-password" required minLength={8} />
        </label>
        <p className="small muted">
          {t('auth.register.agreement')}{' '}
          <Link to="/terms">{t('auth.register.terms')}</Link> {t('auth.register.and')}{' '}
          <Link to="/privacy">{t('auth.register.privacy')}</Link>.
        </p>
        <button className="btn primary lg block" disabled={busy}>
          {busy ? t('auth.register.busy') : t('auth.register.button')}
        </button>
        <p className="muted center">
          {t('auth.register.haveAccount')} <Link to="/login">{t('auth.register.login')}</Link>
        </p>
      </form>
    </div>
  )
}