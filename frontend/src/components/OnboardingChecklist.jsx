import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, CircleDot, ChevronRight, LoaderCircle, RefreshCw, ListChecks } from 'lucide-react'
import { client } from '../api/client'
import { useI18n } from '../i18n'

const DISMISS_KEY = 'myxtrading_onboarding_dismissed'

export default function OnboardingChecklist({ autoRefreshMs = 45000 }) {
  const { t } = useI18n()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(DISMISS_KEY) === '1'
    } catch {
      return false
    }
  })

  const load = useCallback(() => {
    client
      .get('/onboarding/')
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
    if (!autoRefreshMs) return undefined
    const id = setInterval(load, autoRefreshMs)
    return () => clearInterval(id)
  }, [load, autoRefreshMs])

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(DISMISS_KEY, next ? '1' : '0')
      } catch {
        /* storage disabled */
      }
      return next
    })
  }

  if (loading && !data) {
    return (
      <div className="card onboarding">
        <div className="loader">
          <LoaderCircle size={22} className="spin" />
        </div>
      </div>
    )
  }
  if (!data) return null

  const { steps = [], percent = 0, completed = 0, total = 0, next } = data

  return (
    <section className="card onboarding" aria-label={t('onboarding.title')}>
      <button type="button" className="onboarding-head" onClick={toggle} aria-expanded={!collapsed}>
        <span className="onboarding-icon">
          <ListChecks size={18} />
        </span>
        <div className="onboarding-titles">
          <strong>{t('onboarding.title')}</strong>
          <span className="muted small">
            {t('onboarding.progress', { completed, total })}
          </span>
        </div>
        <span className="onboarding-count">
          {completed}/{total}
        </span>
        <ChevronRight size={18} className={collapsed ? 'chev' : 'chev open'} />
      </button>

      <div className="progress" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
        <span style={{ width: `${percent}%` }} />
      </div>

      {!collapsed && (
        <ol className="onboarding-steps">
          {steps.map((step) => (
            <li key={step.key} className={`ob-step ${step.done ? 'done' : ''} ${step.is_next ? 'next' : ''}`}>
              <span className="ob-mark">
                {step.done ? <Check size={14} /> : step.is_next ? <CircleDot size={12} /> : <span className="ob-dot" />}
              </span>
              <div className="ob-text">
                <b>
                  <span className="ob-idx">{t('onboarding.step', { index: step.index })}</span>
                  {step.key === 'claim_payout_mission' && (
                    <span className="ob-badge">{t('onboarding.mission')}</span>
                  )}
                  {step.title}
                </b>
                {!step.done && <p className="muted small">{step.detail}</p>}
              </div>
              {!step.done && step.key !== 'verify_email' && step.key !== 'claim_payout_mission' && (
                <Link to={step.href} className="btn primary ob-cta">
                  {step.cta || t('onboarding.start')}
                  <ChevronRight size={15} />
                </Link>
              )}
            </li>
          ))}
        </ol>
      )}

      {!collapsed && (
        <div className="onboarding-foot">
          <button type="button" className="btn ghost small" onClick={load}>
            <RefreshCw size={14} /> {t('onboarding.refresh')}
          </button>
        </div>
      )}

      {next && collapsed && (
        <Link to={next.href} className="ob-resume">
          <span>{next.title}</span>
          <ChevronRight size={16} />
        </Link>
      )}
    </section>
  )
}
