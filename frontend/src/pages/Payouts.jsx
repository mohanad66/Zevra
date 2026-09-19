import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '../api/client'
import { useI18n } from '../i18n'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { Trophy } from 'lucide-react'

export default function Payouts() {
  const [payouts, setPayouts] = useState([])
  const [accounts, setAccounts] = useState([])
  const { t } = useI18n()

  useEffect(() => {
    client.get('/payouts/').then((res) => setPayouts(res.data ?? []))
    client.get('/accounts/').then((res) => setAccounts(res.data ?? [])).catch(() => {})
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('po.title')}</h2>
          <p>{t('po.subtitle')}</p>
        </div>
      </div>

      <div className="notice">
        {t('po.notice')}
      </div>

      {accounts.length === 0 && (
        <div className="notice warn">
          {t('po.noAccounts')} <Link to="/profile">{t('po.addAccount')} →</Link>
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