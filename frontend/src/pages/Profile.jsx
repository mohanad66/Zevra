import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { client } from '../api/client'
import { Camera, ShieldCheck, KeyRound, LogOut, Trash2, Plus } from 'lucide-react'

export default function Profile() {
  const { user, refreshUser, logout, apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const location = useLocation()
  const kycRef = useRef(null)
  const [profile, setProfile] = useState({ email: '', first_name: '', last_name: '', phone: '' })
  const [avatar, setAvatar] = useState(null)
  const [pwd, setPwd] = useState({ old_password: '', new_password: '' })
  const [kyc, setKyc] = useState({ status: 'not_submitted', required_to_invest: false, required_to_withdraw: false })
  const [kycForm, setKycForm] = useState({ first_name: '', last_name: '', document_type: 'ID card', document_front: null, document_back: null, selfie: null })
  const [accounts, setAccounts] = useState([])
  const [coins, setCoins] = useState([])
  const [accForm, setAccForm] = useState({ coin: null, address: '', label: '' })
  const [busy, setBusy] = useState(false)

  async function load() {
    const [kycRes, accRes, coinRes] = await Promise.all([
      client.get('/kyc/'),
      client.get('/accounts/'),
      client.get('/coins/'),
    ])
    setKyc(kycRes.data)
    setAccounts(accRes.data ?? [])
    setCoins(coinRes.data ?? [])
    if (coinRes.data?.length) setAccForm((f) => ({ ...f, coin: f.coin ?? coinRes.data[0].id }))
  }

  useEffect(() => { load().catch(() => {}) }, [])

  useEffect(() => {
    if (location.state?.kyc && kycRef.current) {
      kycRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [location.state, kyc.status])

  useEffect(() => {
    if (user) {
      setProfile({ email: user.email, first_name: user.first_name, last_name: user.last_name, phone: user.phone || '' })
      setKycForm((f) => ({
        ...f,
        first_name: f.first_name || user.first_name || '',
        last_name: f.last_name || user.last_name || '',
      }))
    }
  }, [user])

  async function saveProfile(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const form = new FormData()
      form.append('email', profile.email)
      form.append('first_name', profile.first_name)
      form.append('last_name', profile.last_name)
      form.append('phone', profile.phone)
      if (avatar) form.append('avatar', avatar)
      await client.patch('/auth/me/', form)
      await refreshUser()
      setAvatar(null)
      toast(t('pf.saved'), 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function changePassword(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await client.post('/auth/change-password/', pwd)
      setPwd({ old_password: '', new_password: '' })
      toast(t('pf.passwordChanged'), 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function submitKyc(e) {
    e.preventDefault()
    if (!kycForm.first_name.trim() || !kycForm.last_name.trim()) {
      toast(t('pf.kyc.namesNote'), 'error')
      return
    }
    if (!kycForm.document_front) { toast(t('pf.kyc.frontRequired'), 'error'); return }
    setBusy(true)
    try {
      const form = new FormData()
      form.append('first_name', kycForm.first_name.trim())
      form.append('last_name', kycForm.last_name.trim())
      form.append('document_type', kycForm.document_type)
      form.append('document_front', kycForm.document_front)
      if (kycForm.document_back) form.append('document_back', kycForm.document_back)
      if (kycForm.selfie) form.append('selfie', kycForm.selfie)
      const res = await client.post('/kyc/submit/', form)
      toast(res.data.message, 'success')
      await load()
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function addAccount(e) {
    e.preventDefault()
    if (!accForm.address.trim()) { toast(t('pf.acc.enterAddress'), 'error'); return }
    setBusy(true)
    try {
      await client.post('/accounts/', { coin: accForm.coin, address: accForm.address, label: accForm.label })
      setAccForm({ coin: accForm.coin, address: '', label: '' })
      await load()
      toast(t('pf.acc.saved'), 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function delAccount(id) {
    try {
      await client.delete(`/accounts/${id}/`)
      await load()
      toast(t('pf.acc.removed'), 'success')
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function delAccountAll() {
    if (!window.confirm(t('pf.deleteConfirm'))) return
    try {
      await client.post('/auth/delete/')
      toast(t('pf.deleted'), 'success')
      await logout()
    } catch (err) { toast(apiError(err), 'error') }
  }

  const kycBadge = kyc.kyc_verified
    ? 'verified'
    : kyc.kyc_rejected
      ? 'rejected'
      : kyc.status === 'pending'
        ? 'pending'
        : 'none'

  const kycLabel = kyc.kyc_verified
    ? t('pf.kyc.verified')
    : kyc.kyc_rejected
      ? t('pf.kyc.rejected')
      : kyc.status === 'pending'
        ? t('pf.kyc.pending')
        : t('pf.kyc.notSubmitted')

  return (
    <div className="page">
      <div className="page-head">
        <div><h2>{t('pf.title')}</h2><p>{t('pf.subtitle')}</p></div>
      </div>

      <div className="profile-grid">
        <form className="card form" onSubmit={saveProfile}>
          <h3>{t('pf.personal')}</h3>
          <div className="avatar-row">
            {avatar ? (
              <img className="avatar lg" src={URL.createObjectURL(avatar)} alt="" />
            ) : user?.avatar_url ? (
              <img className="avatar lg" src={user.avatar_url} alt="" />
            ) : (
              <span className="avatar-fallback lg">{user?.email?.[0]?.toUpperCase()}</span>
            )}
            <label className="btn ghost file-btn">
              <Camera size={16} /> {t('pf.changePhoto')}
              <input type="file" accept="image/*" onChange={(e) => setAvatar(e.target.files[0])} hidden />
            </label>
          </div>
          <div className="row2">
            <label>{t('auth.register.firstName')}
              <input value={profile.first_name} onChange={(e) => setProfile({ ...profile, first_name: e.target.value })} />
            </label>
            <label>{t('auth.register.lastName')}
              <input value={profile.last_name} onChange={(e) => setProfile({ ...profile, last_name: e.target.value })} />
            </label>
          </div>
          <div className="row2">
            <label>{t('pf.email')}
              <input
                type="email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                required
              />
            </label>
            <label>{t('pf.phone')}
              <input value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} placeholder={t('pf.optional')} />
            </label>
          </div>
          <button className="btn primary block" disabled={busy}>{t('pf.saveChanges')}</button>
        </form>

        <form className="card form" onSubmit={changePassword}>
          <h3><KeyRound size={18} /> {t('pf.password')}</h3>
          <label>{t('pf.currentPassword')}
            <input type="password" value={pwd.old_password} onChange={(e) => setPwd({ ...pwd, old_password: e.target.value })} required />
          </label>
          <label>{t('pf.newPassword')}
            <input type="password" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} required minLength={8} />
          </label>
          <button className="btn primary block" disabled={busy}>{t('pf.changePassword')}</button>
        </form>
      </div>

      <div className="card form" ref={kycRef}>
        <h3><ShieldCheck size={18} /> {t('pf.kyc.title')}</h3>
        <div className="kyc-status">
          <span className={`pill pill-${kycBadge}`}>
            {kycLabel}
          </span>
          {kyc.required_to_invest && <span className="muted small">{t('pf.kyc.reqInvest')}</span>}
          {kyc.required_to_withdraw && <span className="muted small">{t('pf.kyc.reqWithdraw')}</span>}
          {kyc.reason && <p className="small warn-text">{t('pf.kyc.reason')}: {kyc.reason}</p>}
        </div>

        {!kyc.kyc_verified && (
          <form onSubmit={submitKyc}>
            <h3 style={{ marginTop: '.5rem' }}>{t('pf.kyc.formTitle')}</h3>
            <div className="notice" style={{ backgroundColor: 'rgba(206,167,77,.08)', borderColor: 'rgba(206,167,77,.35)' }}>
              {t('pf.kyc.namesNote')}
            </div>
            <div className="row2">
              <label>{t('pf.kyc.firstName')}
                <input value={kycForm.first_name} onChange={(e) => setKycForm({ ...kycForm, first_name: e.target.value })} />
              </label>
              <label>{t('pf.kyc.lastName')}
                <input value={kycForm.last_name} onChange={(e) => setKycForm({ ...kycForm, last_name: e.target.value })} />
              </label>
            </div>
            <label>{t('pf.kyc.docType')}
              <select value={kycForm.document_type} onChange={(e) => setKycForm({ ...kycForm, document_type: e.target.value })}>
                {['ID card', 'Passport', 'Driver license'].map((d) => <option key={d}>{d}</option>)}
              </select>
            </label>
            <div className="row2">
              <label className="file-drop">
                {t('pf.kyc.docFront')} ({t('pf.required')})
                <input type="file" accept="image/*" required onChange={(e) => setKycForm({ ...kycForm, document_front: e.target.files[0] })} />
                <small>{kycForm.document_front?.name || 'JPG / PNG'}</small>
              </label>
              <label className="file-drop">
                {t('pf.kyc.docBack')}
                <input type="file" accept="image/*" onChange={(e) => setKycForm({ ...kycForm, document_back: e.target.files[0] })} />
                <small>{kycForm.document_back?.name || t('pf.optional')}</small>
              </label>
            </div>
            <label className="file-drop">
              {t('pf.kyc.selfie')} ({t('pf.required')})
              <input type="file" accept="image/*" required onChange={(e) => setKycForm({ ...kycForm, selfie: e.target.files[0] })} />
              <small>{kycForm.selfie?.name || 'JPG / PNG'}</small>
            </label>
            <button className="btn primary block" disabled={busy}>{busy ? t('pf.kyc.submitting') : t('pf.kyc.submit')}</button>
          </form>
        )}
      </div>

      <div className="card form">
        <h3>{t('pf.acc.title')}</h3>
        <p className="small muted">{t('pf.acc.hint')}</p>
        <div className="acc-list">
          {accounts.map((a) => (
            <div className="acc-row" key={a.id}>
              <span className="coin-fallback">{a.coin_symbol[0]}</span>
              <div>
                <b>{a.coin_symbol}</b>
                <code className="tx">{a.address}</code>
              </div>
              {a.is_primary && <span className="pill pill-light">{t('pf.acc.primary')}</span>}
              <button className="icon-btn danger" onClick={() => delAccount(a.id)} title={t('common.delete')}><Trash2 size={16} /></button>
            </div>
          ))}
          {accounts.length === 0 && <p className="muted small">{t('pf.acc.none')}</p>}
        </div>
        <form className="row-grid" onSubmit={addAccount}>
          <label>{t('invest.coin')}
            <select value={accForm.coin ?? ''} onChange={(e) => setAccForm({ ...accForm, coin: Number(e.target.value) })} required>
              {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol}</option>)}
            </select>
          </label>
          <label className="grow">{t('pf.acc.address')}
            <input value={accForm.address} onChange={(e) => setAccForm({ ...accForm, address: e.target.value })} placeholder={t('wd.addressPlaceholder')} required />
          </label>
          <button className="btn primary" disabled={busy}><Plus size={16} /> {t('pf.acc.add')}</button>
        </form>
      </div>

      <div className="card form danger-zone">
        <h3>{t('pf.danger')}</h3>
        <div className="row-actions">
          <button className="btn ghost" onClick={() => logout()}>
            <LogOut size={16} /> {t('nav.logout')}
          </button>
          <button className="btn danger" onClick={delAccountAll}>
            <Trash2 size={16} /> {t('pf.deleteAccount')}
          </button>
        </div>
      </div>
    </div>
  )
}