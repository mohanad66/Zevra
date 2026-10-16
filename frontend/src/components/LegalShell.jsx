import { Link } from 'react-router-dom'
import { ArrowLeft, Sun, Moon } from 'lucide-react'
import { useI18n } from '../i18n'
import { useTheme } from '../theme'

export function LegalShell({ title, updated, children }) {
  const { t } = useI18n()
  const { theme, toggleTheme } = useTheme()
  return (
    <div className="legal">
      <div className="legal-top">
        <Link to="/" className="back-link"><ArrowLeft size={16} /> {t('legal.back')}</Link>
        <button className="icon-btn" title={t('nav.theme')} onClick={toggleTheme}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
      <h1>{title}</h1>
      <p className="muted">{t('legal.lastUpdated', { date: updated })}</p>
      <div className="legal-body">{children}</div>
    </div>
  )
}
