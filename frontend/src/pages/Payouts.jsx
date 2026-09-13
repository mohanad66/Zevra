import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '../api/client'
import { fmtCrypto, StatusBadge } from '../components/Format'
import { Trophy } from 'lucide-react'

export default function Payouts() {
  const [payouts, setPayouts] = useState([])
  const [accounts, setAccounts] = useState([])

  useEffect(() => {
    client.get('/payouts/').then((res) => setPayouts(res.data ?? []))
    client.get('/accounts/').then((res) => setAccounts(res.data ?? [])).catch(() => {})
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Admin payouts</h2>
          <p>Payments issued to you directly by the administration.</p>
        </div>
      </div>

      <div className="notice">
        To receive coins, keep a crypto account on file. Payouts are automatically transferred from
        the platform wallet to the account on your profile shortly after they are issued.
      </div>

      {accounts.length === 0 && (
        <div className="notice warn">
          You have no saved crypto accounts. <Link to="/profile">Add one in your profile →</Link>
        </div>
      )}

      {payouts.length === 0 ? (
        <p className="muted">No payouts issued yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Amount</th><th>Status</th><th>TX hash</th><th>Note</th><th>Date</th></tr>
            </thead>
            <tbody>
              {payouts.map((p) => (
                <tr key={p.id}>
                  <td>
                    <b>{fmtCrypto(p.amount)} {p.coin_symbol}</b>
                    {p.is_bonus && <span className="pill pill-light">{p.percent}% bonus</span>}
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