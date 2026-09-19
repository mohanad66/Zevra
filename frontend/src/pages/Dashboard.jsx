import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmtCrypto } from '../components/Format'
import { TrendingUp, Wallet, Users, Trophy, ArrowDownToLine, Copy, Check, RefreshCw, Gift, Clock, Loader2 } from 'lucide-react'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [windows, setWindows] = useState([])
  const [claiming, setClaiming] = useState(false)
  const [copied, setCopied] = useState(false)
  const { user, apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
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

  const actTitle = (a) => {
    const key = `act.${a.type}`
    if (a.symbol) return t(key, { amount: fmtCrypto(a.amount), symbol: a.symbol })
    return a.title || t(key)
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('dash.title')}</h2>
          <p>{t('dash.subtitle')} {data.user?.full_name || data.user?.email}</p>
        </div>
        <button className="btn ghost" onClick={load}><RefreshCw size={16} /> {t('common.refresh')}</button>
      </div>

      {windows.map((w) => (
        <div className="card payout-claim" key={w.id}>
          <div className="payout-claim-head">
            <span className="payout-claim-icon"><Gift size={20} /></span>
            <div>
              <h3>{w.title}</h3>
              <p className="muted small" style={{ margin: 0 }}>
                <Clock size={13} style={{ verticalAlign: 'middle' }} />
                {t('dash.windowInfo', { hours: Math.round(w.time_left_hours), percent: w.percent, coins: w.coin_symbol ? ` ${w.coin_symbol}` : t('dash.allCoins') })}
              </p>
            </div>
          </div>
          <div className="payout-claim-preview">
            {w.preview.map((p) => (
              <span key={p.coin_symbol}>
                <b>+{fmtCrypto(p.amount)} {p.coin_symbol}</b>
                <i>{t('dash.onInvested', { amount: fmtCrypto(p.invested_balance), symbol: p.coin_symbol })}</i>
              </span>
            ))}
          </div>
          {w.claimed ? (
            <span className="pill" style={{ background: 'var(--accent)', color: '#fff' }}>
              <Check size={13} style={{ verticalAlign: 'middle' }} /> {t('dash.claimed')}
            </span>
          ) : (
            <button className="btn success lg" disabled={claiming} onClick={() => claimWindow(w.id)}>
              {claiming ? <Loader2 size={16} className="spin" /> : <Gift size={16} />} {claiming ? t('dash.claiming') : t('dash.claimPayout')}
            </button>
          )}
        </div>
      ))}

      <div className="totals-grid">
        <div className="tcard">
          <div className="tcard-icon"><TrendingUp /></div>
          <span className="tlabel">{t('dash.investedBalance')}</span>
          <span className="tvalue">$ {fmtCrypto(data.totals.total_invested)}</span>
          <span className="tnote">{t('dash.lockedIn')}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Wallet /></div>
          <span className="tlabel">{t('dash.withdrawableBalance')}</span>
          <span className="tvalue">$ {fmtCrypto(data.totals.total_withdrawable)}</span>
          <span className="tnote">{t('dash.readyToWithdraw')}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Users /></div>
          <span className="tlabel">{t('dash.referralEarnings')}</span>
          <span className="tvalue">3 {t('dash.levels')}</span>
          <span className="tnote">{t('dash.inviteEarn')}</span>
        </div>
      </div>

      <div className="invite-banner">
        <div>
          <strong>{t('dash.inviteCode')}</strong>
          <span className="code">{user?.invite_code}</span>
        </div>
        <button className="btn primary" onClick={copyInvite}>
          {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? t('common.copied') : t('common.copy')}
        </button>
        <p className="small muted">
          {t('dash.shareHint', { percent: data.settings?.referral_levels?.[0]?.percent })}
        </p>
      </div>

      <div className="section">
        <div className="section-head">
          <h3>{t('dash.holdings')}</h3>
          <span className="muted small">{t('dash.clickToInvest')}</span>
        </div>
        <div className="wallet-grid">
          {data.wallets.length === 0 && <p className="muted">{t('dash.noWallets')} <Link to="/invest">{t('dash.firstInvestment')} →</Link></p>}
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
                <span><i>{t('wd2.invested')}</i><b>{fmtCrypto(w.invested_balance)}</b></span>
                <span><i>{t('wd2.withdrawable')}</i><b>{fmtCrypto(w.withdrawable_balance)}</b></span>
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
              >{t('dash.viewDetails')} →</span>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>{t('dash.recentActivity')}</h3>
        <div className="activity">
          {data.activity.length === 0 && <p className="muted">{t('dash.noActivity')}</p>}
          {data.activity.map((a) => (
            <div className="act-row" key={`${a.type}-${a.id}`}>
              <span className={`act-icon act-${a.type}`}>
                {a.type === 'invest' && <TrendingUp size={16} />}
                {a.type === 'withdraw' && <ArrowDownToLine size={16} />}
                {a.type === 'payout' && <Trophy size={16} />}
                {a.type === 'award' && <Wallet size={16} />}
              </span>
              <div className="act-meta">
                <strong>{actTitle(a)}</strong>
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