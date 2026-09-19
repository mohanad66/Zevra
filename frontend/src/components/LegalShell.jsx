import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useI18n } from '../i18n'

export function LegalShell({ title, updated, children }) {
  const { t } = useI18n()
  return (
    <div className="legal">
      <Link to="/" className="back-link"><ArrowLeft size={16} /> {t('legal.back')}</Link>
      <h1>{title}</h1>
      <p className="muted">{t('legal.lastUpdated', { date: updated })}</p>
      <div className="legal-body">{children}</div>
    </div>
  )
}