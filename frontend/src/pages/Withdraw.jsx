import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { ArrowDownToLine } from 'lucide-react'

export default function Withdraw() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const [settings, setSettings] = useState(null)
  const [wallets, setWallets] = useState([])
  const [accounts, setAccounts] = useState([])
  const [withdrawals, setWithdrawals] = useState([])
  const [coinId, setCoinId] = useState(null)
  const [amount, setAmount] = useState('')
  const [address, setAddress] = useState('')
  const [network, setNetwork] = useState('TRC20')
  const [busy, setBusy] = useState(false)

  async function loadData() {
    const [dash, accs, wds] = await Promise.all([
      client.get('/dashboard/'),
      client.get('/accounts/'),
      client.get('/withdrawals/'),
    ])
    setSettings(dash.data.settings)
    setWallets(dash.data.wallets ?? [])
    setAccounts(accs.data ?? [])
    setWithdrawals(wds.data ?? [])
    const first = dash.data.wallets?.[0]
    if (first) {
      setCoinId(first.coin.id)
      setNetwork(first.coin.chain || 'TRC20')
    }
  }

  useEffect(() => { loadData().catch(() => {}) }, [])

  const wallet = useMemo(() => wallets.find((w) => w.coin.id === coinId), [wallets, coinId])
  const feePct = settings?.withdraw_fee_percent ?? 1

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const res = await client.post('/withdraw/', {
        coin_id: coinId,
        amount: parseFloat(amount),
        address,
        network,
      })
      toast(res.data.message, 'success')
      setAmount('')
      await loadData()
    } catch (err) {
      toast(apiError(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  const netAmount = amount && !isNaN(parseFloat(amount))
    ? parseFloat(amount) * (1 - feePct / 100)
    : 0

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Withdraw</h2>
          <p>Move your withdrawable balance (awards & payouts) to your own crypto account.</p>
        </div>
      </div>

      {settings?.kyc_required_to_withdraw && (
        <div className="notice warn">
          KYC verification is required to withdraw. <Link to="/profile">Get verified →</Link>
        </div>
      )}

      {settings?.withdraw_cooldown_hours > 0 && (
        <div className="notice">
          A {settings.withdraw_cooldown_hours}h cooldown applies between withdrawals.
        </div>
      )}

      <form className="card form" onSubmit={submit}>
        <label>
          Coin
          <select value={coinId ?? ''} onChange={(e) => {
            const c = wallets.find((w) => w.coin.id === Number(e.target.value))
            setCoinId(Number(e.target.value))
            setNetwork(c?.coin.chain || 'TRC20')
          }}>
            {wallets.map((w) => (
              <option key={w.coin.id} value={w.coin.id}>
                {w.coin.symbol} — withdrawable {fmtCrypto(w.withdrawable_balance)}
              </option>
            ))}
          </select>
        </label>

        {wallet && (
          <div className="invest-summary">
            <span><i>Withdrawable</i><b>{fmtCrypto(wallet.withdrawable_balance)} {wallet.coin.symbol}</b></span>
            <span><i>Fee</i><b>{feePct}% + network</b></span>
            <span><i>Min amount</i><b>{settings?.min_withdrawal ?? 0} {wallet.coin.symbol}</b></span>
            <span><i>You receive</i><b>{fmtCrypto(netAmount)} {wallet.coin.symbol}</b></span>
          </div>
        )}

        <label>
          Amount
          <input
            type="number"
            min="0"
            step="any"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            required
          />
        </label>
        <div className="quick-amounts">
          <button type="button" className="chip" onClick={() => setAmount(String(wallet?.withdrawable_balance ?? ''))}>
            Max ({wallet ? fmtCrypto(wallet.withdrawable_balance) : '—'})
          </button>
        </div>

        <label>
          Network
          <select value={network} onChange={(e) => setNetwork(e.target.value)}>
            {['TRC20', 'ERC20', 'BEP20', 'BEP2', 'SOL', 'TON'].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>

        <label>
          Receive to crypto account
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Your wallet address"
            required
          />
        </label>
        {accounts.length > 0 && (
          <div className="saved-accounts">
            <span className="muted small">Saved accounts</span>
            {accounts.filter((a) => !coinId || a.coin === coinId || true).map((a) => (
              <button
                key={a.id}
                type="button"
                className={`chip ${address === a.address ? 'chip-active' : ''}`}
                onClick={() => setAddress(a.address)}
              >
                {a.coin_symbol} · {a.address.slice(0, 12)}…
              </button>
            ))}
          </div>
        )}

        <button className="btn primary lg block" disabled={busy}>
          <ArrowDownToLine size={18} /> {busy ? 'Processing…' : 'Request withdrawal'}
        </button>
        <p className="small muted center">
          <Link to="/payouts">View admin payouts →</Link>
        </p>
      </form>

      {withdrawals.length > 0 && (
        <section className="section">
          <h3>Your withdrawals</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Amount</th><th>Address</th><th>Status</th><th>Date</th></tr></thead>
              <tbody>
                {withdrawals.map((w2) => (
                  <tr key={w2.id}>
                    <td>{fmtCrypto(w2.amount)} {w2.coin_symbol}</td>
                    <td><code className="tx">{w2.address.slice(0, 18)}…</code></td>
                    <td><StatusBadge status={w2.status_display} /></td>
                    <td>{new Date(w2.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}