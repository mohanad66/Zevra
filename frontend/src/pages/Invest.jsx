import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt } from '../components/Format'
import { TrendingUp, ExternalLink, CheckCircle2, Clipboard, Loader2 } from 'lucide-react'

export default function Invest() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const [searchParams] = useSearchParams()
  const [coins, setCoins] = useState([])
  const [accounts, setAccounts] = useState([])
  const [coinId, setCoinId] = useState(null)
  const [amount, setAmount] = useState('')
  const [sourceAddress, setSourceAddress] = useState('')
  const [phase, setPhase] = useState('form')
  const [payment, setPayment] = useState(null)
  const [busy, setBusy] = useState(false)
  const coinParam = (searchParams.get('coin') || '').trim()

  useEffect(() => {
    client.get('/coins/').then((res) => {
      setCoins(res.data)
      if (res.data.length) setCoinId(res.data[0].id)
    }).catch(() => {})
    client.get('/accounts/').then((res) => {
      setAccounts(res.data ?? [])
      if (res.data?.length) setSourceAddress(res.data[0].address)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!coinParam || !coins.length) return
    const want = coinParam.toLowerCase()
    const match = coins.find(
      (c) => String(c.symbol).toLowerCase() === want || String(c.id) === coinParam
    )
    if (match) {
      setCoinId(match.id)
      setAmount('')
    }
  }, [coinParam, coins])

  const coin = useMemo(() => coins.find((c) => c.id === coinId), [coins, coinId])

  async function createOrder(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const res = await client.post('/invest/', {
        coin_id: coinId,
        amount: parseFloat(amount),
        source_address: sourceAddress,
      })
      setPayment(res.data.payment)
      setPhase('checkout')
      toast(res.data.message, 'success')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  async function confirmPayment() {
    if (!payment?.order_ref) return
    setBusy(true)
    try {
      const res = await client.post('/invest/confirm/', { order_ref: payment.order_ref })
      toast(res.data.message, 'success')
      setPhase('confirmed')
    } catch (err) {
      toast(apiError(err), 'error')
    } finally { setBusy(false) }
  }

  function copy(text) {
    navigator.clipboard.writeText(text).then(() => toast(t('common.copied'), 'success')).catch(() => {})
  }

  if (!coin) return <div className="page"><p className="muted">{t('invest.noCoins')}</p></div>

  if (phase === 'confirmed') {
    return (
      <div className="page">
        <div className="page-head"><div><h2>{t('invest.title')}</h2></div></div>
        <div className="card form" style={{ textAlign: 'center', padding: '2rem' }}>
          <CheckCircle2 size={48} color="var(--accent)" />
          <h3 style={{ margin: '1rem 0 .5rem' }}>{t('invest.confirmedTitle')}</h3>
          <p className="muted">{t('invest.confirmedBody')}</p>
          <Link to="/dashboard" className="btn primary" style={{ marginTop: '1rem' }}>{t('invest.openDashboard')}</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('invest.title')}</h2>
          <p>{t('invest.subtitle')}</p>
        </div>
      </div>

      {phase === 'form' ? (
        <form className="card form" onSubmit={createOrder}>
          <div className="coin-picker">
            {coins.map((c) => (
              <button
                type="button"
                key={c.id}
                className={`coin-opt ${c.id === coinId ? 'active' : ''}`}
                onClick={() => setCoinId(c.id)}
              >
                {c.icon_url ? <img src={c.icon_url} alt="" /> : <span className="coin-fallback">{c.symbol[0]}</span>}
                <span><b>{c.name}</b><small>{c.symbol} · {c.chain}</small></span>
              </button>
            ))}
          </div>

          <div className="invest-summary">
            <span><i>{t('invest.selectedCoin')}</i><b>{coin.name} ({coin.symbol})</b></span>
            <span><i>{t('invest.price')}</i><b>${fmt(coin.current_price, 8)}</b></span>
            <span><i>{t('invest.min')}</i><b>{fmt(coin.min_invest)} {coin.symbol}</b></span>
          </div>

          <label>
            {t('invest.toInvest')}
            <input
              type="number"
              min={parseFloat(coin.min_invest) || 0}
              step="any"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={`${t('invest.min')} ${coin.min_invest} ${coin.symbol}`}
              required
            />
          </label>
          <div className="quick-amounts">
            {[50, 100, 250, 500].map((q) => (
              <button type="button" className="chip" key={q} onClick={() => setAmount(String(q))}>
                {q} {coin.symbol}
              </button>
            ))}
          </div>

          <label>
            {t('invest.payFrom')}
            <input
              value={sourceAddress}
              onChange={(e) => setSourceAddress(e.target.value)}
              placeholder="TRC20 / ERC20 / …"
              required
            />
          </label>
          {accounts.length > 0 && (
            <div className="saved-accounts">
              <span className="muted small">{t('wd.savedAccounts')}</span>
              {accounts.map((a) => (
                <button
                  type="button"
                  key={a.id}
                  className={`chip ${sourceAddress === a.address ? 'chip-active' : ''}`}
                  onClick={() => setSourceAddress(a.address)}
                >
                  {a.coin_symbol} · {a.address.slice(0, 10)}…
                </button>
              ))}
            </div>
          )}

          <p className="small muted">
            {t('invest.gatewayHint')}
          </p>

          <button className="btn primary lg block" disabled={busy}>
            <TrendingUp size={18} /> {busy ? t('invest.processing') : t('invest.payAmount', { amount: amount || '0', symbol: coin.symbol })}
          </button>
        </form>
      ) : phase === 'checkout' ? (
        <div className="card form checkout-box">
          <h3>{t('invest.completePayment')}</h3>
          <p className="small muted">{t('invest.completeHint')}</p>

          <div className="checkout-amount">
            <span className="checkout-amt-value">{fmt(payment.pay_amount ?? payment.amount)}</span>
            <span className="checkout-amt-symbol">{payment.pay_currency || payment.coin_symbol}</span>
          </div>

          {payment.payment_mode === 'manual' ? (
            <div className="notice">
              {t('invest.manualHint')}
            </div>
          ) : null}

          {payment.checkout_url ? (
            <a className="btn primary lg block" href={payment.checkout_url} target="_blank" rel="noreferrer" style={{ marginBottom: '1rem', textAlign: 'center' }}>
              <ExternalLink size={18} /> {t('invest.openGateway')}
            </a>
          ) : null}

          {payment.address ? (
            <label className="checkout-address-label">
              {t('invest.depositAddress')} <span className="pill pill-light">{payment.chain}</span>
              <div className="checkout-addr">
                <code className="tx" style={{ fontSize: '13px', lineHeight: '2' }}>{payment.address}</code>
                <button type="button" className="icon-btn" title={t('common.copy')} onClick={() => copy(payment.address)}><Clipboard size={16} /></button>
              </div>
            </label>
          ) : null}

          {payment.payment_mode === 'manual' ? (
            <p className="small muted">{t('invest.awaitingAdmin')}</p>
          ) : (
            <button className="btn success lg block" style={{ marginTop: '1rem' }} disabled={busy} onClick={confirmPayment}>
              {busy ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />} {busy ? t('invest.confirming') : t('invest.completedPayment')}
            </button>
          )}

          <button className="btn ghost" style={{ marginTop: '.5rem' }} onClick={() => { setPhase('form'); setPayment(null) }}>
            {t('invest.newOrder')}
          </button>
        </div>
      ) : null}
    </div>
  )
}