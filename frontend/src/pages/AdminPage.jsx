import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt, fmtCrypto, StatusBadge } from '../components/Format'
import {
  Shield, Clock, Users, UserCheck, Search, Coins, Plus, X, Check, Lock, Unlock,
  Ban, Wallet, PlugZap, Trash2, ListOrdered, RefreshCw, Eye, Bell, Settings2,
  Pencil,
} from 'lucide-react'

const PAY_MODES = [
  { value: 'provider', labelKey: 'admin.pay.auto' },
  { value: 'manual', labelKey: 'admin.pay.manual' },
]

const COOLDOWN_UNITS = {
  months: 'unitMonths',
  weeks: 'unitWeeks',
  days: 'unitDays',
  hours: 'unitHours',
}

const COOLDOWN_GROUPS = [
  { prefix: 'withdraw_cooldown', titleKey: 'withdrawCooldown' },
  { prefix: 'payout_cooldown', titleKey: 'payoutCooldown' },
]

export default function AdminPage() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const [tab, setTab] = useState('windows')
  const [windows, setWindows] = useState([])
  const [users, setUsers] = useState([])
  const [coins, setCoins] = useState([])
  const [q, setQ] = useState('')
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
  const [previewImg, setPreviewImg] = useState(null)
  const [previewLabel, setPreviewLabel] = useState('')

  const [pay, setPay] = useState({ payment_mode: 'simulate', provider: {}, payram: {}, platform_wallets: [] })
  const [providerForm, setProviderForm] = useState({ provider_url: '', provider_key: '', provider_secret: '', store_id: '', webhook_token: '', callback_url: '', success_url: '' })
  const [payramForm, setPayramForm] = useState({ payram_mode: 'test', payram_base_url_test: '', payram_api_key_test: '', payram_base_url_production: '', payram_api_key_production: '' })
  const [walletForm, setWalletForm] = useState({ wallet_coin_id: '', wallet_address: '', wallet_label: 'Platform wallet' })
  const [streetBusy, setStreetBusy] = useState(false)
  const [testResult, setTestResult] = useState('')

  const [orders, setOrders] = useState([])
  const [orderStatus, setOrderStatus] = useState('all')
  const [ordersBusy, setOrdersBusy] = useState(false)

  const [allCoins, setAllCoins] = useState([])
  const [coinShow, setCoinShow] = useState(false)
  const [coinEditId, setCoinEditId] = useState(null)
  const [coinForm, setCoinForm] = useState({ name: '', symbol: '', chain: 'TRC20', contract_address: '', reference_price: '', min_invest: '0', is_stable: true, is_active: true, icon: null })
  const [coinBusy, setCoinBusy] = useState(false)

  const [plats, setPlats] = useState({ _meta: [] })
  const [platDraft, setPlatDraft] = useState({})
  const [settingsBusy, setSettingsBusy] = useState(false)

  const [annList, setAnnList] = useState([])
  const [annBusy, setAnnBusy] = useState(false)
  const [annForm, setAnnForm] = useState({
    title: '', title_ar: '', body: '', body_ar: '', link: '', target: 'all',
  })
  const [annSending, setAnnSending] = useState(false)

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

  async function loadSettings() {
    setSettingsBusy(true)
    try {
      const res = await client.get('/admin/settings/')
      setPlats(res.data)
    } catch (err) { toast(apiError(err), 'error') }
    finally { setSettingsBusy(false) }
  }

  async function loadAnnouncements() {
    setAnnBusy(true)
    try {
      const res = await client.get('/admin/notifications/')
      setAnnList(res.data)
    } catch (err) { toast(apiError(err), 'error') }
    finally { setAnnBusy(false) }
  }

  async function loadCoins() {
    try {
      const res = await client.get('/coins/')
      setCoins(res.data)
    } catch { /* non-critical */ }
  }

  async function loadAdminCoins() {
    setCoinBusy(true)
    try {
      const res = await client.get('/admin/coins/')
      setAllCoins(res.data)
    } catch (err) { toast(apiError(err), 'error') }
    finally { setCoinBusy(false) }
  }

  useEffect(() => {
    loadCoins()
    loadWindows()
    loadUsers()
    loadKyc()
    loadPayments()
    loadOrders()
    loadSettings()
    loadAnnouncements()
    loadAdminCoins()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const t = setTimeout(loadUsers, 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => { loadKyc() }, [kycStatus])

  useEffect(() => { loadOrders() }, [orderStatus])

  async function toggleWindow(id, active) {
    try {
      const res = await client.post(`/admin/payout-windows/${id}/toggle/`, { active })
      toast(res.data.message, 'success')
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function openFlow(ids = []) {
    setPickBusy(true)
    try {
      const current = windows[0]
      const payload = { active: true }
      if (ids.length) payload.target_user_ids = ids
      const res = current
        ? await client.post(`/admin/payout-windows/${current.id}/toggle/`, payload)
        : await client.post('/admin/payout-windows/', payload)
      toast(res.data.message, 'success')
      setPickWindow(null)
      setPickSel(new Set())
      loadWindows()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setPickBusy(false) }
  }

  function openPicker(w) {
    setPickWindow(w)
    setPickSel(new Set(w?.target_users || []))
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
      toast(t('admin.toast.balanceUpdated'), 'success')
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
      const reason = window.prompt(t('admin.kyc.reasonPrompt'))
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

  async function previewKyc(id, field, label) {
    try {
      const res = await client.get(`/admin/kyc/${id}/file/${field}/`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      setPreviewImg(url)
      setPreviewLabel(label)
    } catch (err) { toast(apiError(err), 'error') }
  }

  function closePreview() {
    if (previewImg) URL.revokeObjectURL(previewImg)
    setPreviewImg(null)
    setPreviewLabel('')
  }

  async function saveMode(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', { payment_mode: pay.payment_mode })
      toast(t('admin.toast.modeSaved'), 'success')
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setStreetBusy(false) }
  }

  async function saveProvider(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', { ...providerForm, ...payramForm })
      toast(t('admin.toast.providerSaved'), 'success')
      setProviderForm({ provider_url: '', provider_key: '', store_id: '', webhook_token: '', callback_url: '', success_url: '' })
      setPayramForm({ payram_mode: 'test', payram_base_url_test: '', payram_api_key_test: '', payram_base_url_production: '', payram_api_key_production: '' })
      loadPayments()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setStreetBusy(false) }
  }

  async function addWallet(e) {
    e.preventDefault()
    setStreetBusy(true)
    try {
      await client.post('/admin/payments/', walletForm)
      toast(t('admin.toast.walletSaved'), 'success')
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
      setTestResult(`${res.data.ok ? t('admin.pay.ok') : t('admin.pay.failed')} — ${res.data.message}`)
    } catch (err) { toast(apiError(err), 'error') }
  }

  function openAddCoin() {
    setCoinEditId(null)
    setCoinForm({ name: '', symbol: '', chain: 'TRC20', contract_address: '', reference_price: '', min_invest: '0', is_stable: true, is_active: true, icon: null })
    setCoinShow(true)
  }

  function openEditCoin(c) {
    setCoinEditId(c.id)
    setCoinForm({
      name: c.name, symbol: c.symbol, chain: c.chain, contract_address: c.contract_address || '',
      reference_price: String(c.reference_price ?? ''), min_invest: String(c.min_invest ?? '0'),
      is_stable: c.is_stable, is_active: c.is_active, icon: null,
    })
    setCoinShow(true)
  }

  const cf = (e) => setCoinForm((p) => ({
    ...p, [e.target.name]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  }))
  const cff = (e) => setCoinForm((p) => ({ ...p, icon: e.target.files[0] || null }))

  async function saveCoin(e) {
    e.preventDefault()
    if (!coinForm.name.trim() || !coinForm.symbol.trim()) return
    setCoinBusy(true)
    try {
      const fd = new FormData()
      fd.append('name', coinForm.name.trim())
      fd.append('symbol', coinForm.symbol.trim().toUpperCase())
      fd.append('chain', coinForm.chain)
      fd.append('contract_address', coinForm.contract_address || '')
      fd.append('reference_price', String(coinForm.reference_price ?? '0'))
      fd.append('min_invest', String(coinForm.min_invest ?? '0'))
      fd.append('is_stable', coinForm.is_stable ? 'true' : 'false')
      fd.append('is_active', coinForm.is_active ? 'true' : 'false')
      if (coinForm.icon) fd.append('icon', coinForm.icon)

      if (coinEditId) {
        await client.put(`/admin/coins/${coinEditId}/`, fd)
      } else {
        await client.post('/admin/coins/', fd)
      }
      toast(t('admin.toast.coinSaved'), 'success')
      setCoinShow(false)
      loadAdminCoins()
      loadCoins()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setCoinBusy(false) }
  }

  async function deleteCoin(id) {
    if (!window.confirm(t('admin.coins.confirmDelete'))) return
    try {
      await client.delete(`/admin/coins/${id}/`)
      toast(t('admin.toast.coinDeleted'), 'success')
      loadAdminCoins()
      loadCoins()
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

  async function submitSettings(e) {
    e.preventDefault()
    setSettingsBusy(true)
    try {
      const payload = {}
      for (const m of plats._meta) {
        if (!(m.key in platDraft)) continue
        if (m.type === 'num') payload[m.key] = Number(platDraft[m.key])
        else if (m.type === 'bool') payload[m.key] = platDraft[m.key] === true
        else payload[m.key] = platDraft[m.key]
      }
      const res = await client.post('/admin/settings/', payload)
      toast(res.data.message, 'success')
      setPlatDraft({})
      loadSettings()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setSettingsBusy(false) }
  }

  async function submitAnnouncement(e) {
    e.preventDefault()
    setAnnSending(true)
    try {
      await client.post('/admin/notifications/', annForm)
      toast(t('admin.toast.annSent'), 'success')
      setAnnForm({ title: '', title_ar: '', body: '', body_ar: '', link: '', target: 'all' })
      loadAnnouncements()
    } catch (err) { toast(apiError(err), 'error') }
    finally { setAnnSending(false) }
  }

  const prf = (e) => setPayramForm((p) => ({ ...p, [e.target.name]: e.target.value }))
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
        <div><h2><Shield size={20} style={{ marginRight: 8, verticalAlign: 'middle' }} />{t('admin.title')}</h2></div>
      </div>

      <div className="tabs" style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button className={`btn ${tab === 'windows' ? 'primary' : 'ghost'}`} onClick={() => setTab('windows')}>
          <Clock size={16} /> {t('admin.tab.windows')}
        </button>
        <button className={`btn ${tab === 'users' ? 'primary' : 'ghost'}`} onClick={() => setTab('users')}>
          <Users size={16} /> {t('admin.tab.users')}
        </button>
        <button className={`btn ${tab === 'kyc' ? 'primary' : 'ghost'}`} onClick={() => setTab('kyc')}>
          <Check size={16} /> {t('admin.tab.kyc')}
        </button>
        <button className={`btn ${tab === 'payments' ? 'primary' : 'ghost'}`} onClick={() => setTab('payments')}>
          <Wallet size={16} /> {t('admin.tab.payments')}
        </button>
        <button className={`btn ${tab === 'coins' ? 'primary' : 'ghost'}`} onClick={() => setTab('coins')}>
          <Coins size={16} /> {t('admin.tab.coins')}
        </button>
        <button className={`btn ${tab === 'notifications' ? 'primary' : 'ghost'}`} onClick={() => setTab('notifications')}>
          <Bell size={16} /> {t('admin.tab.notifications')}
        </button>
        <button className={`btn ${tab === 'settings' ? 'primary' : 'ghost'}`} onClick={() => setTab('settings')}>
          <Settings2 size={16} /> {t('admin.tab.settings')}
        </button>
      </div>

      {tab === 'windows' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>{t('admin.win.head')}</h3>
            <button className="btn ghost" onClick={loadWindows}><RefreshCw size={14} /></button>
          </div>
          <p className="muted small" style={{ marginBottom: '1rem' }}>{t('admin.win.settingsHint')}</p>

          {windows[0] ? (
            <div key={windows[0].id} className="card" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <strong style={{ fontSize: '1.05rem' }}>{windows[0].title}</strong>
                  <div className="muted small" style={{ marginTop: '0.15rem' }}>
                    {t('admin.win.percent')}: {windows[0].percent}% · {t('admin.win.duration')}: {windows[0].duration_hours}h
                    {!windows[0].is_open && windows[0].target_mode === 'specific' && windows[0].target_users.length > 0 && (
                      <span style={{ color: 'var(--accent)' }}>{t('admin.win.targeted', { count: windows[0].target_users.length })}</span>
                    )}
                  </div>
                </div>
                <span className={`pill ${windows[0].is_active ? 'pill-active' : ''}`} style={{ background: windows[0].is_active ? 'var(--accent)' : 'var(--muted-bg)', color: windows[0].is_active ? '#fff' : 'var(--muted)', fontSize: '0.75rem' }}>
                  {windows[0].is_active ? t('admin.win.open') : t('admin.win.closed')}
                </span>
              </div>

              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.85rem' }}>
                <span><Users size={14} style={{ verticalAlign: 'middle' }} /> {t('admin.win.eligible', { count: windows[0].eligible_count })}</span>
                <span><Check size={14} style={{ verticalAlign: 'middle' }} /> {t('admin.win.claimed', { count: windows[0].claimed_count })}</span>
                <span><Coins size={14} style={{ verticalAlign: 'middle' }} /> {t('admin.win.paid', { amount: fmt(windows[0].total_granted) })}</span>
                {windows[0].is_open && <span className="muted"><Clock size={14} style={{ verticalAlign: 'middle' }} /> {t('admin.win.left', { hours: Math.round(windows[0].time_left_hours) })}</span>}
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.2rem', flexWrap: 'wrap' }}>
                {windows[0].is_active ? (
                  <button className="btn ghost" style={{ color: 'var(--danger, #e44)' }} onClick={() => toggleWindow(windows[0].id, false)}>
                    <Lock size={14} /> {t('admin.win.closeWindow')}
                  </button>
                ) : (
                  <>
                    <button className="btn primary" disabled={pickBusy} onClick={() => openFlow([])}>
                      <Users size={14} /> {t('admin.win.openAll')}
                    </button>
                    <button className="btn primary" style={{ background: 'var(--bg)', color: 'var(--text)' }} onClick={() => openPicker(windows[0])}>
                      <Users size={14} /> {t('admin.win.openSel')}
                    </button>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
              <p className="muted" style={{ marginBottom: '1rem' }}>{t('admin.win.empty')}</p>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                <button className="btn primary" disabled={pickBusy} onClick={() => openFlow([])}>
                  <Users size={14} /> {t('admin.win.openAll')}
                </button>
                <button className="btn primary" style={{ background: 'var(--bg)', color: 'var(--text)' }} onClick={() => openPicker(null)}>
                  <Users size={14} /> {t('admin.win.openSel')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'users' && (
        <div>
          <div style={{ position: 'relative', marginBottom: '1rem' }}>
            <Search size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t('admin.users.search')}
              style={{ paddingLeft: '2.2rem' }}
            />
          </div>
          {users.length === 0 && <p className="muted">{t('admin.users.empty')}</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {users.map((u) => (
              <div key={u.id} className="card" style={{ padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
                  <div>
                    <strong>{u.email}</strong>
                    <div className="muted small">
                      {t('admin.users.invested', { inv: fmt(u.total_invested), wd: fmt(u.total_withdrawable) })}
                      {u.is_banned && u.banned_until && <span style={{ color: '#c00', marginLeft: '0.6rem' }}>{t('admin.users.banned', { date: new Date(u.banned_until).toLocaleString() })}</span>}
                    </div>
                    <div className="muted small">
                      {t('admin.users.tree', { l1: u.level1_count ?? 0, l2: u.level2_count ?? 0, l3: u.level3_count ?? 0 })}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    <button className="btn ghost" title={t('admin.bal.title', { email: u.email })} onClick={() => openBalance(u)}><Coins size={14} /> {t('admin.users.balance')}</button>
                    {u.is_banned ? (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'unban')}><Unlock size={14} /> {t('admin.users.unban')}</button>
                    ) : (
                      <button className="btn ghost" onClick={() => { setBanUser(u); setModal({ hours: '' }) }}><Ban size={14} /> {t('admin.users.ban')}</button>
                    )}
                    {u.is_frozen ? (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'unfreeze')}><Unlock size={14} /> {t('admin.users.unfreeze')}</button>
                    ) : (
                      <button className="btn ghost" onClick={() => userAction(u.id, 'freeze')}><Lock size={14} /> {t('admin.users.freeze')}</button>
                    )}
                    {u.kyc_verified ? (
                      <span className="pill pill-active" style={{ fontSize: '0.75rem', background: 'var(--accent)', color: '#fff' }}>KYC ✓</span>
                    ) : (
                      <>
                        <button className="btn primary" style={{ fontSize: '0.8rem' }} onClick={() => userAction(u.id, 'kyc_approve')}>
                          <Check size={14} /> {t('admin.users.kyc')}
                        </button>
                        {u.kyc_rejected && <span className="pill" style={{ fontSize: '0.75rem', background: '#fee', color: '#c00' }}>{t('admin.users.rejected')}</span>}
                      </>
                    )}
                    <button className="btn ghost" style={{ color: '#c00' }} onClick={() => { setDeleteUser(u); setModal({ confirm: '' }) }}>
                      <Trash2 size={14} /> {t('admin.users.delete')}
                    </button>
                  </div>
                </div>
                {u.wallets && u.wallets.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.6rem' }}>
                    {u.wallets.map((w) => (
                      <span key={w.coin_id} className="pill" style={{ fontSize: '0.75rem' }}>
                        {t('admin.users.wallet', { symbol: w.symbol, i: fmtCrypto(w.invested_balance), w: fmtCrypto(w.withdrawable_balance) })}
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
            <h3>{t('admin.kyc.head')}</h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <select value={kycStatus} onChange={(e) => setKycStatus(e.target.value)}>
                <option value="pending">{t('admin.kyc.pending')}</option>
                <option value="approved">{t('admin.kyc.approved')}</option>
                <option value="rejected">{t('admin.kyc.rejected')}</option>
                <option value="all">{t('admin.kyc.all')}</option>
              </select>
              <button className="btn ghost" onClick={loadKyc} disabled={kycBusy}><RefreshCw size={14} /> {t('admin.kyc.refresh')}</button>
            </div>
          </div>
          {kycList.length === 0 && <p className="muted">{t('admin.kyc.empty')}</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {kycList.map((s) => (
              <div key={s.id} className="card" style={{ padding: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.6rem' }}>
                  <div>
                    <strong>{s.user_email}</strong>
                    <div className="muted small">
                      {s.document_type} · {new Date(s.submitted_at).toLocaleString()} · <StatusBadge status={s.status} />
                    </div>
                    {s.status === 'rejected' && s.reason && <div className="muted small" style={{ color: '#c00' }}>{t('admin.kyc.reason', { reason: s.reason })}</div>}
                  </div>
                  {s.status === 'pending' && (
                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button className="btn primary" onClick={() => reviewKyc(s.id, 'approve')}><Check size={14} /> {t('admin.kyc.approve')}</button>
                      <button className="btn ghost" style={{ color: '#c00' }} onClick={() => reviewKyc(s.id, 'reject')}><X size={14} /> {t('admin.kyc.reject')}</button>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', marginTop: '0.6rem' }}>
                  {[
                    { label: t('admin.kyc.front'), field: 'front', url: s.document_front_url },
                    { label: t('admin.kyc.back'), field: 'back', url: s.document_back_url },
                    { label: t('admin.kyc.selfie'), field: 'selfie', url: s.selfie_url },
                  ]
                    .filter((f) => f.url)
                    .map((f) => (
                      <button key={f.field} type="button" className="btn ghost" style={{ fontSize: '0.8rem' }} onClick={() => previewKyc(s.id, f.field, f.label)}>
                        <Eye size={14} /> {f.label}
                      </button>
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
            <h3 style={{ marginBottom: '0.6rem' }}>{t('admin.pay.mode')}</h3>
            <div className="row2">
              <label>
                {t('admin.pay.modeField')}
                <select value={pay.payment_mode} onChange={(e) => setPay((p) => ({ ...p, payment_mode: e.target.value }))}>
                  {PAY_MODES.map((m) => <option key={m.value} value={m.value}>{t(m.labelKey)}</option>)}
                </select>
              </label>
              <button className="btn primary" style={{ alignSelf: 'flex-end' }} disabled={streetBusy} onClick={saveMode}>
                {t('admin.pay.saveMode')}
              </button>
            </div>
            <p className="muted small" style={{ marginTop: '0.3rem' }}>
              {t('admin.pay.modeHint')}
            </p>
          </div>

          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>{t('admin.pay.provider')}</h3>
            <p className="muted small" style={{ marginBottom: '0.6rem' }}>{t('admin.pay.payramHint')}</p>
            <div className="row2">
              <label>
                {t('admin.pay.payramMode')}
                <select name="payram_mode" value={payramForm.payram_mode || pay.payram.mode || 'test'} onChange={prf}>
                  <option value="test">{t('admin.pay.payramTest')}</option>
                  <option value="production">{t('admin.pay.payramProduction')}</option>
                </select>
              </label>
            </div>
            {['test', 'production'].map((env) => {
              const cfg = env === 'production' ? pay.payram?.production : pay.payram?.test
              const baseField = env === 'production' ? 'payram_base_url_production' : 'payram_base_url_test'
              const keyField = env === 'production' ? 'payram_api_key_production' : 'payram_api_key_test'
              return (
                <fieldset key={env} className="card" style={{ marginTop: '0.6rem', padding: '0.6rem', border: '1px solid var(--line)' }}>
                  <legend style={{ fontWeight: 600, padding: '0 0.4rem' }}>
                    {env === 'production' ? t('admin.pay.payramProduction') : t('admin.pay.payramTest')}
                  </legend>
                  <label>
                    {t('admin.pay.baseUrl')}
                    <input name={baseField} value={payramForm[baseField]} onChange={prf} placeholder={cfg?.base_url || 'https://pay.example.com'} />
                  </label>
                  <label>
                    {t('admin.pay.apiKey')} <span className="muted small">{t('admin.pay.apiKeyHint')}</span>
                    <input name={keyField} type="password" value={payramForm[keyField]} onChange={prf} placeholder={cfg?.api_key_masked || t('admin.pay.notSet')} />
                  </label>
                </fieldset>
              )
            })}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.6rem' }}>
              <button className="btn primary" disabled={streetBusy} onClick={saveProvider}>{t('admin.pay.saveProvider')}</button>
              <button className="btn ghost" onClick={testConnection}><PlugZap size={14} /> {t('admin.pay.testConnection')}</button>
            </div>
            <p className="muted small" style={{ marginTop: '0.5rem' }}>{t('admin.pay.webhookUrl')}: <code>/api/gateway/webhook/</code></p>
            {testResult && <p className={`small ${testResult.startsWith('OK') ? 'pos' : 'neg'}`}>{testResult}</p>}
          </div>

          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>{t('admin.pay.wallets')}</h3>
            {pay.platform_wallets.length === 0 && <p className="muted small">{t('admin.pay.walletsEmpty')}</p>}
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
                {t('admin.pay.selectCoin')}
                <select name="wallet_coin_id" value={walletForm.wallet_coin_id} onChange={wf}>
                  <option value="">{t('admin.pay.selectCoin')}</option>
                  {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol} — {c.name}</option>)}
                </select>
              </label>
              <label>
                {t('admin.pay.address')}
                <input name="wallet_address" value={walletForm.wallet_address} onChange={wf} placeholder="T… / 0x… / bc1…" required />
              </label>
            </div>
            <label>
              {t('admin.pay.label')} <span className="muted small">{t('admin.pay.optional')}</span>
              <input name="wallet_label" value={walletForm.wallet_label} onChange={wf} placeholder={t('admin.pay.labelPh')} />
            </label>
            <button className="btn primary" disabled={streetBusy} onClick={addWallet} style={{ marginTop: '0.5rem' }}>
              <Plus size={14} /> {t('admin.pay.addWallet')}
            </button>
          </div>

          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h3 style={{ margin: 0 }}>{t('admin.pay.orders')}</h3>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select value={orderStatus} onChange={(e) => setOrderStatus(e.target.value)}>
                  <option value="all">{t('admin.pay.orderAll')}</option>
                  <option value="pending">{t('admin.pay.orderPending')}</option>
                  <option value="paid">{t('admin.pay.orderPaid')}</option>
                  <option value="expired">{t('admin.pay.orderExpired')}</option>
                </select>
                <button className="btn ghost" onClick={loadOrders} disabled={ordersBusy}><RefreshCw size={14} /></button>
              </div>
            </div>
            {orders.length === 0 && <p className="muted small">{t('admin.pay.noOrders')}</p>}
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
                      <Check size={13} /> {t('admin.pay.markPaid')}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'coins' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>{t('admin.coins.head')}</h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="btn ghost" onClick={loadAdminCoins} disabled={coinBusy}><RefreshCw size={14} /></button>
              {!coinShow && <button className="btn primary" onClick={openAddCoin}><Plus size={14} /> {t('admin.coins.add')}</button>}
            </div>
          </div>
          <p className="muted small" style={{ margin: 0 }}>{t('admin.coins.headHint')}</p>

          {coinShow && (
            <form className="card form" style={{ padding: '1rem' }} onSubmit={saveCoin}>
              <h3 style={{ marginBottom: '0.6rem' }}>{coinEditId ? t('admin.coins.edit') : t('admin.coins.add')}</h3>
              <div className="row2">
                <label>
                  {t('admin.coins.name')} *
                  <input name="name" value={coinForm.name} onChange={cf} required />
                </label>
                <label>
                  {t('admin.coins.symbol')} *
                  <input name="symbol" value={coinForm.symbol} onChange={cf} required placeholder="USDT" />
                </label>
              </div>
              <div className="row2">
                <label>
                  {t('admin.coins.chain')}
                  <select name="chain" value={coinForm.chain} onChange={cf}>
                    {['TRC20', 'ERC20', 'BEP20', 'BEP2', 'SOL', 'TON'].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label>
                  {t('admin.coins.contract')}
                  <input name="contract_address" value={coinForm.contract_address} onChange={cf} placeholder="T… / 0x…" />
                </label>
              </div>
              <div className="row2">
                <label>
                  {t('admin.coins.referencePrice')}
                  <input name="reference_price" type="number" step="any" value={coinForm.reference_price} onChange={cf} />
                </label>
                <label>
                  {t('admin.coins.minInvest')}
                  <input name="min_invest" type="number" step="any" value={coinForm.min_invest} onChange={cf} />
                </label>
              </div>
              <div className="row2">
                <label>
                  {t('admin.coins.icon')}
                  <input name="icon" type="file" accept="image/*" onChange={cff} />
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.2rem', flexWrap: 'wrap', paddingTop: '1.4rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0 }}>
                    <input name="is_stable" type="checkbox" checked={coinForm.is_stable} onChange={cf} />
                    {t('admin.coins.isStable')}
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: 0 }}>
                    <input name="is_active" type="checkbox" checked={coinForm.is_active} onChange={cf} />
                    {t('admin.coins.isActive')}
                  </label>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.6rem' }}>
                <button className="btn primary" disabled={coinBusy}>{coinBusy ? t('admin.coins.saving') : t('admin.coins.save')}</button>
                <button type="button" className="btn ghost" onClick={() => setCoinShow(false)}>{t('admin.coins.cancel')}</button>
              </div>
            </form>
          )}

          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
              <h3 style={{ margin: 0 }}>{t('admin.coins.list')}</h3>
              <span className="muted small">{allCoins.length}</span>
            </div>
            {allCoins.length === 0 && <p className="muted small">{t('admin.coins.empty')}</p>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {allCoins.map((c) => (
                <div key={c.id} className="pill" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', justifyContent: 'space-between', flexWrap: 'wrap', padding: '0.35rem 0.6rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {c.icon_url && <img src={c.icon_url} alt={c.symbol} style={{ width: 20, height: 20, borderRadius: '50%' }} />}
                    <strong>{c.symbol}</strong>
                    <span className="muted small">{c.name}</span>
                    <span className="pill" style={{ fontSize: '0.7rem', padding: '0.05rem 0.4rem' }}>{c.chain}</span>
                    {c.is_active
                      ? <span className="pill" style={{ fontSize: '0.7rem', background: 'var(--accent)', color: '#fff' }}>{t('admin.coins.active')}</span>
                      : <span className="pill" style={{ fontSize: '0.7rem' }}>{t('admin.coins.inactive')}</span>}
                    {c.is_stable && <span className="muted small">{t('admin.coins.stable')}</span>}
                  </span>
                  <span className="muted small">{t('admin.coins.refPrice', { p: fmt(c.reference_price) })} · {t('admin.coins.minInv', { m: fmt(c.min_invest) })}</span>
                  <span style={{ display: 'flex', gap: '0.4rem' }}>
                    <button className="btn ghost" title={t('admin.coins.edit')} onClick={() => openEditCoin(c)}><Pencil size={14} /></button>
                    <button className="btn ghost" style={{ color: '#c00' }} title={t('admin.coins.delete')} onClick={() => deleteCoin(c.id)}><Trash2 size={14} /></button>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'notifications' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card form" style={{ padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.6rem' }}>{t('admin.ann.head')}</h3>
            <label>
              {t('admin.ann.titleEn')}
              <input name="title" value={annForm.title} onChange={(e) => setAnnForm((p) => ({ ...p, title: e.target.value }))} placeholder={t('admin.ann.titlePh')} required />
            </label>
            <label>
              {t('admin.ann.titleAr')}
              <input name="title_ar" value={annForm.title_ar} onChange={(e) => setAnnForm((p) => ({ ...p, title_ar: e.target.value }))} placeholder="العنوان بالعربية" />
            </label>
            <label>
              {t('admin.ann.msgEn')}
              <textarea name="body" value={annForm.body} onChange={(e) => setAnnForm((p) => ({ ...p, body: e.target.value }))} placeholder={t('admin.ann.msgPh')} rows={3} />
            </label>
            <label>
              {t('admin.ann.msgAr')}
              <textarea name="body_ar" value={annForm.body_ar} onChange={(e) => setAnnForm((p) => ({ ...p, body_ar: e.target.value }))} placeholder="الرسالة بالعربية" rows={3} />
            </label>
            <label>
              {t('admin.ann.link')} <span className="muted small">{t('admin.ann.linkHint')}</span>
              <input name="link" value={annForm.link} onChange={(e) => setAnnForm((p) => ({ ...p, link: e.target.value }))} placeholder="/payouts" />
            </label>
            <div className="row2">
              <label>
                {t('admin.ann.audience')}
                <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.3rem', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className={`btn ${annForm.target === 'all' ? 'primary' : 'ghost'}`}
                    onClick={() => setAnnForm((p) => ({ ...p, target: 'all' }))}
                  >
                    <Users size={14} /> {t('admin.ann.audAll')}
                  </button>
                  <button
                    type="button"
                    className={`btn ${annForm.target === 'invested' ? 'primary' : 'ghost'}`}
                    onClick={() => setAnnForm((p) => ({ ...p, target: 'invested' }))}
                  >
                    <UserCheck size={14} /> {t('admin.ann.audInvested')}
                  </button>
                </div>
              </label>
              <button className="btn primary" style={{ alignSelf: 'flex-end' }} disabled={annSending} onClick={submitAnnouncement}>
                <Bell size={14} /> {annSending ? t('admin.ann.sending') : t('admin.ann.send')}
              </button>
            </div>
          </div>

          <div className="card" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h3 style={{ margin: 0 }}>{t('admin.ann.recent')}</h3>
              <button className="btn ghost" onClick={loadAnnouncements} disabled={annBusy}><RefreshCw size={14} /></button>
            </div>
            {annList.length === 0 && <p className="muted small">{t('admin.ann.empty')}</p>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {annList.map((n) => (
                <div key={n.id} className="pill" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', justifyContent: 'space-between', flexWrap: 'wrap', padding: '0.35rem 0.6rem' }}>
                  <span style={{ fontWeight: 600 }}>{n.title}</span>
                  <span className="muted small">{n.recipient}</span>
                  <span className="muted small">{new Date(n.created_at).toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'settings' && (
        <div className="card form" style={{ padding: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h3 style={{ margin: 0 }}>{t('admin.set.head')}</h3>
            <button className="btn ghost" onClick={loadSettings} disabled={settingsBusy}><RefreshCw size={14} /></button>
          </div>
          <p className="muted small" style={{ marginBottom: '0.8rem' }}>
            {t('admin.set.hint')}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
            {COOLDOWN_GROUPS.map((g) => {
              const items = plats._meta.filter((m) => m.key.startsWith(g.prefix))
              if (items.length === 0) return null
              return (
                <fieldset key={g.prefix} className="cooldown-box">
                  <legend>{t(`admin.set.${g.titleKey}`)}</legend>
                  <div className="cooldown-grid">
                    {items.map((m) => {
                      const cur = plats[m.key]
                      const draft = platDraft[m.key]
                      const unit = m.key.split(`${g.prefix}_`).pop()
                      const dirty = draft !== undefined && String(draft) !== String(cur)
                      return (
                        <label key={m.key}>
                          {t(`admin.set.${COOLDOWN_UNITS[unit] || 'unitHours'}`)}
                          <input
                            type="number"
                            step="any"
                            min="0"
                            value={draft !== undefined ? draft : String(cur)}
                            onChange={(e) => setPlatDraft((p) => ({ ...p, [m.key]: e.target.value }))}
                            className={dirty ? 'input-highlight' : ''}
                          />
                        </label>
                      )
                    })}
                  </div>
                </fieldset>
              )
            })}
            {plats._meta
              .filter((m) => !COOLDOWN_GROUPS.some((g) => m.key.startsWith(g.prefix)))
              .map((m) => {
              const cur = plats[m.key]
              const draft = platDraft[m.key]
              const dirty = draft !== undefined && String(draft) !== String(cur)
              return (
                <label key={m.key}>
                  {t(`admin.set.${m.key}`) || m.label} <span className="muted small">({m.key})</span>
                  {m.key === 'default_lang' ? (
                    <select
                      value={draft !== undefined ? draft : String(cur)}
                      onChange={(e) => setPlatDraft((p) => ({ ...p, [m.key]: e.target.value }))}
                      className={dirty ? 'input-highlight' : ''}
                    >
                      <option value="en">EN — English</option>
                      <option value="ar">عربي — العربية</option>
                    </select>
                  ) : m.type === 'bool' ? (
                    <select
                      value={draft !== undefined ? (draft ? '1' : '0') : (cur ? '1' : '0')}
                      onChange={(e) => setPlatDraft((p) => ({ ...p, [m.key]: e.target.value === '1' }))}
                      className={dirty ? 'input-highlight' : ''}
                    >
                      <option value="1">{t('admin.yes')}</option>
                      <option value="0">{t('admin.no')}</option>
                    </select>
                  ) : (
                    <input
                      type={m.type === 'num' ? 'number' : 'text'}
                      step={m.type === 'num' ? 'any' : undefined}
                      value={draft !== undefined ? draft : String(cur)}
                      onChange={(e) => setPlatDraft((p) => ({ ...p, [m.key]: e.target.value }))}
                      className={dirty ? 'input-highlight' : ''}
                    />
                  )}
                </label>
              )
            })}
          </div>
          <button className="btn primary lg block" disabled={settingsBusy || Object.keys(platDraft).length === 0} onClick={submitSettings} style={{ marginTop: '0.8rem' }}>
            <Check size={14} /> {settingsBusy ? t('admin.set.saving') : t('admin.set.save')}
          </button>
        </div>
      )}

      {balanceUser && (
        <Modal title={t('admin.bal.title', { email: balanceUser.email })} onClose={() => { setBalanceUser(null); setModal({}) }}>
          <form onSubmit={submitBalance}>
            <label>
              {t('admin.bal.coin')}
              <select name="coin_id" value={modal.coin_id || ''} onChange={mf} required>
                <option value="">{t('admin.pay.selectCoin')}</option>
                {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol} — {c.name}</option>)}
              </select>
            </label>
            <div className="row2" style={{ marginTop: '0.6rem' }}>
              <label>
                {t('admin.bal.investedDelta')}
                <input name="invested_delta" type="number" step="0.00000001" value={modal.invested_delta || ''} onChange={mf} placeholder="0" />
              </label>
              <label>
                {t('admin.bal.wdDelta')}
                <input name="withdrawable_delta" type="number" step="0.00000001" value={modal.withdrawable_delta || ''} onChange={mf} placeholder="0" />
              </label>
            </div>
            <label style={{ marginTop: '0.6rem' }}>
              {t('admin.bal.note')} <span className="muted small">{t('admin.bal.noteHint')}</span>
              <input name="note" value={modal.note || ''} onChange={mf} placeholder={t('admin.bal.notePh')} />
            </label>
            <p className="muted small" style={{ marginTop: '0.4rem' }}>{t('admin.bal.hint')}</p>
            <button type="submit" className="btn primary lg block" disabled={modalBusy} style={{ marginTop: '0.6rem' }}>
              {modalBusy ? t('admin.bal.saving') : t('admin.bal.save')}
            </button>
          </form>
        </Modal>
      )}

      {banUser && (
        <Modal title={t('admin.ban.title', { email: banUser.email })} onClose={() => setBanUser(null)}>
          <form onSubmit={submitBan}>
            <label>
              {t('admin.ban.hours')}
              <input name="hours" type="number" min="1" value={modal.hours || ''} onChange={mf} placeholder={t('admin.ban.hoursPh')} autoFocus required />
            </label>
            <p className="muted small" style={{ marginTop: '0.4rem' }}>{t('admin.ban.hint')}</p>
            <button type="submit" className="btn primary lg block" disabled={modalBusy} style={{ marginTop: '0.6rem' }}>
              {modalBusy ? t('admin.ban.saving') : t('admin.ban.save')}
            </button>
          </form>
        </Modal>
      )}

      {deleteUser && (
        <Modal title={t('admin.del.title', { email: deleteUser.email })} onClose={() => setDeleteUser(null)}>
          <form onSubmit={submitDelete}>
            <p style={{ marginBottom: '0.6rem' }}>
              {t('admin.del.warn', { email: deleteUser.email })}
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
              {modalBusy ? t('admin.del.saving') : t('admin.del.save')}
            </button>
          </form>
        </Modal>
      )}

      {pickWindow && (
        <Modal title={t('admin.pick.title', { title: pickWindow?.title || t('admin.win.openSel') })} onClose={() => setPickWindow(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
              <input
                value={pickQ}
                onChange={(e) => setPickQ(e.target.value)}
                placeholder={t('admin.pick.search')}
                style={{ paddingLeft: '1.8rem' }}
              />
            </div>
            <div style={{ maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              {pickUsers
                .filter((u) => {
                  const txt = `${u.email} ${u.phone} ${u.full_name}`.toLowerCase()
                  return txt.includes(pickQ.toLowerCase())
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
              {pickUsers.length === 0 && <p className="muted small">{t('admin.pick.none')}</p>}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                className="btn primary"
                disabled={pickBusy || pickSel.size === 0}
                onClick={() => openFlow([...pickSel])}
              >
                <Unlock size={14} /> {t('admin.pick.openFor', { count: pickSel.size })}
              </button>
            </div>
            <p className="muted small" style={{ margin: 0 }}>
              {pickSel.size === 0 ? t('admin.pick.hintNone') : t('admin.pick.hintSome')}
            </p>
          </div>
        </Modal>
      )}

      {previewImg && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
          onClick={closePreview}
        >
          <div style={{ background: 'var(--card-bg, #fff)', borderRadius: 10, padding: '1rem', maxWidth: '92vw', maxHeight: '88vh' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
              <strong>{previewLabel}</strong>
              <button className="btn ghost" style={{ padding: '0.25rem 0.5rem' }} onClick={closePreview}><X size={16} /></button>
            </div>
            <img src={previewImg} alt={previewLabel} style={{ maxWidth: '84vw', maxHeight: '74vh', borderRadius: 8, objectFit: 'contain', display: 'block' }} />
          </div>
        </div>
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