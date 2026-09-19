import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { client, apiError } from '../api/client'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt, percentageClass } from '../components/Format'
import { RefreshCw } from 'lucide-react'

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

  if (!data) return null

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('market.title')}</h2>
          <p className="muted">
            {lastUpdated ? `${t('market.updatedAt')} ${lastUpdated.toLocaleTimeString()}` : t('market.live')}
          </p>
        </div>
        <button className="btn ghost" onClick={() => load(true)}>
          <RefreshCw size={16} /> {t('common.refresh')}
        </button>
      </div>

      <div className="market-grid">
        {data.data.map((m) => {
          const cls = percentageClass(m.change_24h)
          return (
            <div
              className="market-card"
              key={m.coin.symbol}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/invest?coin=${m.coin.symbol}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(`/invest?coin=${m.coin.symbol}`)
                }
              }}
            >
              <div className="market-top">
                {m.coin.icon_url ? (
                  <img src={m.coin.icon_url} alt={m.coin.symbol} />
                ) : (
                  <span className="coin-fallback">{m.coin.symbol[0]}</span>
                )}
                <div>
                  <strong>{m.coin.name}</strong>
                  <span className="muted small">{m.coin.symbol} · {m.coin.chain}</span>
                </div>
                <span className={`pill ${m.coin.is_stable ? 'pill-light' : 'pill-accent'}`}>
                  {m.coin.is_stable ? t('market.stable') : t('market.crypto')}
                </span>
              </div>
              <div className="market-price">
                <span className="mp-label">{t('market.priceUsd')}</span>
                <span className="mp-value">${fmt(m.price, 8)}</span>
                <span className={`mp-change ${cls}`}>{t('market.h24')}: {sign(m.change_24h)} {fmt(m.change_24h, 2)}%</span>
              </div>
              <span className="market-invest">{t('market.invest', { symbol: m.coin.symbol })}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function sign(v) {
  return parseFloat(v) >= 0 ? '+' : ''
}