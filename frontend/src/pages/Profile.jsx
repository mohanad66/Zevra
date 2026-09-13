import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { client } from '../api/client'
import { Camera, ShieldCheck, KeyRound, LogOut, Trash2, Plus } from 'lucide-react'

const KYC_LABEL = { pending: 'Pending review', approved: 'Verified', rejected: 'Rejected', verified: 'Verified', not_submitted: 'Not submitted' }

export default function Profile() {
  const { user, refreshUser, logout, apiError } = useAuth()
  const { toast } = useToast()
  const [profile, setProfile] = useState({ email: '', first_name: '', last_name: '', phone: '' })
  const [avatar, setAvatar] = useState(null)
  const [pwd, setPwd] = useState({ old_password: '', new_password: '' })
  const [kyc, setKyc] = useState({ status: 'not_submitted', required_to_invest: false, required_to_withdraw: false })
  const [kycForm, setKycForm] = useState({ document_type: 'ID', document_front: null, document_back: null, selfie: null })
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
    if (user) setProfile({ email: user.email, first_name: user.first_name, last_name: user.last_name, phone: user.phone || '' })
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
      toast('Profile updated', 'success')
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
      toast('Password changed', 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function submitKyc(e) {
    e.preventDefault()
    if (!kycForm.document_front) { toast('Upload at least your document front image', 'error'); return }
    setBusy(true)
    try {
      const form = new FormData()
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
    if (!accForm.address.trim()) { toast('Enter an address', 'error'); return }
    setBusy(true)
    try {
      await client.post('/accounts/', { coin: accForm.coin, address: accForm.address, label: accForm.label })
      setAccForm({ coin: accForm.coin, address: '', label: '' })
      await load()
      toast('Crypto account saved', 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function delAccount(id) {
    try {
      await client.delete(`/accounts/${id}/`)
      await load()
      toast('Account removed', 'success')
    } catch (err) { toast(apiError(err), 'error') }
  }

  async function delAccountAll() {
    if (!window.confirm('Delete your account? This cannot be undone.')) return
    try {
      await client.post('/auth/delete/')
      toast('Account deleted', 'success')
      await logout()
    } catch (err) { toast(apiError(err), 'error') }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div><h2>Profile</h2><p>Manage your identity, security and verification.</p></div>
      </div>

      <div className="profile-grid">
        <form className="card form" onSubmit={saveProfile}>
          <h3>Personal info</h3>
          <div className="avatar-row">
            {avatar ? (
              <img className="avatar lg" src={URL.createObjectURL(avatar)} alt="" />
            ) : user?.avatar_url ? (
              <img className="avatar lg" src={user.avatar_url} alt="" />
            ) : (
              <span className="avatar-fallback lg">{user?.email?.[0]?.toUpperCase()}</span>
            )}
            <label className="btn ghost file-btn">
              <Camera size={16} /> Change photo
              <input type="file" accept="image/*" onChange={(e) => setAvatar(e.target.files[0])} hidden />
            </label>
          </div>
          <div className="row2">
            <label>First name
              <input value={profile.first_name} onChange={(e) => setProfile({ ...profile, first_name: e.target.value })} />
            </label>
            <label>Last name
              <input value={profile.last_name} onChange={(e) => setProfile({ ...profile, last_name: e.target.value })} />
            </label>
          </div>
          <div className="row2">
            <label>Email
              <input
                type="email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                required
              />
            </label>
            <label>Phone
              <input value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} placeholder="Optional" />
            </label>
          </div>
          <button className="btn primary block" disabled={busy}>Save profile</button>
        </form>

        <form className="card form" onSubmit={changePassword}>
          <h3><KeyRound size={18} /> Change password</h3>
          <label>Current password
            <input type="password" value={pwd.old_password} onChange={(e) => setPwd({ ...pwd, old_password: e.target.value })} required />
          </label>
          <label>New password
            <input type="password" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} required minLength={8} />
          </label>
          <button className="btn primary block" disabled={busy}>Update password</button>
        </form>
      </div>

      <div className="card form">
        <h3><ShieldCheck size={18} /> KYC verification</h3>
        <div className="kyc-status">
          <span className={`pill pill-${kyc.kyc_verified ? 'completed' : kyc.kyc_rejected ? 'rejected' : 'pending'}`}>
            {kyc.kyc_verified ? 'Verified' : kyc.kyc_rejected ? 'Rejected' : KYC_LABEL[kyc.status] || kyc.status}
          </span>
          {kyc.required_to_invest && <span className="muted small">Required to invest</span>}
          {kyc.required_to_withdraw && <span className="muted small">Required to withdraw</span>}
          {kyc.reason && <p className="small warn-text">Reason: {kyc.reason}</p>}
        </div>

        {!kyc.kyc_verified && (
          <form onSubmit={submitKyc}>
            <label>Document type
              <select value={kycForm.document_type} onChange={(e) => setKycForm({ ...kycForm, document_type: e.target.value })}>
                {['ID card', 'Passport', 'Driver license'].map((d) => <option key={d}>{d}</option>)}
              </select>
            </label>
            <div className="row2">
              <label className="file-drop">
                Front of document (required)
                <input type="file" accept="image/*" required onChange={(e) => setKycForm({ ...kycForm, document_front: e.target.files[0] })} />
                <small>{kycForm.document_front?.name || 'JPG / PNG'}</small>
              </label>
              <label className="file-drop">
                Back of document
                <input type="file" accept="image/*" onChange={(e) => setKycForm({ ...kycForm, document_back: e.target.files[0] })} />
                <small>{kycForm.document_back?.name || 'Optional'}</small>
              </label>
            </div>
            <label className="file-drop">
              Selfie with ID (required)
              <input type="file" accept="image/*" required onChange={(e) => setKycForm({ ...kycForm, selfie: e.target.files[0] })} />
              <small>{kycForm.selfie?.name || 'JPG / PNG'}</small>
            </label>
            <button className="btn primary block" disabled={busy}>Submit for review</button>
          </form>
        )}
      </div>

      <div className="card form">
        <h3>Your crypto accounts</h3>
        <p className="small muted">These addresses receive withdrawals and admin payouts.</p>
        <div className="acc-list">
          {accounts.map((a) => (
            <div className="acc-row" key={a.id}>
              <span className="coin-fallback">{a.coin_symbol[0]}</span>
              <div>
                <b>{a.coin_symbol}</b>
                <code className="tx">{a.address}</code>
              </div>
              {a.is_primary && <span className="pill pill-light">primary</span>}
              <button className="icon-btn danger" onClick={() => delAccount(a.id)} title="Delete"><Trash2 size={16} /></button>
            </div>
          ))}
          {accounts.length === 0 && <p className="muted small">No accounts added yet.</p>}
        </div>
        <form className="row-grid" onSubmit={addAccount}>
          <label>Coin
            <select value={accForm.coin ?? ''} onChange={(e) => setAccForm({ ...accForm, coin: Number(e.target.value) })} required>
              {coins.map((c) => <option key={c.id} value={c.id}>{c.symbol}</option>)}
            </select>
          </label>
          <label className="grow">Address
            <input value={accForm.address} onChange={(e) => setAccForm({ ...accForm, address: e.target.value })} placeholder="Wallet address" required />
          </label>
          <button className="btn primary" disabled={busy}><Plus size={16} /> Add</button>
        </form>
      </div>

      <div className="card form danger-zone">
        <h3>Account</h3>
        <div className="row-actions">
          <button className="btn ghost" onClick={() => logout()}>
            <LogOut size={16} /> Log out
          </button>
          <button className="btn danger" onClick={delAccountAll}>
            <Trash2 size={16} /> Delete account
          </button>
        </div>
      </div>
    </div>
  )
}