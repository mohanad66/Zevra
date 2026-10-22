import { useEffect, useMemo, useState } from 'react'
import { client, apiError } from '../api/client'
import { useI18n } from '../i18n'
import { useToast } from '../components/Toast'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { Trophy, Gift, Clock, Check, Loader2 } from 'lucide-react'
import Loading from '../components/Loading'

const RECEIVED = new Set(['completed', 'paid', 'approved', 'success'])

export default function Payouts() {
  const [payouts, setPayouts] = useState([])
  const [windows, setWindows] = useState([])
  const [claiming, setClaiming] = useState(false)
  const [loading, setLoading] = useState(true)
  const { t } = useI18n()
  const { toast } = useToast()

  function loadWindows() {
    return client
      .get('/payout-window/')
      .then((res) => setWindows(res.data ?? []))
      .catch((err) => toast(apiError(err), 'error'))
  }

  useEffect(() => {
    Promise.allSettled([
      client.get('/payouts/').then((res) => setPayouts(res.data ?? [])),
      client.get('/payout-window/').then((res) => setWindows(res.data ?? [])),
    ]).finally(() => setLoading(false))
  }, [])

  const totalReceived = useMemo(
    () =>
      payouts
        .filter((p) => RECEIVED.has(String(p.status).toLowerCase()))
        .reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0),
    [payouts]
  )

  async function claimWindow(id) {
    setClaiming(true)
    try {
      const res = await client.post('/payout-window/claim/', { window_id: id })
      toast(res.data.message, 'success')
      await Promise.all([
        loadWindows(),
        client.get('/payouts/').then((res) => setPayouts(res.data ?? [])),
      ])
    } catch (err) {
      toast(apiError(err), 'error')
    } finally {
      setClaiming(false)
    }
  }

  if (loading) return <Loading />

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('po.title')}</h2>
          <p>{t('po.subtitle')}</p>
        </div>
      </div>

      <div className="po-hero">
        <div>
          <span className="deposit-amount-label">{t('po.totalReceived')}</span>
          <span className="po-hero-value">$ {fmtCrypto(totalReceived)}</span>
          <span className="quick-deposit-note">{t('po.allTime')}</span>
        </div>
        <span className="po-hero-icon"><Trophy size={26} /></span>
      </div>

      <section className="section">
        <div className="section-head">
          <h3>{t('po.openWindows')}</h3>
        </div>
        {windows.length === 0 ? (
          <p className="muted">{t('po.noWindows')}</p>
        ) : (
          <div className="po-window-grid">
            {windows.map((w) => (
              <div className={`po-window ${w.claimed ? 'claimed' : ''}`} key={w.id}>
                <div className="po-window-top">
                  <span className="po-window-icon"><Gift size={20} /></span>
                  <span className="pill pill-light"><Clock size={12} /> {t('po.timeLeft', { hours: Math.round(w.time_left_hours) })}</span>
                </div>
                <div className="po-window-rate">
                  <b>{w.percent}%</b>
                  <span className="muted small">{t('po.payoutRate')}</span>
                </div>
                <div className="po-window-preview">
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
                  <button className="btn primary lg block" disabled={claiming} onClick={() => claimWindow(w.id)}>
                    {claiming ? <Loader2 size={16} className="spin" /> : <Gift size={16} />}{' '}
                    {claiming ? t('dash.claiming') : t('dash.claimPayout')}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h3>{t('po.tabHistory')}</h3>
          <span className="muted small">{payouts.length}</span>
        </div>
        {payouts.length === 0 ? (
          <p className="muted">{t('po.noHistory')}</p>
        ) : (
          <div className="po-history">
            {payouts.map((p) => (
              <div className="po-history-row" key={p.id}>
                <span className="po-history-icon"><Trophy size={18} /></span>
                <div className="po-history-meta">
                  <b>{fmtCrypto(p.amount)} {p.coin_symbol}</b>
                  <span className="muted small">
                    {new Date(p.created_at).toLocaleString()}
                    {p.note ? ` · ${p.note}` : ''}
                  </span>
                  {p.tx_hash ? <code className="tx po-history-tx">{p.tx_hash.slice(0, 24)}…</code> : null}
                </div>
                <div className="po-history-side">
                  {p.is_bonus && <span className="pill pill-light">{p.percent}% {t('po.bonus')}</span>}
                  <StatusBadge status={p.status_display} />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
