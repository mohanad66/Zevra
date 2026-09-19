import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { useI18n } from '../i18n'
import { fmtCrypto } from '../components/Format'
import { Copy, Check, Users, Star } from 'lucide-react'

export default function Referrals() {
  const [data, setData] = useState(null)
  const [copied, setCopied] = useState(false)
  const { apiError } = useAuth()
  const { toast } = useToast()
  const { t } = useI18n()

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
    { level: 1, label: t('rf.level1'), earned: data.level1_earned, count: data.level1_count, desc: t('rf.desc1') },
    { level: 2, label: t('rf.level2'), earned: data.level2_earned, count: data.level2_count, desc: t('rf.desc2') },
    { level: 3, label: t('rf.level3'), earned: data.level3_earned, count: data.level3_count, desc: t('rf.desc3') },
  ]

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>{t('rf.title')}</h2>
          <p>{t('rf.subtitle')}</p>
        </div>
      </div>

      <div className="invite-banner">
        <div>
          <strong>{t('rf.share')}</strong>
          <span className="code">{data.invite_code}</span>
        </div>
        <button className="btn primary" onClick={copy}>
          {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? t('common.copied') : t('common.copy')}
        </button>
        <p className="small muted">
          {t('rf.inviteFriends')} <b>{import.meta.env.VITE_APP_URL || window.location.origin}/register?invite={data.invite_code}</b>
        </p>
      </div>

      <div className="totals-grid three">
        <div className="tcard">
          <div className="tcard-icon"><Users /></div>
          <span className="tlabel">{t('rf.direct')}</span>
          <span className="tvalue">{data.direct_invites}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Star /></div>
          <span className="tlabel">{t('rf.totalEarned')}</span>
          <span className="tvalue">{fmtCrypto(data.total_earned)}</span>
        </div>
        <div className="tcard">
          <div className="tcard-icon"><Users /></div>
          <span className="tlabel">{t('rf.totalReferrals')}</span>
          <span className="tvalue">{data.total_referrals}</span>
        </div>
      </div>

      <div className="levels">
        {levels.map((l) => (
          <div className="level-card" key={l.level}>
            <span className="level-badge">L{l.level}</span>
            <div>
              <strong>{l.label}</strong>
              <span className="muted small">{l.desc}</span>
              <span className="muted small">{l.count} {t('rf.referrals')}</span>
            </div>
            <b>{fmtCrypto(l.earned)}</b>
          </div>
        ))}
      </div>

      <section className="section">
        <h3>{t('rf.history')}</h3>
        {data.awards.length === 0 ? (
          <p className="muted">
            {t('rf.noAwards')}
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t('rf.colLevel')}</th><th>{t('rf.colPct')}</th><th>{t('wd.amountLabel')}</th><th>{t('rf.colFrom')}</th><th>{t('rf.colDate')}</th></tr></thead>
              <tbody>
                {data.awards.map((a) => (
                  <tr key={a.id}>
                    <td>{t('rf.colLevel')} {a.level}</td>
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