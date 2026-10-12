import { LoaderCircle } from 'lucide-react'
import { useI18n } from '../i18n'

export default function Loading({ label }) {
  const { t } = useI18n()
  return (
    <div className="loader">
      <LoaderCircle size={36} className="spin" />
      <span>{label || t('common.loading')}</span>
    </div>
  )
}
