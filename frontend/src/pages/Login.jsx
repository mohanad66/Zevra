import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'

export default function Login() {
  const { login, apiError } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ email: '', password: '' })
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await login(form.email, form.password)
      toast('Welcome back!', 'success')
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
          <img src="/logo.png" alt="Zevra" className="brand-mark" />
          <h1>Log in to Zevra</h1>
        </div>
        {params.get('invite') && (
          <div className="notice">You were invited — create your account to join.</div>
        )}
        <label>
          Email or phone
          <input type="text" value={form.email} onChange={v('email')} autoComplete="username" placeholder="you@example.com or +1 555 000 1234" required />
        </label>
        <label>
          Password
          <input type="password" value={form.password} onChange={v('password')} autoComplete="current-password" required />
        </label>
        <button className="btn primary lg block" disabled={busy}>
          {busy ? 'Logging in…' : 'Log in'}
        </button>
        <p className="muted center">
          Don&apos;t have an account? <Link to="/register">Create one</Link>
        </p>
      </form>
    </div>
  )
}