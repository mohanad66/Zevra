import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { fmt, fmtCrypto, StatusBadge } from '../components/Format'
import {
  Shield, Clock, Users, Search, Coins, Plus, X, Check, Lock, Unlock,
  Ban, Wallet, PlugZap, Trash2, ListOrdered, RefreshCw, Eye,
} from 'lucide-react'

const MODES = ['simulate', 'provider', 'manual']

export default function AdminPage() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const [tab, setTab] = useState('windows')
  const [windows, setWindows] = useState([])
  const [users, setUsers] = useState([])
  const [coins, setCoins] = useState([])
  const [q, setQ] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [formBusy, setFormBusy] = useState(false)
  const [form, setForm] = useState({ title: '', percent: '10', coin: '', duration_hours: '48', target_mode: 'all', target_emails: '' })
  const [percentDraft, setPercentDraft] = useState({})

  const [pickWindow, setPickWindow] = useState(null)
  const [pickUsers, setPickUsers] = useState([])
  const [pickSel, setPickSel] = useState(new Set())
  const [pickQ, setPickQ] = useState('')
  const [pickBusy, setPickBusy] = useState(false)

  const [balanceUser, setBalanceUser] = useState(null)
  const [banUser, setBanUser] = useState(null)
  const [deleteUser, setDeleteUser] = useState(null)
  const [modal, setModal] = useState({})
  const [modalBusy, setModalBusy] = useState(false)

  const [kycList, setKycList] = useState([])
  const [kycStatus, setKycStatus] = useState('pending')
  const [kycBusy, setKycBusy] = useState(false)

  const [pay, setPay] = useState({ payment_mode: 'simulate', provider: {}, platform_wallets: [] })
  const [providerForm, setProviderForm] = useState({ provider_url: '', provider_key: '', store_id: '', webhook_token: '', callback_url: '', success_url: '' })
  const [walletForm, setWalletForm] = useState({ wallet_coin_id: '', wallet_address: '', wallet_label: 'Platform wallet' })
  const [streetBusy, setStreetBusy] = useState(false)
  const [testResult, setTestResult] = useState('')

  const [orders, setOrders] = useState([])
  const [orderStatus, setOrderStatus] = useState('all')
  const [ordersBusy, setOrdersBusy] = useState(false)

  async function loadWindows() {
    try {
      const res = await client.get('/admin/payout-windows/')
      setWindows(res.data)
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function loadUsers() {
    try {
      const res = await client.get('/admin/users/', { params: q ? { q } : {} })
      setUsers(res.data)
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function loadKyc() {
    setKycBusy(true)
    try {
      const res = await client.get('/admin/kyc/', { params: { status: kycStatus } })
      setKycList(res.data)
    } catch (err) { toast(apiError(err), 'error') }
    finally { setKycBusy(false) }
  }

  async function loadPayments() {
    try {
      const res = await client.get('/admin/payments/')
      setPay(res.data)
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function loadOrders() {
    setOrdersBusy(true)
    try {
      const params = orderStatus === 'all' ? {} : { status: orderStatus }
      const res = await client.get('/admin/orders/', { params })
      setOrders(res.data)
    } catch (err) { toast(apiError(err), 'error') }
    finally { setOrdersBusy(false) }
  }

  useEffect(() => {
    client.get('/coins/').then((r) => setCoins(r.data)).catch(() => {})
    loadWindows()
    loadUsers()
    loadKyc()
    loadPayments()
    loadOrders()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const t = setTimeout(loadUsers, 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => { loadKyc() }, [kycStatus])

  useEffect(() => { loadOrders() }, [orderStatus])

  async function createWindow(e) {
    e.preventDefault()
    setFormBusy(true)
    try {
      const payload = {
        title: form.title,
        percent: parseFloat(form.percent),
        duration_hours: parseInt(form.duration_hours, 10),
        target_mode: form.target_mode,
      }
      if (form.coin) payload.coin = parseInt(form.coin, 10)
      if (form.target_mode === 'specific' && form.target_emails.trim()) {
        payload.target_emails = form.target_emails.split(',').map((e) => e.trim()).filter(Boolean)
      }
      await client.post('/admin/payout-windows/', payload)
      toast('Window created', 'success')
      setForm({ title: '', percent: '10', coin: '', duration_hours: '48', target_mode: 'all', target_emails: '' })
      setCreateOpen(false)
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setFormBusy(false) }
  }

  async function toggleWindow(id, active) {
    try {
      const res = await client.post(`/admin/payout-windows/${id}/toggle/`, { active })
      toast(res.data.message, 'success')
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function savePercent(id) {
    try {
      const val = parseFloat(percentDraft[id])
      if (Number.isNaN(val) || val <= 0) {
        toast('Enter a positive percent', 'error')
        return
      }
      const res = await client.post(`/admin/payout-windows/${id}/toggle/`, { percent: val })
      toast(res.data.message, 'success')
      setPercentDraft((p) => { const n = { ...p }; delete n[id]; return n })
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function openWindow(id, ids = []) {
    setPickBusy(true)
    try {
      const res = await client.post(`/admin/payout-windows/${id}/toggle/`, {
        active: true,
        target_user_ids: ids,
      })
      toast(res.data.message, 'success')
      setPickWindow(null)
      setPickSel(new Set())
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setPickBusy(false) }
  }

  function openPicker(w) {
    setPickWindow(w)
    setPickSel(new Set(w.target_users || []))
    setPickQ('')
    client.get('/admin/users/')
      .then((res) => setPickUsers(res.data))
      .catch((err) => toast(apiError(err), 'error'))
  }

  function togglePick(id) {
    setPickSel((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function userAction(id, action, extra = {}) {
    try {
      const res = await client.post(`/admin/users/${id}/action/`, { action, ...extra })
      toast(res.data.message, 'success')
      loadUsers()
      setBalanceUser(null)
      setBanUser(null)
      setDeleteUser(null)
      setModal({})
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function submitBalance(e) {
    e.preventDefault()
    setModalBusy(true)
    try {
      await client.post(`/admin/users/${balanceUser.id}/balance/`, {
        coin_id: modal.coin_id,
        invested_delta: modal.invested_delta || '0',
        withdrawable_delta: modal.withdrawable_delta || '0',
        note: modal.note || '',
      })
      toast('Balance updated', 'success')
      setBalanceUser(null)
      setModal({})
      loadUsers()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setModalBusy(false) }
  }

  async function submitBan(e) {
    e.preventDefault()
    setModalBusy(true)
    try {
      await userAction(banUser.id, 'ban', { hours: parseInt(modal.hours, 10) || 0 })
    } catch (err) { toast(apiError(err), 'error') }
    finally { setModalBusy(false) }
  }

  async function submitDelete(e) {
    e.preventDefault()
    setModalBusy(true)
    try {
      await userAction(deleteUser.id, 'delete', { confirm: modal.confirm || '' })
    } catch (err) { toast(apiError(err), 'error') }
    finally { setModalBusy(false) }
  }

  async function reviewKyc(id, action) {
    let body = { action }
    if (action === 'reject') {
      const reason = window.prompt('Reason for rejection:')
      if (reason === null) return
      body.reason = reason
    }
    try {
      const res = await client.post(`/admin/kyc/${id}/review/`, body)
      toast(res.data.message, 'success')
      loadKyc()
      loadUsers()
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function saveMode(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', { payment_mode: pay.payment_mode })
      toast('Payment mode saved', 'success')
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setStreetBusy(false) }
  }

  async function saveProvider(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', providerForm)
      toast('Provider settings saved', 'success')
      setProviderForm({ provider_url: '', provider_key: '', store_id: '', webhook_token: '', callback_url: '', success_url: '' })
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setStreetBusy(false) }
  }

  async function addWallet(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', walletForm)
      toast('Platform wallet saved', 'success')
      setWalletForm({ wallet_coin_id: '', wallet_address: '', wallet_label: 'Platform wallet' })
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setStreetBusy(false) }
  }

  async function deleteWallet(id) {
    try {
      const res = await client.delete(`/admin/payments/wallets/${id}/`)
      toast(res.data.message, 'success')
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function testConnection() {
    setTestResult('')
    try {
      const res = await client.post('/admin/payments/test/', {})
      toast(res.data.message, res.data.ok ? 'success' : 'error')
      setTestResult(`${res.data.ok ? 'OK' : 'FAILED'} — ${res.data.message}`)
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function confirmOrder(id) {
    try {
      const res = await client.post(`/admin/orders/${id}/confirm/`, {})
      toast(res.data.message, 'success')
      loadOrders()
      loadUsers()
    } catch (err) { toast(apiError(err), 'error') }
  }

  const f = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }))
  const pf = (e) => setProviderForm((p) => ({ ...p, [e.target.name]: e.target.value }))
  const wf = (e) => setWalletForm((p) => ({ ...p, [e.target.name]: e.target.value }))
  const mf = (e) => setModal((p) => ({ ...p, [e.target.name]: e.target.value }))

  const openBalance = (u) => {
    const w = (u.wallets && u.wallets[0]) || coins[0]
    setBalanceUser(u)
    setModal({ coin_id: w ? String(w.coin_id) : '', invested_delta: '0', withdrawable_delta: '0', note: '' })
  }

  return (
    <div className="page">
      <div className="page-head">
        <div><h2><Shield size={20} style={{ marginRight: 8, verticalAlign: 'middle' }} />Admin Panel</h2></div>
      </div>

      <div className="tabs" style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button className={`btn ${tab === 'windows' ? 'primary' : 'ghost'}`} onClick={() => setTab('windows')}>
          <Clock size={16} /> Payout Windows
        </button>
        <button className={`btn ${tab === 'users' ? 'primary' : 'ghost'}`} onClick={() => setTab('users')}>
          <Users size={16} /> Users
        </button>
        <button className={`btn ${tab === 'kyc' ? 'primary' : 'ghost'}`} onClick={() => setTab('kyc')}>
          <Check size={16} /> KYC Review
        </button>
        <button className={`btn ${tab === 'payments' ? 'primary' : 'ghost'}`} onClick={() => setTab('payments')}>
          <Wallet size={16} /> Payments
        </button>
      </div>

      {tab === 'windows' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Open / Close Payout Windows</h3>
            <button className="btn primary" onClick={() => setCreateOpen((v) => !v)}>
              {createOpen ? <><X size={16} /> Close</> : <><Coins size={16} /> New Window</>}
            </button>
          </div>

          {createOpen && (
            <form className="card form" onSubmit={createWindow}>
              <label>
                Title
                <input name="title" value={form.title} onChange={f} placeholder="e.g. Summer bonus 10%" required />
              </label>
              <div className="row2">
                <label>
                  Payout percent
                  <input name="percent" type="number" min="0.01" step="0.01" value={form.percent} onChange={f} required />
                </label>
                <label>
                  Duration (hours)
                  <input name="duration_hours" type="number" min="1" value={form.duration_hours} onChange={f} required />
                </label>
              </div>
              <label>
                Coin
                <select name="coin" value={form.coin} onChange={f}>
                  <option value="">All coins</option>
                  {coins.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.symbol})</option>)}
                </select>
              </label>
              <label>
                Target
                <select name="target_mode" value={form.target_mode} onChange={f}>
                  <option value="all">All users with invested balance</option>
                  <option value="specific">Specific users (by email)</option>
                </select>
              </label>
              {form.target_mode === 'specific' && (
                <label>
                  Target emails <span className="muted small">(comma-separated)</span>
                  <textarea name="target_emails" value={form.target_emails} onChange={f} placeholder="user1@example.com, user2@example.com" rows={3} />
                </label>
              )}
              <button className="btn primary lg block" disabled={formBusy} style={{ marginTop: '0.5rem' }}>
                {formBusy ? 'Creating…' : 'Create window'}
              </button>
            </form>
          )}

          {windows.length === 0 && <p className="muted">No payout windows yet.</p>}

          <div className="wallet-grid" style={{ marginTop: createOpen ? '1.5rem' : 0 }}>
            {windows.map((w) => (
              <div key={w.id} className="card" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <strong style={{ fontSize: '1.05rem' }}>{w.title}</strong>
                    <div className="muted small" style={{ marginTop: '0.15rem' }}>
                      {w.coin ? ` · ${w.coin_symbol}` : ' · All coins'} · {w.duration_hours}h
                      {!w.is_open && w.target_mode === 'specific' && w.target_users.length > 0 && (
                        <span style={{ color: 'var(--accent)' }}> · {w.target_users.length} targeted</span>
                      )}
                    </div>
                  </div>
                  <span className={`pill ${w.is_active ? 'pill-active' : ''}`} style={{ background: w.is_active ? 'var(--accent)' : 'var(--muted-bg)', color: w.is_active ? '#fff' : 'var(--muted)', fontSize: '0.75rem' }}>
                    {w.is_active ? 'OPEN' : 'CLOSED'}
                  </span>
                </div>

                <div className="row2" style={{ gap: '0.5rem' }}>
                  <label style={{ margin: 0 }}>
                    Payout %
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={percentDraft[w.id] ?? w.percent}
                      onChange={(e) =>
                        setPercentDraft((p) => ({ ...p, [w.id]: e.target.value }))
                      }
                      style={{ padding: '0.35rem 0.5rem' }}
                    />
                  </label>
                  <button className="btn ghost" style={{ alignSelf: 'flex-end' }} onClick={() => savePercent(w.id)}>
                    <Check size={14} /> Save %
                  </button>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.85rem' }}>
                  <span><Users size={14} style={{ verticalAlign: 'middle' }} /> {w.eligible_count} eligible</span>
                  <span><Check size={14} style={{ verticalAlign: 'middle' }} /> {w.claimed_count} claimed</span>
                  <span><Coins size={14} style={{ verticalAlign: 'middle' }} /> ${fmt(w.total_granted)} paid</span>
                  {w.is_open && <span className="muted"><Clock size={14} style={{ verticalAlign: 'middle' }} /> {Math.round(w.time_left_hours)}h left</span>}
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.2rem', flexWrap: 'wrap' }}>
                  {w.is_active ? (
                    <button className="btn ghost" style={{ color: 'var(--danger, #e44)' }} onClick={() => toggleWindow(w.id, false)}>
                      <Lock size={14} /> Close window
                    </button>
                  ) : (
                    <>
                      <button className="btn primary" onClick={() => openWindow(w.id, [])}>
                        <Users size={14} /> Open for all
                      </button>
                      <button className="btn primary" style={{ background: 'var(--bg)', color: 'var(--text)' }} onClick={() => openPicker(w)}>
                        <Users size={14} /> Open for selected…
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'users' && (
        <div>
          <div style={{ position: 'relative', marginBottom: '1rem' }}>
            <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by email, name, or phone…"
              style={{ paddingLeft: '2.2rem' }}
            />
          </div>
          {users.length === 0 && <p className="muted">No users found.</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {users.map((u) => (
              <div key={u.id} className="card" style={{ padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                  <div>
                    <strong>{u.email}</strong>
                    <div className="muted small">
                      Invested ${fmt(u.total_invested)} · Withdrawable ${fmt(u.total_withdrawable)}
                      {u.is_banned && u.banned_until && <span style={{ color: '#c00', marginLeft: '0.6rem' }}>Banned until {new Date(u.banned_until).toLocaleString()}</span>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    <button className="btn ghost" title="Adjust balances" onClick={() => openBalance(u)}><Coins size={14} /> Balance</button>
                    {u.is_banned ? (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'unban')}><Unlock size={14} /> Unban</button>
                    ) : (
                      <button className="btn ghost" onClick={() => { setBanUser(u); setModal({ hours: '' }) }}><Ban size={14} /> Ban</button>
                    )}
                    {u.is_frozen ? (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'unfreeze')}><Unlock size={14} /> Unfreeze</button>
                    ) : (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'freeze')}><Lock size={14} /> Freeze</button>
                    )}
                    {u.kyc_verified ? (
                      <span className="pill pill-active" style={{ fontSize: '0.75rem', background: 'var(--accent)', color: '#fff' }}>KYC ✓</span>
                    ) : (
                      <>
                        <button className="btn primary" style={{ fontSize: '0.8rem' }} onClick={() => userAction(u.id, 'kyc_approve')}>
                          <Check size={14} /> KYC
                        </button>
                        {u.kyc_rejected && <span className="pill" style={{ fontSize: '0.75rem', background: '#fee', color: '#c00' }}>Rejected</span>}
                      </>
                    )}
                    <button className="btn ghost" style={{ color: '#c00' }} onClick={() => { setDeleteUser(u); setModal({ confirm: '' }) }}>
                      <Trash2 size={14} /> Delete
                    </button>
                  </div>
                </div>
                {u.wallets && u.wallets.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.6rem' }}>
                    {u.wallets.map((w) => (
                      <span key={w.coin_id} className="pill" style={{ fontSize: '0.75rem' }}>
                        {w.symbol} · inv {fmtCrypto(w.invested_balance)} / wd {fmtCrypto(w.withdrawable_balance)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'kyc' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3>KYC Review</h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <select value={kycStatus} onChange={(e) => setKycStatus(e.target.value)}>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="all">All</option>
              </select>
              <button className="btn ghost" onClick={loadKyc} disabled={kycBusy}><RefreshCw size={14} /> Refresh</button>
            </div>
          </div>
          {kycList.length === 0 && <p className="muted">Nothing to review.</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {kycList.map((s) => (
              <div key={s.id} className="card" style={{ padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
                  <div>
                    <strong>{s.user_email}</strong>
                    <div className="muted small">
                      {s.document_type} · {new Date(s.submitted_at).toLocaleString()} · <StatusBadge status={s.status} />
                    </div>
                    {s.status === 'rejected' && s.reason && <div className="muted small" style={{ color: '#c00' }}>Reason: {s.reason}</div>}
                  </div>
                  {s.status === 'pending' && (
                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button className="btn primary" onClick={() => reviewKyc(s.id, 'approve')}><Check size={14} /> Approve</button>
                      <button className="btn ghost" style={{ color: '#c00' }} onClick={() => reviewKyc(s.id, 'reject')}><X size={14} /> Reject</button>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', marginTop: '0.6rem' }}>
                  {[{ label: 'Front', url: s.document_front_url }, { label: 'Back', url: s.document_back_url }, { label: 'Selfie', url: s.selfie_url }]
                    .filter((f) => f.url)
                    .map((f) => (
                      <a key={f.label} href={f.url} target="_blank" rel="noreferrer" className="btn ghost" style={{ fontSize: '0.8rem' }}>
                        <Eye size={14} /> {f.label}
                      </a>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'payments' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>Payment Mode</h3>
            <div className="row2">
              <label>
                Mode
                <select value={pay.payment_mode} onChange={(e) => setPay((p) => ({ ...p, payment_mode: e.target.value }))}>
                  {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <button className="btn primary" style={{ alignSelf: 'flex-end' }} disabled={streetBusy} onClick={saveMode}>
                Save mode
              </button>
            </div>
            <p className="muted small" style={{ marginTop: '0.3rem' }}>
              simulate = auto-credit on confirm · provider = live gateway (webhook) · manual = admin confirms each order.
            </p>
          </div>

          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>Gateway Provider</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              <label>
                BTCPay instance URL <span className="muted small">(no /api/v1; blank keeps, typed blank clears)</span>
                <input name="provider_url" value={providerForm.provider_url} onChange={pf} placeholder={pay.provider.url || 'https://testnet.btcpayserver.org'} />
              </label>
              <label>
                API key <span className="muted small">(BTCPay key — "Authorization: token")</span>
                <input name="provider_key" type="password" value={providerForm.provider_key} onChange={pf} placeholder={pay.provider.key_masked || 'Not set yet'} />
              </label>
              <label>
                Store ID
                <input name="store_id" value={providerForm.store_id} onChange={pf} placeholder={pay.provider.store_id || 'BTCPay store id'} />
              </label>
              <label>
                Webhook token <span className="muted small">(BTCPay webhook secret used to verify BTCPay-Sig)</span>
                <input name="webhook_token" type="password" value={providerForm.webhook_token} onChange={pf} placeholder={pay.provider.webhook_token_masked || 'Not set yet'} />
              </label>
              <label>
                Callback URL <span className="muted small">(public URL webhooks are POSTed to — keep BTCPay's webhook in sync)</span>
                <input name="callback_url" value={providerForm.callback_url} onChange={pf} placeholder={pay.provider.callback_url || 'https://<tunnel>/api/gateway/webhook/'} />
              </label>
              <label>
                Success URL <span className="muted small">(frontend page users land on after paying)</span>
                <input name="success_url" value={providerForm.success_url} onChange={pf} placeholder={pay.provider.success_url || 'http://localhost:5173/login'} />
              </label>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button className="btn primary" disabled={streetBusy} onClick={saveProvider}>Save provider</button>
                <button className="btn ghost" onClick={testConnection}><PlugZap size={14} /> Test connection</button>
              </div>
              {testResult && <p className={`small ${testResult.startsWith('OK') ? 'pos' : 'neg'}`}>{testResult}</p>}
            </div>
          </div>

          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>Platform Deposit Wallets</h3>
            {pay.platform_wallets.length === 0 && <p className="muted small">No platform wallets yet — add each coin address the site deposits to.</p>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginBottom: '0.8rem' }}>
              {pay.platform_wallets.map((w) => (
                <div key={w.id} className="pill" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'space-between', padding: '0.35rem 0.6rem' }}>
                  <span style={{ fontWeight: 600 }}>{w.coin_symbol}</span>
                  <span className="muted small" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{w.address}</span>
                  <button className="btn ghost" style={{ padding: '0.15rem 0.4rem', color: '#c00' }} onClick={() => deleteWallet(w.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <div className="row2">
              <label>
                Coin
                <select name="wallet_coin_id" value={walletForm.wallet_coin_id} onChange={wf}>
                  <option value="">Select coin…</option>
                  {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol} — {c.name}</option>)}
                </select>
              </label>
              <label>
                Address
                <input name="wallet_address" value={walletForm.wallet_address} onChange={wf} placeholder="T… / 0x… / bc1…" required />
              </label>
            </div>
            <label>
              Label <span className="muted small">(optional)</span>
              <input name="wallet_label" value={walletForm.wallet_label} onChange={wf} placeholder="Platform reserve" />
            </label>
            <button className="btn primary" disabled={streetBusy} onClick={addWallet} style={{ marginTop: '0.5rem' }}>
              <Plus size={14} /> Add wallet
            </button>
          </div>

          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h3 style={{ margin: 0 }}>Payment Orders</h3>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select value={orderStatus} onChange={(e) => setOrderStatus(e.target.value)}>
                  <option value="all">All</option>
                  <option value="pending">Pending</option>
                  <option value="paid">Paid</option>
                  <option value="expired">Expired</option>
                </select>
                <button className="btn ghost" onClick={loadOrders} disabled={ordersBusy}><RefreshCw size={14} /></button>
              </div>
            </div>
            {orders.length === 0 && <p className="muted small">No orders.</p>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {orders.map((o) => (
                <div key={o.id} className="pill" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', justifyContent: 'space-between', flexWrap: 'wrap', padding: '0.35rem 0.6rem' }}>
                  <span><ListOrdered size={13} style={{ verticalAlign: 'middle' }} /> {o.order_ref}</span>
                  <span className="muted small">{o.user_email}</span>
                  <span style={{ fontWeight: 600 }}>{fmtCrypto(o.amount)} {o.coin_symbol}</span>
                  <StatusBadge status={o.status} />
                  <StatusBadge status={o.investment_status} />
                  {o.status === 'pending' && (
                    <button className="btn primary" style={{ fontSize: '0.78rem', padding: '0.2rem 0.5rem' }} onClick={() => confirmOrder(o.id)}>
                      <Check size={13} /> Mark paid & confirm
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {balanceUser && (
        <Modal title={`Adjust balance — ${balanceUser.email}`} onClose={() => { setBalanceUser(null); setModal({}) }}>
          <form onSubmit={submitBalance}>
            <label>
              Coin
              <select name="coin_id" value={modal.coin_id || ''} onChange={mf} required>
                <option value="">Select coin…</option>
                {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol} — {c.name}</option>)}
              </select>
            </label>
            <div className="row2" style={{ marginTop: '0.6rem' }}>
              <label>
                Invested delta
                <input name="invested_delta" type="number" step="0.00000001" value={modal.invested_delta || ''} onChange={mf} placeholder="0" />
              </label>
              <label>
                Withdrawable delta
                <input name="withdrawable_delta" type="number" step="0.00000001" value={modal.withdrawable_delta || ''} onChange={mf} placeholder="0" />
              </label>
            </div>
            <label style={{ marginTop: '0.6rem' }}>
              Note <span className="muted small">(optional, shown in payout ledger)</span>
              <input name="note" value={modal.note || ''} onChange={mf} placeholder="Support adjustment" />
            </label>
            <p className="muted small" style={{ marginTop: '0.4rem' }}>Use negative values to correct over-credits. Withdrawable changes are recorded in the payout ledger.</p>
            <button type="submit" className="btn primary lg block" disabled={modalBusy} style={{ marginTop: '0.6rem' }}>
              {modalBusy ? 'Saving…' : 'Save balance'}
            </button>
          </form>
        </Modal>
      )}

      {banUser && (
        <Modal title={`Ban — ${banUser.email}`} onClose={() => setBanUser(null)}>
          <form onSubmit={submitBan}>
            <label>
              Duration (hours)
              <input name="hours" type="number" min="1" value={modal.hours || ''} onChange={mf} placeholder="e.g. 24" autoFocus required />
            </label>
            <p className="muted small" style={{ marginTop: '0.4rem' }}>The user cannot log in until this period ends. They can be unbanned any time.</p>
            <button type="submit" className="btn primary lg block" disabled={modalBusy} style={{ marginTop: '0.6rem' }}>
              {modalBusy ? 'Banning…' : 'Ban user'}
            </button>
          </form>
        </Modal>
      )}

      {deleteUser && (
        <Modal title={`Delete — ${deleteUser.email}`} onClose={() => setDeleteUser(null)}>
          <form onSubmit={submitDelete}>
            <p style={{ marginBottom: '0.6rem' }}>
              This permanently deletes the account, wallets, and investments. Type <strong>{deleteUser.email}</strong> to confirm.
            </p>
            <input
              value={modal.confirm || ''}
              onChange={mf}
              name="confirm"
              placeholder={deleteUser.email}
              autoFocus
              required
            />
            <button type="submit" className="btn lg block" disabled={modalBusy || modal.confirm !== deleteUser.email} style={{ marginTop: '0.6rem', background: '#c00', color: '#fff' }}>
              {modalBusy ? 'Deleting…' : 'Delete account'}
            </button>
          </form>
        </Modal>
      )}

      {pickWindow && (
        <Modal title={`Target users — ${pickWindow.title}`} onClose={() => setPickWindow(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
              <input
                value={pickQ}
                onChange={(e) => setPickQ(e.target.value)}
                placeholder="Search users…"
                style={{ paddingLeft: '1.8rem' }}
              />
            </div>
            <div style={{ maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              {pickUsers
                .filter((u) => {
                  const t = `${u.email} ${u.phone} ${u.full_name}`.toLowerCase()
                  return t.includes(pickQ.toLowerCase())
                })
                .map((u) => (
                  <label key={u.id} className="pick-row" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={pickSel.has(u.id)}
                      onChange={() => togglePick(u.id)}
                    />
                    <span style={{ minWidth: 0 }}>
                      <span className="small" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.email || u.phone}</span>
                      <span className="muted" style={{ fontSize: '0.75rem' }}>{u.phone}</span>
                    </span>
                  </label>
                ))}
              {pickUsers.length === 0 && <p className="muted small">No users.</p>}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                className="btn primary"
                disabled={pickBusy || pickSel.size === 0}
                onClick={() => openWindow(pickWindow.id, [...pickSel])}
              >
                <Unlock size={14} /> Open for {pickSel.size} selected
              </button>
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              {pickSel.size === 0 ? 'No users selected — the window opens for nobody until you pick members.' : 'Only the checked users will see and claim this payout.'}
            </p>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, onClose, children }) {
  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
      onClick={onClose}
    >
      <div className="card form" style={{ width: '100%', maxWidth: 420, padding: '1.2rem' }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="btn ghost" style={{ padding: '0.25rem 0.5rem' }} onClick={onClose}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}