import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client, apiError } from '../api/client'
import { useI18n } from '../i18n'
import { useToast } from '../components/Toast'
import { fmt, fmtCrypto } from '../components/Format'
import Loading from '../components/Loading'
import { TrendingUp, Coins, ArrowDownToLine, Percent } from 'lucide-react'

export default function Growth() {
  const [data, setData] = useState(null)
  const { t } = useI18n()
  const { toast } = useToast()

  useEffect(() => {
    client
      .get('/growth/')
      .then((res) => setData(res.data))
      .catch((err) => toast(apiError(err), 'error'))
  }, [toast])

  if (!data) return <Loading />

  const { coins = [], totals = {} } = data
  const maxEarned = Math.max(...coins.map((c) => Number(c.earned) || 0), 0.00000001)

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('growth.title')}</h2>
          <p>{t('growth.subtitle')}</p>
        </div>
      </div>

      <div className="totals-grid">
        <div className="tcard">
          <div className="tcard-icon"><TrendingUp /></div>
          <span className="tlabel">{t('growth.invested')}</span>
          <span className="tvalue">$ {fmtCrypto(totals.invested)}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Coins /></div>
          <span className="tlabel">{t('growth.earned')}</span>
          <span className="tvalue">$ {fmtCrypto(totals.earned)}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><ArrowDownToLine /></div>
          <span className="tlabel">{t('growth.withdrawn')}</span>
          <span className="tvalue">$ {fmtCrypto(totals.withdrawn)}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Percent /></div>
          <span className="tlabel">{t('growth.totalGrowth')}</span>
          <span className="tvalue">{fmt(totals.growth_percent)}%</span>
        </div>
      </div>

      {coins.length === 0 ? (
        <div className="card" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <p className="muted" style={{ marginBottom: '1rem' }}>{t('growth.empty')}</p>
          <Link className="btn primary" to="/invest">{t('growth.startInvesting')}</Link>
        </div>
      ) : (
        <div className="card" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
          <strong>{t('growth.perCoin')}</strong>
          {coins.map((c) => (
            <div key={c.coin_id} className="growth-row">
              <div className="growth-row-head">
                <span className="growth-coin">
                  {c.icon_url ? (
                    <img src={c.icon_url} alt={c.symbol} />
                  ) : (
                    <span className="coin-fallback">{c.symbol?.slice(0, 1)}</span>
                  )}
                  <b>{c.symbol}</b>
                  <span className="muted small">{c.name}</span>
                </span>
                <span className={`growth-pct ${Number(c.growth_percent) >= 0 ? 'up' : 'down'}`}>
                  {Number(c.growth_percent) >= 0 ? '+' : ''}{fmt(c.growth_percent)}%
                </span>
              </div>
              <div className="growth-bar">
                <span style={{ width: `${Math.min(100, (Number(c.earned) / maxEarned) * 100)}%` }} />
              </div>
              <div className="growth-meta">
                <span>{t('growth.invested')}: <b>{fmtCrypto(c.invested_balance)} {c.symbol}</b></span>
                <span>{t('growth.earned')}: <b>{fmtCrypto(c.earned)} {c.symbol}</b></span>
                <span>{t('growth.withdrawn')}: <b>{fmtCrypto(c.withdrawn)} {c.symbol}</b></span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
