import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

export function LegalShell({ title, updated, children }) {
  return (
    <div className="legal">
      <Link to="/" className="back-link"><ArrowLeft size={16} /> Back to home</Link>
      <h1>{title}</h1>
      <p className="muted">Last updated: {updated}</p>
      <div className="legal-body">{children}</div>
    </div>
  )
}