import { useEffect, useState } from 'react'
import { client, apiError } from '../api/client'
import { useI18n } from '../i18n'
import { useToast } from '../components/Toast'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { Trophy, Gift, Clock, Check, Loader2 } from 'lucide-react'
import Loading from '../components/Loading'

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

  async function claimWindow(id) {
    setClaiming(true)
    try {
      const res = await client.post('/payout-window/claim/', { window_id: id })
      toast(res.data.message, 'success')
      await loadWindows()
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

      {windows.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
          {windows.map((w) => (
            <div className="card payout-claim" key={w.id}>
              <div className="payout-claim-head">
                <span className="payout-claim-icon"><Gift size={20} /></span>
                <div>
                  <h3>{t('dash.payoutTitle')}</h3>
                  <p className="muted small" style={{ margin: 0 }}>
                    <Clock size={13} style={{ verticalAlign: 'middle' }} />
                    {t('dash.windowInfo', {
                      hours: Math.round(w.time_left_hours),
                      percent: w.percent,
                      coins: w.coin_symbol ? ` ${w.coin_symbol}` : t('dash.allCoins'),
                    })}
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
                  {claiming ? <Loader2 size={16} className="spin" /> : <Gift size={16} />}{' '}
                  {claiming ? t('dash.claiming') : t('dash.claimPayout')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {payouts.length === 0 ? (
        <p className="muted">{t('po.noHistory')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t('wd.amountLabel')}</th><th>{t('common.status')}</th><th>TX hash</th><th>{t('po.note')}</th><th>{t('common.date')}</th></tr>
            </thead>
            <tbody>
              {payouts.map((p) => (
                <tr key={p.id}>
                  <td>
                    <b>{fmtCrypto(p.amount)} {p.coin_symbol}</b>
                    {p.is_bonus && <span className="pill pill-light">{p.percent}% {t('po.bonus')}</span>}
                  </td>
                  <td><span className="act-icon act-payout"><Trophy size={14} /></span>{' '}<StatusBadge status={p.status_display} /></td>
                  <td><code className="tx">{p.tx_hash?.slice(0, 20) || '—'}</code></td>
                  <td>{p.note || '—'}</td>
                  <td>{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
