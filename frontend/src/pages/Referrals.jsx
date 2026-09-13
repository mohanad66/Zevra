import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { fmtCrypto } from '../components/Format'
import { Copy, Check, Users, Star } from 'lucide-react'

export default function Referrals() {
  const [data, setData] = useState(null)
  const [copied, setCopied] = useState(false)
  const { apiError } = useAuth()
  const { toast } = useToast()

  useEffect(() => {
    client.get('/referrals/').then((res) => setData(res.data)).catch((err) => toast(apiError(err), 'error'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!data) return null

  const copy = () => {
    navigator.clipboard?.writeText(data.invite_code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const levels = [
    { level: 1, label: 'Level 1 · Direct', earned: data.level1_earned, desc: 'People you invite' },
    { level: 2, label: 'Level 2 · Indirect', earned: data.level2_earned, desc: 'People they invite' },
    { level: 3, label: 'Level 3 · Indirect', earned: data.level3_earned, desc: 'Their referrals too' },
  ]

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Referral program</h2>
          <p>Earn a percentage of every investment made through your invite tree.</p>
        </div>
      </div>

      <div className="invite-banner">
        <div>
          <strong>Share your code</strong>
          <span className="code">{data.invite_code}</span>
        </div>
        <button className="btn primary" onClick={copy}>
          {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? 'Copied!' : 'Copy'}
        </button>
        <p className="small muted">
          Invite friends at <b>{import.meta.env.VITE_APP_URL || window.location.origin}/register?invite={data.invite_code}</b>
        </p>
      </div>

      <div className="totals-grid three">
        <div className="tcard">
          <div className="tcard-icon"><Users /></div>
          <span className="tlabel">Direct invites</span>
          <span className="tvalue">{data.direct_invites}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Star /></div>
          <span className="tlabel">Total earned</span>
          <span className="tvalue">{fmtCrypto(data.total_earned)}</span>
        </div>
      </div>

      <div className="levels">
        {levels.map((l) => (
          <div className="level-card" key={l.level}>
            <span className="level-badge">L{l.level}</span>
            <div>
              <strong>{l.label}</strong>
              <span className="muted small">{l.desc}</span>
            </div>
            <b>{fmtCrypto(l.earned)}</b>
          </div>
        ))}
      </div>

      <section className="section">
        <h3>Award history</h3>
        {data.awards.length === 0 ? (
          <p className="muted">
            No awards yet. Awards activate as soon as someone you invited makes their first investment.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Level</th><th>% </th><th>Amount</th><th>From</th><th>Date</th></tr></thead>
              <tbody>
                {data.awards.map((a) => (
                  <tr key={a.id}>
                    <td>Level {a.level}</td>
                    <td>{a.percent}%</td>
                    <td><b>+{fmtCrypto(a.amount)} {a.coin_symbol}</b></td>
                    <td>{a.investor_email}</td>
                    <td>{new Date(a.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}