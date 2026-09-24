import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt } from '../components/Format'
import { TrendingUp, CheckCircle2, Clipboard, Loader2 } from 'lucide-react'

// Networks the customer can pay on. PayRam only deploys real deposit addresses
// on Tron, Polygon, Ethereum, Base and Bitcoin, so every enabled choice must
// match _PAYRAM_DEPOSIT_CODES in backend/api/services.py. BEP20 / SOL have no
// PayRam deposit wallet yet, so they stay disabled ("coming soon").
const NETWORKS = [
  { id: 'TRC20', label: 'TRC20', hint: 'Tron', enabled: true },
  { id: 'POL', label: 'POL', hint: 'Polygon', enabled: true },
  { id: 'BEP20', label: 'BEP20', hint: 'BNB Chain', enabled: false },
  { id: 'SOL', label: 'SOL', hint: 'Solana', enabled: false },
]

export default function Invest() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const { t, lang } = useI18n()
  const [searchParams] = useSearchParams()
  const [coins, setCoins] = useState([])
  const [coinId, setCoinId] = useState(null)
  const [amount, setAmount] = useState('')
  const [network, setNetwork] = useState(NETWORKS.find((n) => n.enabled).id)
  const [phase, setPhase] = useState('form')
  const [payment, setPayment] = useState(null)
  const [busy, setBusy] = useState(false)
  const coinParam = (searchParams.get('coin') || '').trim()
  const ar = lang === 'ar'

  useEffect(() => {
    client.get('/coins/').then((res) => {
      setCoins(res.data)
      if (res.data.length) setCoinId(res.data[0].id)
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

  const isAllowed = (n) => n.enabled

  async function createOrder(e) {
    e.preventDefault()
    setBusy(true)
    try {
      // The backend reads the chosen network from `source_address`
      // (existing field, so no database migration is needed).
      const res = await client.post('/invest/', {
        coin_id: coinId,
        amount: parseFloat(amount),
        source_address: network,
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

  // Provider checkout: PayRam watches the deposit address and confirms the
  // payment on its side. We poll our backend so the user stays on this page —
  // "checking" until PayRam reports the order filled, then we switch to the
  // confirmed screen automatically.
  useEffect(() => {
    if (phase !== 'checkout' || payment?.payment_mode !== 'provider' || !payment?.order_ref) return
    let active = true
    const check = async () => {
      try {
        const res = await client.get('/invest/status/', { params: { order_ref: payment.order_ref } })
        const st = res.data || {}
        if (!active) return
        if (st.status === 'paid') {
          setPhase('confirmed')
          toast(st.message || t('invest.confirmed'), 'success')
        } else if (st.status === 'failed') {
          toast(st.message || t('invest.paymentExpired'), 'error')
          setPhase('form')
          setPayment(null)
        }
      } catch (err) {
        if (!active) return
        if (err?.response?.status === 404) {
          toast(t('invest.paymentExpired'), 'error')
          setPhase('form')
          setPayment(null)
        }
      }
    }
    check()
    const id = setInterval(check, 5000)
    return () => { active = false; clearInterval(id) }
  }, [phase, payment])

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
                <span><b>{c.name}</b><small>{c.symbol}</small></span>
              </button>
            ))}
          </div>

          <div className="invest-summary">
            <span><i>{t('invest.selectedCoin')}</i><b>{coin.name} ({coin.symbol})</b></span>
            <span><i>{t('invest.price')}</i><b>${fmt(coin.current_price, 8)}</b></span>
            <span><i>{t('invest.min')}</i><b>{fmt(coin.min_invest)} {coin.symbol}</b></span>
            <span><i>{ar ? 'شبكة الدفع' : 'Network'}</i><b>{network}</b></span>
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

          <div className="saved-accounts" role="radiogroup" aria-label={ar ? 'شبكة الدفع' : 'Payment network'}>
            <span className="muted small">{ar ? 'ادفع عبر شبكة' : 'Pay on network'}</span>
            {NETWORKS.map((n) => {
              const ok = isAllowed(n)
              const why = ar ? 'قريباً' : 'coming soon'
              return (
                <button
                  type="button"
                  key={n.id}
                  role="radio"
                  aria-checked={network === n.id}
                  disabled={!ok}
                  title={ok ? n.hint : `${n.hint} — ${why}`}
                  className={`chip ${network === n.id ? 'chip-active' : ''}`}
                  style={ok ? undefined : { opacity: 0.45, cursor: 'not-allowed' }}
                  onClick={() => ok && setNetwork(n.id)}
                >
                  {n.label} · {n.hint}{n.enabled ? '' : ` (${ar ? 'قريباً' : 'soon'})`}
                </button>
              )
            })}
          </div>

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
            <span className="pill pill-light" style={{ marginInlineStart: '.5rem' }}>{payment.chain || network}</span>
          </div>

          {payment.payment_mode === 'manual' ? (
            <div className="notice">
              {t('invest.manualHint')}
            </div>
          ) : null}

          {payment.address ? (
            <div style={{ textAlign: 'center', margin: '0 0 1rem' }}>
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(payment.address)}`}
                alt={ar ? 'رمز QR لعنوان الدفع' : 'QR code for the deposit address'}
                width={220}
                height={220}
                style={{ borderRadius: '12px', background: '#fff', padding: '8px' }}
              />
            </div>
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

          {payment.payment_mode === 'provider' ? (
            <div className="notice" style={{ textAlign: 'center' }}>
              <Loader2 className="spin" size={20} style={{ marginBottom: '.35rem' }} />
              <div><b>{t('invest.checkingPayment')}</b></div>
              <span className="small">{t('invest.checkingBody')}</span>
            </div>
          ) : null}

          {payment.payment_mode === 'manual' ? (
            <p className="small muted">{t('invest.awaitingAdmin')}</p>
          ) : null}

          {payment.payment_mode !== 'manual' && payment.payment_mode !== 'provider' ? (
            <button className="btn success lg block" style={{ marginTop: '1rem' }} disabled={busy} onClick={confirmPayment}>
              {busy ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />} {busy ? t('invest.confirming') : t('invest.completedPayment')}
            </button>
          ) : null}

          <button className="btn ghost" style={{ marginTop: '.5rem' }} onClick={() => { setPhase('form'); setPayment(null) }}>
            {t('invest.newOrder')}
          </button>
        </div>
      ) : null}
    </div>
  )
}