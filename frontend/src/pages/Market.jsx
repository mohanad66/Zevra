import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { client, apiError } from '../api/client'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt, percentageClass } from '../components/Format'
import { BarChart3, RefreshCw } from 'lucide-react'
import Loading from '../components/Loading'

function MiniChart({ change }) {
  const up = parseFloat(change) >= 0
  const h1 = up ? 12 : 22
  const h3 = up ? 10 : 26
  return (
    <svg className="mc" viewBox="0 0 90 36" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        points={`0,${up ? 24 : 14} 15,${up ? 20 : 16} 30,${up ? 26 : 20} 45,${up ? 16 : 22} 60,${up ? 18 : 24} 75,${up ? 10 : 28} 90,${up ? h1 : h3}`}
        fill="none"
        stroke={up ? '#22c55e' : '#ef4444'}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function Market() {
  const [data, setData] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const { toast } = useToast()
  const { t } = useI18n()
  const navigate = useNavigate()

  async function load(showToast = false) {
    try {
      const res = await client.get('/market/')
      setData(res.data)
      setLastUpdated(new Date())
      if (showToast) toast(t('market.updated'), 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    }
  }

  useEffect(() => {
    load()
    const t2 = setInterval(() => load(), 60000)
    return () => clearInterval(t2)
  }, [])

  const items = useMemo(() => data?.data ?? [], [data])

  if (!data) return <Loading />

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('market.title')}</h2>
          <p className="muted">
            <BarChart3 size={14} style={{ verticalAlign: 'middle' }} />{' '}
            {lastUpdated ? `${t('market.updatedAt')} ${lastUpdated.toLocaleTimeString()}` : t('market.live')}
          </p>
        </div>
        <button className="btn ghost" onClick={() => load(true)}>
          <RefreshCw size={16} /> {t('common.refresh')}
        </button>
      </div>

      <div className="mc-grid">
        {items.map((m) => {
          const cls = percentageClass(m.change_24h)
          const up = parseFloat(m.change_24h) >= 0
          return (
            <button className="mcard" key={m.coin.symbol} onClick={() => navigate(`/invest?coin=${m.coin.symbol}`)}>
              <div className="mcard-head">
                {m.coin.icon_url ? (
                  <img src={m.coin.icon_url} alt={m.coin.symbol} />
                ) : (
                  <span className="coin-fallback">{m.coin.symbol[0]}</span>
                )}
                <div className="mcard-info">
                  <div className="mcard-name">{m.coin.name}</div>
                  <div className="mcard-sym">{m.coin.symbol}</div>
                </div>
                <span className={`mcard-chg ${up ? 'up' : 'down'}`}>
                  {up ? '+' : ''}{fmt(m.change_24h, 2)}%
                </span>
              </div>
              <div className="mcard-price">
                <span className="mcard-price-val">${fmt(m.price, 8)}</span>
                <span className={`mcard-chg-sm ${cls}`}>
                  {t('market.h24Label')} {up ? '+' : ''}
                  {fmt(m.change_24h, 2)}%
                </span>
              </div>
              <div className="mcard-chart">
                <MiniChart change={m.change_24h} />
              </div>
              <div className="mcard-foot">
                {t('market.tradeWith', { symbol: m.coin.symbol })}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
