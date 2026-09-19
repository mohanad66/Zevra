import { LegalShell } from '../components/LegalShell'
import { useI18n } from '../i18n'

export default function KycPolicy() {
  const { t } = useI18n()
  const sections = [1, 2, 4, 5, 6, 7, 8, 9].map((i) => ({
    head: t(`legal.kyc.${i}`),
    body: t(`legal.kyc.${i}b`),
  }))

  return (
    <LegalShell title={t('legal.kyc.title')} updated="September 11, 2026">
      {sections.map((x) => (
        <div key={x.head}>
          <h2>{x.head}</h2>
          <p>{x.body}</p>
        </div>
      ))}
      <div>
        <h2>{t('legal.kyc.3')}</h2>
        <ul>
          {t('legal.kyc.3list').split('\n').map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>
    </LegalShell>
  )
}