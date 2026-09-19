import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { client } from '../api/client'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmt, fmtCrypto, StatusBadge } from '../components/Format'
import { ArrowLeft, TrendingUp, Wallet } from 'lucide-react'

export default function WalletDetail() {
  const { coinId } = useParams()
  const [data, setData] = useState(null)
  const { toast } = useToast()
  const { t } = useI18n()

  useEffect(() => {
    client
      .get(`/wallet/${coinId}/`)
      .then((res) => setData(res.data))
      .catch((err) => toast((err?.response?.data?.detail) || t('common.error'), 'error'))
  }, [coinId, t])

  if (!data) return null
  const w = data.wallet

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link to="/dashboard" className="back-link"><ArrowLeft size={16} /> {t('common.back')}</Link>
          <h2>{w.coin.name} <span className="coin-symbol">{w.coin.symbol} · {w.coin.chain}</span></h2>
        </div>
      </div>

      <div className="totals-grid two">
        <div className="tcard">
          <div className="tcard-icon"><TrendingUp /></div>
          <span className="tlabel">{t('wd2.invested')}</span>
          <span className="tvalue">{fmtCrypto(w.invested_balance)} {w.coin.symbol}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Wallet /></div>
          <span className="tlabel">{t('wd2.withdrawable')}</span>
          <span className="tvalue">{fmtCrypto(w.withdrawable_balance)} {w.coin.symbol}</span>
        </div>
      </div>

      <section className="section">
        <h3>{t('wd2.investments')}</h3>
        <Table
          cols={[t('wd.amountLabel'), t('common.status'), 'TX hash', t('common.date')]}
          rows={data.investments.map((i) => [`
            ${fmtCrypto(i.amount)} ${i.coin_symbol}`, <StatusBadge status={i.status_display} key={i.id} />,
            <code className="tx" key={i.id}>{i.tx_hash?.slice(0, 18) || '—'}</code>,
            new Date(i.created_at).toLocaleString()])}
          empty={data.investments.length === 0}
          emptyText={t('wd2.nothere')}
        />
      </section>

      <section className="section">
        <h3>{t('wd2.withdrawals')}</h3>
        <Table
          cols={[t('wd.amountLabel'), t('wd.tAddress'), t('wd.fee'), t('common.status'), t('common.date')]}
          rows={data.withdrawals.map((w2) => [`
            ${fmtCrypto(w2.amount)} ${w2.coin_symbol}`, <code className="tx" key={w2.id}>{w2.address?.slice(0, 14)}…</code>,
            fmt(w2.fee), <StatusBadge status={w2.status_display} key={`s${w2.id}`} />,
            new Date(w2.created_at).toLocaleString()])}
          empty={data.withdrawals.length === 0}
          emptyText={t('wd2.nothere')}
        />
      </section>

      <section className="section">
        <h3>{t('wd2.payouts')}</h3>
        <Table
          cols={[t('wd.amountLabel'), t('common.status'), 'TX hash', t('common.date')]}
          rows={data.payouts.map((p) => [`
            ${fmtCrypto(p.amount)} ${p.coin_symbol}`, <StatusBadge status={p.status_display} key={p.id} />,
            <code className="tx" key={p.id}>{p.tx_hash?.slice(0, 18) || '—'}</code>,
            new Date(p.created_at).toLocaleString()])}
          empty={data.payouts.length === 0}
          emptyText={t('wd2.nothere')}
        />
      </section>

      <section className="section">
        <h3>{t('wd2.awards')}</h3>
        <Table
          cols={[t('rf.colLevel'), t('rf.colPct'), t('wd.amountLabel'), t('rf.colFrom'), t('common.date')]}
          rows={data.awards.map((a) => [`${t('rf.colLevel')} ${a.level}`, `${a.percent}%`,
            <b key={a.id}>{fmtCrypto(a.amount)} {a.coin_symbol}</b>,
            a.investor_email, new Date(a.created_at).toLocaleString()])}
          empty={data.awards.length === 0}
          emptyText={t('wd2.nothere')}
        />
      </section>
    </div>
  )
}

function Table({ cols, rows, empty, emptyText }) {
  if (empty) return <p className="muted">{emptyText}</p>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}