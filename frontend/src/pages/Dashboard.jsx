import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { fmtCrypto } from '../components/Format'
import { TrendingUp, Wallet, Users, Trophy, ArrowDownToLine, Copy, Check, RefreshCw, Gift, Clock, Loader2 } from 'lucide-react'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [windows, setWindows] = useState([])
  const [claiming, setClaiming] = useState(false)
  const [copied, setCopied] = useState(false)
  const { user, apiError } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()

  async function load() {
    try {
      const res = await client.get('/dashboard/')
      setData(res.data)
    } catch (err) {
      toast(apiError(err), 'error')
    }
  }

  async function loadWindows() {
    try {
      const res = await client.get('/payout-window/')
      setWindows(res.data ?? [])
    } catch (err) { toast(apiError(err), 'error') }
  }

  useEffect(() => {
    load()
    loadWindows()
  }, [])

  if (!data) return null

  async function claimWindow(id) {
    setClaiming(true)
    try {
      const res = await client.post('/payout-window/claim/', { window_id: id })
      toast(res.data.message, 'success')
      loadWindows()
      load()
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setClaiming(false) }
  }

  const copyInvite = () => {
    navigator.clipboard?.writeText(user?.invite_code || '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Dashboard</h2>
          <p>Welcome back, {data.user?.full_name || data.user?.email}</p>
        </div>
        <button className="btn ghost" onClick={load}><RefreshCw size={16} /> Refresh</button>
      </div>

      {windows.map((w) => (
        <div className="card payout-claim" key={w.id}>
          <div className="payout-claim-head">
            <span className="payout-claim-icon"><Gift size={20} /></span>
            <div>
              <h3>{w.title}</h3>
              <p className="muted small" style={{ margin: 0 }}>
                <Clock size={13} style={{ verticalAlign: 'middle' }} />
                {Math.round(w.time_left_hours)}h left · you receive {w.percent}% of your invested balance
                {w.coin_symbol ? ` in ${w.coin_symbol}` : ' (all coins)'}
              </p>
            </div>
          </div>
          <div className="payout-claim-preview">
            {w.preview.map((p) => (
              <span key={p.coin_symbol}>
                <b>+{fmtCrypto(p.amount)} {p.coin_symbol}</b>
                <i>on {fmtCrypto(p.invested_balance)} invested</i>
              </span>
            ))}
          </div>
          {w.claimed ? (
            <span className="pill" style={{ background: 'var(--accent)', color: '#fff' }}>
              <Check size={13} style={{ verticalAlign: 'middle' }} /> Claimed
            </span>
          ) : (
            <button className="btn success lg" disabled={claiming} onClick={() => claimWindow(w.id)}>
              {claiming ? <Loader2 size={16} className="spin" /> : <Gift size={16} />} {claiming ? 'Claiming…' : 'Claim my payout'}
            </button>
          )}
        </div>
      ))}

      <div className="totals-grid">
        <div className="tcard">
          <div className="tcard-icon"><TrendingUp /></div>
          <span className="tlabel">Invested balance</span>
          <span className="tvalue">$ {fmtCrypto(data.totals.total_invested)}</span>
          <span className="tnote">Locked into your investments</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Wallet /></div>
          <span className="tlabel">Withdrawable balance</span>
          <span className="tvalue">$ {fmtCrypto(data.totals.total_withdrawable)}</span>
          <span className="tnote">Referral awards + payouts, ready to withdraw</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Users /></div>
          <span className="tlabel">Referral earnings</span>
          <span className="tvalue">3 levels</span>
          <span className="tnote">Invite others and earn on each level</span>
        </div>
      </div>

      <div className="invite-banner">
        <div>
          <strong>Your invite code</strong>
          <span className="code">{user?.invite_code}</span>
        </div>
        <button className="btn primary" onClick={copyInvite}>
          {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? 'Copied!' : 'Copy'}
        </button>
        <p className="small muted">
          Share your code — friends invest {data.settings?.referral_levels?.[0]?.percent}% to you on level 1.
        </p>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>Your coin wallets</h3>
          <span className="muted small">Click a coin to invest — use 'View details' for balances</span>
        </div>
        <div className="wallet-grid">
          {data.wallets.length === 0 && <p className="muted">No wallets yet. <Link to="/invest">Make your first investment →</Link></p>}
          {data.wallets.map((w) => (
            <div
              key={w.coin.id}
              className="wallet-card"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/invest?coin=${w.coin.symbol}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(`/invest?coin=${w.coin.symbol}`)
                }
              }}
            >
              <div className="wallet-top">
                {w.coin.icon_url ? <img src={w.coin.icon_url} alt={w.coin.symbol} /> : <span className="coin-fallback">{w.coin.symbol[0]}</span>}
                <span className="coin-name">{w.coin.name}</span>
                <span className="coin-symbol">{w.coin.symbol}</span>
              </div>
              <div className="wallet-bals">
                <span><i>Invested</i><b>{fmtCrypto(w.invested_balance)}</b></span>
                <span><i>Withdrawable</i><b>{fmtCrypto(w.withdrawable_balance)}</b></span>
              </div>
              <span
                className="wallet-link"
                role="button"
                tabIndex={0}
                onClick={(e) => { e.stopPropagation(); navigate(`/wallet/${w.coin.id}`) }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation()
                    e.preventDefault()
                    navigate(`/wallet/${w.coin.id}`)
                  }
                }}
              >View details →</span>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>Recent activity</h3>
        <div className="activity">
          {data.activity.length === 0 && <p className="muted">No activity yet.</p>}
          {data.activity.map((a) => (
            <div className="act-row" key={`${a.type}-${a.id}`}>
              <span className={`act-icon act-${a.type}`}>
                {a.type === 'invest' && <TrendingUp size={16} />}
                {a.type === 'withdraw' && <ArrowDownToLine size={16} />}
                {a.type === 'payout' && <Trophy size={16} />}
                {a.type === 'award' && <Wallet size={16} />}
              </span>
              <div className="act-meta">
                <strong>{a.title}</strong>
                <span className="muted small">{new Date(a.created_at).toLocaleString()}</span>
              </div>
              <span className="pill pill-light">{a.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}