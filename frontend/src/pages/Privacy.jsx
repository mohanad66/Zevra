import { LegalShell } from '../components/LegalShell'
import { useI18n } from '../i18n'

function ListItem({ lines }) {
  return (
    <ul>
      {lines.map((l, i) => <li key={i}>{l}</li>)}
    </ul>
  )
}

export default function Privacy() {
  const { t } = useI18n()
  const sections = [1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14].map((i) => ({
    head: t(`legal.privacy.${i}`),
    body: t(`legal.privacy.${i}b`),
  }))

  return (
    <LegalShell title={t('legal.privacy.title')} updated="September 11, 2026">
      <div>
        <h2>{t('legal.privacy.1')}</h2>
        <p>{t('legal.privacy.1b')}</p>
      </div>
      <div>
        <h2>{t('legal.privacy.2')}</h2>
        <ListItem lines={t('legal.privacy.2list').split('\n')} />
      </div>
      <div>
        <h2>{t('legal.privacy.3')}</h2>
        <p>{t('legal.privacy.3b')}</p>
        <ListItem lines={t('legal.privacy.3list').split('\n')} />
      </div>
      {sections.map((x) => (
        <div key={x.head}>
          <h2>{x.head}</h2>
          <p>{x.body}</p>
        </div>
      ))}
    </LegalShell>
  )
}