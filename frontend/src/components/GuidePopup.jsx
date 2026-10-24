import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '../api/client'
import { useI18n } from '../i18n'
import { X, Compass, ArrowRight, Check } from 'lucide-react'

const DISMISS_KEY = 'guide_dismissed_v1'
const OPEN_ONCE_KEY = 'guide_opened_en_once'

export default function GuidePopup() {
  const { t, lang } = useI18n()
  const [steps, setSteps] = useState([])
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState(true)

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_KEY) === '1')
    client
      .get('/onboarding/')
      .then((res) => {
        const list = res.data?.steps ?? []
        setSteps(list)
        const pending = list.some((s) => !s.done)
        const alreadyOpened = localStorage.getItem(OPEN_ONCE_KEY) === '1'
        if (pending && localStorage.getItem(DISMISS_KEY) !== '1') {
          if (lang === 'en' && !alreadyOpened) {
            setOpen(true)
            try {
              localStorage.setItem(OPEN_ONCE_KEY, '1')
            } catch {
              /* ignore */
            }
            return
          }
          if (lang !== 'en') {
            setOpen(true)
          }
        }
      })
      .catch(() => {})
  }, [lang])

  const next = steps.find((s) => !s.done)

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, '1')
    setDismissed(true)
    setOpen(false)
  }

  function reopen() {
    localStorage.removeItem(DISMISS_KEY)
    setDismissed(false)
    setOpen(true)
  }

  useEffect(() => {
    if (document.getElementById('guide-anchor')) return
    const el = document.createElement('div')
    el.id = 'guide-anchor'
    document.body.appendChild(el)
    return () => el.remove()
  }, [])

  useEffect(() => {
    if (document.getElementById('guide-anchor')) return
    const el = document.createElement('div')
    el.id = 'guide-anchor'
    document.body.appendChild(el)
    return () => el.remove()
  }, [])

  const doneCount = steps.filter((s) => s.done).length

  return (
    <>
      {!open && dismissed && (
        <button className="guide-fab" title={t('guide.open')} onClick={reopen}>
          <Compass size={18} />
        </button>
      )}

      {open && (
        <div className="guide-pop" role="dialog" aria-live="polite">
          <div className="guide-head">
            <span className="guide-title"><Compass size={16} /> {t('guide.title')}</span>
            <button className="guide-close" onClick={dismiss} title={t('guide.dismiss')}>
              <X size={16} />
            </button>
          </div>

          <p className="guide-body">
            {next ? next.detail || next.title : t('guide.allDone')}
          </p>

          {next ? (
            <div className="guide-next">
              <span className="guide-step">
                {t('guide.stepOf', { current: doneCount + 1, total: steps.length })}
              </span>
              <Link to={next.href || '/dashboard'} className="btn primary sm" onClick={() => setOpen(false)}>
                {next.cta || t('guide.continue')} <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            <div className="guide-next">
              <span className="guide-step"><Check size={14} /> {t('onboarding.complete')}</span>
            </div>
          )}

          <button className="guide-skip" onClick={dismiss}>{t('guide.hide')}</button>
        </div>
      )}
    </>
  )
}
