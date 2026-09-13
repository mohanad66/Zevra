import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { fmt } from '../components/Format'
import { TrendingUp, ExternalLink, CheckCircle2, Clipboard, Loader2 } from 'lucide-react'

export default function Invest() {
  const { apiError } = useAuth()
  const { toast } = useToast()
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
    navigator.clipboard.writeText(text).then(() => toast('Copied', 'success')).catch(() => {})
  }

  if (!coin) return <div className="page"><p className="muted">No coins available yet.</p></div>

  if (phase === 'confirmed') {
    return (
      <div className="page">
        <div className="page-head"><div><h2>Invest</h2></div></div>
        <div className="card form" style={{ textAlign: 'center', padding: '2rem' }}>
          <CheckCircle2 size={48} color="var(--accent)" />
          <h3 style={{ margin: '1rem 0 .5rem' }}>Investment confirmed</h3>
          <p className="muted">Your balance has been updated. You can now see it in your dashboard.</p>
          <Link to="/dashboard" className="btn primary" style={{ marginTop: '1rem' }}>Open dashboard</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Invest</h2>
          <p>Pay with your crypto wallet — the platform confirms your investment after payment is received.</p>
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
            <span><i>Selected coin</i><b>{coin.name} ({coin.symbol})</b></span>
            <span><i>Price</i><b>${fmt(coin.current_price, 8)}</b></span>
            <span><i>Minimum</i><b>{fmt(coin.min_invest)} {coin.symbol}</b></span>
          </div>

          <label>
            Amount to invest
            <input
              type="number"
              min={parseFloat(coin.min_invest) || 0}
              step="any"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={`Min ${coin.min_invest} ${coin.symbol}`}
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
            Pay from your crypto account
            <input
              value={sourceAddress}
              onChange={(e) => setSourceAddress(e.target.value)}
              placeholder="Your wallet address (TRC20 / ERC20 / …)"
              required
            />
          </label>
          {accounts.length > 0 && (
            <div className="saved-accounts">
              <span className="muted small">Saved accounts</span>
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
            You will be shown a deposit address or taken to a payment gateway to complete the transaction.
          </p>

          <button className="btn primary lg block" disabled={busy}>
            <TrendingUp size={18} /> {busy ? 'Creating order…' : `Pay ${amount || '0'} ${coin.symbol}`}
          </button>
        </form>
      ) : phase === 'checkout' ? (
        <div className="card form checkout-box">
          <h3>Complete your payment</h3>
          <p className="small muted">Send exactly the amount shown below to the deposit address. Your investment will be confirmed automatically once payment is received.</p>

          <div className="checkout-amount">
            <span className="checkout-amt-value">{fmt(payment.pay_amount ?? payment.amount)}</span>
            <span className="checkout-amt-symbol">{payment.pay_currency || payment.coin_symbol}</span>
          </div>

          {payment.payment_mode === 'manual' ? (
            <div className="notice">
              This is a manual deposit mode. Send crypto to the address below and wait for the admin to confirm your investment.
            </div>
          ) : null}

          {payment.checkout_url ? (
            <a className="btn primary lg block" href={payment.checkout_url} target="_blank" rel="noreferrer" style={{ marginBottom: '1rem', textAlign: 'center' }}>
              <ExternalLink size={18} /> Open payment gateway
            </a>
          ) : null}

          {payment.address ? (
            <label className="checkout-address-label">
              Deposit address <span className="pill pill-light">{payment.chain}</span>
              <div className="checkout-addr">
                <code className="tx" style={{ fontSize: '13px', lineHeight: '2' }}>{payment.address}</code>
                <button type="button" className="icon-btn" title="Copy address" onClick={() => copy(payment.address)}><Clipboard size={16} /></button>
              </div>
            </label>
          ) : null}

          {payment.payment_mode === 'manual' ? (
            <p className="small muted">Awaiting admin confirmation.</p>
          ) : (
            <button className="btn success lg block" style={{ marginTop: '1rem' }} disabled={busy} onClick={confirmPayment}>
              {busy ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />} {busy ? 'Confirming…' : 'I have completed the payment'}
            </button>
          )}

          <button className="btn ghost" style={{ marginTop: '.5rem' }} onClick={() => { setPhase('form'); setPayment(null) }}>
            Start a new order
          </button>
        </div>
      ) : null}
    </div>
  )
}