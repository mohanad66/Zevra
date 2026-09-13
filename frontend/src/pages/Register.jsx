import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'

export default function Register() {
  const { register, login, apiError } = useAuth()
  const { toast } = useToast()
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
      toast('Provide an email address or a phone number to create an account.', 'error')
      return
    }
    setBusy(true)
    try {
      await register(form)
      await login(form.email.trim() || form.phone.trim(), form.password)
      toast('Account created. Welcome to Zevra!', 'success')
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
          <img src="/logo.png" alt="Zevra" className="brand-mark" />
          <h1>Create your account</h1>
        </div>
        {params.get('invite') && (
          <div className="notice">You were invited with code <b>{params.get('invite')}</b>.</div>
        )}
        <div className="row2">
          <label>
            First name
            <input value={form.first_name} onChange={v('first_name')} autoComplete="given-name" />
          </label>
          <label>
            Last name
            <input value={form.last_name} onChange={v('last_name')} autoComplete="family-name" />
          </label>
        </div>
        <label>
          <span className="opt">Email (enter it or a phone number)</span>
          <input type="email" value={form.email} onChange={v('email')} autoComplete="email" />
        </label>
        <div className="row2">
          <label>
            <span className="opt">Phone (optional)</span>
            <input value={form.phone} onChange={v('phone')} autoComplete="tel" />
          </label>
          <label>
            <span className="opt">Invite code (optional)</span>
            <input value={form.invite_code} onChange={v('invite_code')} />
          </label>
        </div>
        <p className="small muted" style={{ margin: '-0.2rem 0 0' }}>
          Create the account using your email <em>or</em> just your phone number — you can then log in with either.
        </p>
        <label>
          Password
          <input type="password" value={form.password} onChange={v('password')} autoComplete="new-password" required minLength={8} />
        </label>
        <p className="small muted">
          By creating an account you agree to our{' '}
          <Link to="/terms">Terms of Service</Link> and <Link to="/privacy">Privacy Policy</Link>.
        </p>
        <button className="btn primary lg block" disabled={busy}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
        <p className="muted center">
          Already registered? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  )
}