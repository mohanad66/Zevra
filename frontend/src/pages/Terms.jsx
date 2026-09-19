import { LegalShell } from '../components/LegalShell'
import { useI18n } from '../i18n'

export default function Terms() {
  const { t } = useI18n()
  const sections = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17].map((i) => ({
    head: t(`legal.terms.${i}`),
    body: t(`legal.terms.${i}b`),
  }))

  return (
    <LegalShell title={t('legal.terms.title')} updated="September 11, 2026">
      {sections.map((x) => (
        <div key={x.head}>
          <h2>{x.head}</h2>
          <p>{x.body}</p>
        </div>
      ))}
    </LegalShell>
  )
}