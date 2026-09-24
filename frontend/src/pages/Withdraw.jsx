import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Html5Qrcode } from 'html5-qrcode'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { ArrowDownToLine, QrCode, Camera, X } from 'lucide-react'

const NETWORKS = [
  { id: 'TRC20', label: 'USDT · TRC20', hint: 'Tron', enabled: true },
  { id: 'POL', label: 'USDT · POL', hint: 'Polygon', enabled: true },
  { id: 'ETH20', label: 'USDT · ETH20', hint: 'Ethereum', enabled: true },
  { id: 'BEP20', label: 'USDT · BEP20', hint: 'BNB Chain', enabled: true },
]

export default function Withdraw() {
  const { apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()
  const [settings, setSettings] = useState(null)
  const [wallets, setWallets] = useState([])
  const [accounts, setAccounts] = useState([])
  const [withdrawals, setWithdrawals] = useState([])
  const [coinId, setCoinId] = useState(null)
  const [amount, setAmount] = useState('')
  const [address, setAddress] = useState('')
  const [network, setNetwork] = useState('TRC20')
  const [busy, setBusy] = useState(false)
  const [qrOpen, setQrOpen] = useState(false)
  const qrDiv = useRef(null)
  const qrScan = useRef(null)

  async function loadData() {
    const [dash, accs, wds] = await Promise.all([
      client.get('/dashboard/'),
      client.get('/accounts/'),
      client.get('/withdrawals/'),
    ])
    setSettings(dash.data.settings)
    const available = (dash.data.wallets ?? []).filter(
      (w) => parseFloat(w.withdrawable_balance) > 0 || parseFloat(w.invested_balance) > 0
    )
    setWallets(available)
    setAccounts(accs.data ?? [])
    setWithdrawals(wds.data ?? [])
    const first =
      available.find((w) => String(w.coin.symbol).toUpperCase() === 'USDT') || available[0]
    if (first) {
      setCoinId(first.coin.id)
      const map = { ERC20: 'ETH20', POLYGON: 'POL' }
      const chain = map[(first.coin.chain || '').toUpperCase()] || first.coin.chain
      if ({ TRC20:1, ETH20:1, POL:1, BEP20:1, BASE:1, TON:1, SOL:1 }[chain]) setNetwork(chain)
    }
  }

  useEffect(() => { loadData().catch(() => {}) }, [])

  useEffect(() => {
    if (!qrOpen) return
    let scanner = null
    ;(async () => {
      try {
        scanner = new Html5Qrcode('qr-reader-box')
        await scanner.start(
          { facingMode: 'environment' },
          { fps: 10, qrbox: { width: 220, height: 220 } },
          async (decodedText) => {
            setAddress(decodedText.trim())
            setQrOpen(false)
            toast(t('wd.qrLinked'), 'success')
          },
          () => {}
        )
        qrScan.current = scanner
      } catch (err) {
        setQrOpen(false)
        toast(apiError(err), 'error')
      }
    })()
    return () => {
      if (scanner) {
        scanner.stop().then(() => scanner.clear()).catch(() => {})
      }
      qrScan.current = null
    }
  }, [qrOpen, apiError, t, toast])

  const wallet = useMemo(() => wallets.find((w) => w.coin.id === coinId), [wallets, coinId])
  const feePct = settings?.withdraw_fee_percent ?? 1

  // Networks available for the currently selected coin. USDT gets the four
  // gateway-settled options; other coins fall back to their own chain.
  const chainLabel = useMemo(() => {
    const map = { ERC20: 'ETH20', POLYGON: 'POL', BEP20: 'BEP20', TRC20: 'TRC20', BASE: 'BASE', TON: 'TON', SOL: 'SOL' }
    return map[(wallet?.coin.chain || '').toUpperCase()]
  }, [wallet])
  const networkOptions = useMemo(() => {
    if (!wallet) return NETWORKS.filter((n) => n.enabled)
    const opts = NETWORKS.filter((n) => n.enabled)
    if (chainLabel && !opts.some((n) => n.id === chainLabel)) {
      opts.push({ id: chainLabel, label: `${wallet.coin.symbol} · ${chainLabel}`, hint: '', enabled: true })
    }
    return opts
  }, [wallet, chainLabel])

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
          <h2>{t('wd.title')}</h2>
          <p>{t('wd.subtitle')}</p>
        </div>
      </div>

      {settings?.kyc_required_to_withdraw && (
        <div className="notice warn">
          {t('wd.kycRequired')} <Link to="/profile">{t('wd.getVerified')}</Link>
        </div>
      )}

      {settings?.withdraw_cooldown_hours > 0 && (
        <div className="notice">
          {t('wd.cooldown', { hours: settings.withdraw_cooldown_hours })}
        </div>
      )}

      <form className="card form" onSubmit={submit}>
        <label>
          {t('wd.coin')}
          <select value={coinId ?? ''} onChange={(e) => {
            const c = wallets.find((w) => w.coin.id === Number(e.target.value))
            setCoinId(Number(e.target.value))
            if (c) {
              const map = { ERC20: 'ETH20', POLYGON: 'POL' }
              const chain = map[(c.coin.chain || '').toUpperCase()] || c.coin.chain
              if ({ TRC20:1, ETH20:1, POL:1, BEP20:1, BASE:1, TON:1, SOL:1 }[chain]) setNetwork(chain)
            }
          }}>
            {wallets.map((w) => (
              <option key={w.coin.id} value={w.coin.id}>
                {w.coin.symbol} — {t('wd.withdrawable')} {fmtCrypto(w.withdrawable_balance)}
              </option>
            ))}
          </select>
        </label>

        {wallet && (
          <div className="invest-summary">
            <span><i>{t('wd2.withdrawable')}</i><b>{fmtCrypto(wallet.withdrawable_balance)} {wallet.coin.symbol}</b></span>
            <span><i>{t('wd.fee')}</i><b>{feePct}% + {t('wd.network')}</b></span>
            <span><i>{t('wd.minAmount')}</i><b>{settings?.min_withdrawal ?? 0} {wallet.coin.symbol}</b></span>
            <span><i>{t('wd.youReceive')}</i><b>{fmtCrypto(netAmount)} {wallet.coin.symbol}</b></span>
          </div>
        )}

        <label>
          {t('wd.amountLabel')}
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
            {t('wd.max')} ({wallet ? fmtCrypto(wallet.withdrawable_balance) : '—'})
          </button>
        </div>

        <label>
          {t('wd.network')}
          <select value={network} onChange={(e) => setNetwork(e.target.value)}>
            {networkOptions.map((n) => (
              <option key={n.id} value={n.id}>{n.label}</option>
            ))}
          </select>
        </label>

        <label>
          {t('wd.receiveTo')}
          <div className="row2">
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder={t('wd.addressPlaceholder')}
              required
            />
            <button type="button" className="btn ghost" onClick={() => setQrOpen(true)}>
              <QrCode size={16} /> {t('wd.scanQr')}
            </button>
          </div>
        </label>
        {accounts.length > 0 && (
          <div className="saved-accounts">
            <span className="muted small">{t('wd.savedAccounts')}</span>
            {accounts.filter(() => true).map((a) => (
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
          <ArrowDownToLine size={18} /> {busy ? t('common.busy') : t('wd.request')}
        </button>
        <p className="small muted center">
          <Link to="/payouts">{t('wd.viewPayouts')}</Link>
        </p>
      </form>

      {withdrawals.length > 0 && (
        <section className="section">
          <h3>{t('wd.history')}</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('wd.amountLabel')}</th><th>{t('wd.tAddress')}</th><th>{t('common.status')}</th><th>{t('common.date')}</th></tr></thead>
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
      {qrOpen && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}
          onClick={() => setQrOpen(false)}
        >
          <div className="card form" style={{ width: '100%', maxWidth: 420, padding: '1.2rem' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
              <h3 style={{ margin: 0 }}>
                <Camera size={16} style={{ verticalAlign: '-2px', marginRight: '0.3rem' }} /> {t('wd.scanQrTitle')}
              </h3>
              <button className="btn ghost" style={{ padding: '0.25rem 0.5rem' }} onClick={() => setQrOpen(false)}>
                <X size={16} />
              </button>
            </div>
            <p className="muted small" style={{ marginBottom: '0.6rem' }}>{t('wd.scanQrHint')}</p>
            <div id="qr-reader-box" ref={qrDiv} style={{ width: '100%', aspectRatio: '1 / 1', maxHeight: 280, overflow: 'hidden', borderRadius: 10 }} />
          </div>
        </div>
      )}
    </div>
  )
}