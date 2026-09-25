import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'

export default function Auth({ initialMode = 'login' }) {
  const { login, register, apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [mode, setMode] = useState(initialMode)
  const [contact, setContact] = useState('email')
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
  const identifier = () => (contact === 'phone' ? form.phone.trim() : form.email.trim())

  async function submit(e) {
    e.preventDefault()
    if (!identifier()) {
      toast(
        contact === 'phone' ? t('auth.phone.required') : t('auth.email.required'),
        'error'
      )
      return
    }
    if (mode === 'register' && form.password.trim().length < 8) {
      toast(t('auth.register.tooShort'), 'error')
      return
    }
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(identifier(), form.password)
        toast(t('auth.welcomeBack'), 'success')
      } else {
        await register(form)
        await login(identifier(), form.password)
        toast(t('auth.register.success'), 'success')
      }
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
          <h1>
            {mode === 'login' ? t('auth.login.title') : t('auth.register.title')}
          </h1>
        </div>

        {/* <div className="seg">
          <button
            type="button"
            className={`seg-btn${mode === 'login' ? ' active' : ''}`}
            onClick={() => setMode('login')}
          >
            {t('auth.login.button')}
          </button>
          <button
            type="button"
            className={`seg-btn${mode === 'register' ? ' active' : ''}`}
            onClick={() => setMode('register')}
          >
            {t('auth.register.button')}
          </button>
        </div> */}

        {mode === 'register' && params.get('invite') && (
          <div className="notice">
            {t('auth.register.invited')} <b>{params.get('invite')}</b>.
          </div>
        )}

        {mode === 'register' && (
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
        )}

        <div className="seg">
          <button
            type="button"
            className={`seg-btn${contact === 'email' ? ' active' : ''}`}
            onClick={() => setContact('email')}
          >
            {t('auth.contact.email')}
          </button>
          <button
            type="button"
            className={`seg-btn${contact === 'phone' ? ' active' : ''}`}
            onClick={() => setContact('phone')}
          >
            {t('auth.contact.phone')}
          </button>
        </div>

        {contact === 'email' ? (
          <label>
            {t('auth.email.label')}
            <input
              type="email"
              value={form.email}
              onChange={v('email')}
              autoComplete="email"
            />
          </label>
        ) : (
          <label>
            {t('auth.phone.label')}
            <input
              type="tel"
              value={form.phone}
              onChange={v('phone')}
              autoComplete="tel"
            />
          </label>
        )}
{/* <label>
              <span className="opt">{t('auth.register.email')}</span>
              <input type="email" value={form.email} onChange={v('email')} autoComplete="email" />
            </label> */}
        {mode === 'register' && contact === 'phone' ? (
            <label>
              <span className="opt">{t('auth.register.inviteCode')}</span>
              <input value={form.invite_code} onChange={v('invite_code')} />
            </label>
            
        ) : mode === 'register' ? (
          <label>
            <span className="opt">{t('auth.register.inviteCode')}</span>
            <input value={form.invite_code} onChange={v('invite_code')} />
          </label>
        ) : null}

        {mode === 'register' && (
          <p className="small muted" style={{ margin: '-0.2rem 0 0' }}>
            {t('auth.register.hint')}
          </p>
        )}

        <label>
          {t('auth.login.password')}
          <input
            type="password"
            value={form.password}
            onChange={v('password')}
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            required
            minLength={mode === 'register' ? 8 : undefined}
          />
        </label>

        {mode === 'register' && (
          <p className="small muted">
            {t('auth.register.agreement')}{' '}
            <Link to="/terms">{t('auth.register.terms')}</Link> {t('auth.register.and')}{' '}
            <Link to="/privacy">{t('auth.register.privacy')}</Link>.
          </p>
        )}

        <button className="btn primary lg block" disabled={busy}>
          {busy
            ? mode === 'register'
              ? t('auth.register.busy')
              : t('auth.login.busy')
            : mode === 'register'
              ? t('auth.register.button')
              : t('auth.login.button')}
        </button>
        <p className="muted center">
          {mode === 'login'
            ? t('auth.login.noAccount')
            : t('auth.register.haveAccount')}{' '}
          <button
            type="button"
            className="link-btn"
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login'
              ? t('auth.login.createOne')
              : t('auth.register.login')}
          </button>
        </p>
      </form>
    </div>
  )
}