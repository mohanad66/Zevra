import { useCallback, useEffect, useRef, useState } from 'react'
import { Mail, ShieldCheck, RefreshCw, LoaderCircle } from 'lucide-react'
import { client, apiError } from '../api/client'
import { useI18n } from '../i18n'
import { useToast } from './Toast'

const CODE_LENGTH = 6

export default function VerifyEmail({ channel = 'email', purpose = 'register', onVerified, compact }) {
  const { t } = useI18n()
  const toast = useToast()
  const [code, setCode] = useState('')
  const [masked, setMasked] = useState('')
  const [sending, setSending] = useState(false)
  const [checking, setChecking] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  const send = useCallback(
    (silent) => {
      setSending(true)
      setError('')
      client
        .post('/auth/verify/send/', { channel, purpose })
        .then((res) => {
          setMasked(res.data?.masked || '')
          setSent(true)
          setCooldown(res.data?.cooldown || 60)
          if (!silent) toast.success?.(res.data?.detail || t('verify.sent'))
          inputRef.current?.focus()
        })
        .catch((err) => {
          const msg = apiError(err)
          setError(msg)
          // A cooldown 400 still means a code is in flight, so adopt its timer
          // and destination rather than leaving the Send button clickable.
          const data = err?.response?.data
          if (data?.retry_after > 0) {
            if (data.masked) setMasked(data.masked)
            setSent(true)
            setCooldown(data.retry_after)
          }
          if (!silent) toast.error?.(msg)
        })
        .finally(() => setSending(false))
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [channel, purpose],
  )

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const id = setInterval(() => setCooldown((c) => (c <= 1 ? 0 : c - 1)), 1000)
    return () => clearInterval(id)
  }, [cooldown])

  // `register` sends a code before this component ever mounts, so ask the
  // server whether one is already in flight. Without this the UI rendered a
  // Send button that could only bounce off the 60s resend cooldown.
  useEffect(() => {
    client
      .get('/auth/verify/status/', { params: { channel, purpose } })
      .then((res) => {
        const pending = res.data?.pending
        if (pending?.retry_after > 0) {
          setMasked(pending.masked || '')
          setSent(true)
          setCooldown(pending.retry_after)
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const confirm = () => {
    if (code.length !== CODE_LENGTH) return
    setChecking(true)
    setError('')
    client
      .post('/auth/verify/confirm/', { channel, purpose, code })
      .then((res) => {
        toast.success?.(res.data?.message || t('verify.done'))
        onVerified?.(res.data?.user)
      })
      .catch((err) => {
        const msg = apiError(err)
        setError(msg)
        toast.error?.(msg)
        setCode('')
        inputRef.current?.focus()
      })
      .finally(() => setChecking(false))
  }

  const onChange = (e) => {
    const value = (e.target.value || '').replace(/\D/g, '').slice(0, CODE_LENGTH)
    setCode(value)
    setError('')
    if (value.length === CODE_LENGTH) {
      // Auto-submit as soon as the 6th digit lands.
      setChecking(true)
      setError('')
      client
        .post('/auth/verify/confirm/', { channel, purpose, code: value })
        .then((res) => {
          toast.success?.(res.data?.message || t('verify.done'))
          onVerified?.(res.data?.user)
        })
        .catch((err) => {
          const msg = apiError(err)
          setError(msg)
          toast.error?.(msg)
          setCode('')
          inputRef.current?.focus()
        })
        .finally(() => setChecking(false))
    }
  }

  return (
    <div className={compact ? 'verify-box compact' : 'verify-box'}>
      <div className="verify-head">
        <span className="verify-icon">
          <Mail size={18} />
        </span>
        <div>
          <strong>{t('verify.title')}</strong>
          <p className="muted small">{t('verify.subtitle')}</p>
        </div>
      </div>

      {!sent ? (
        <div className="verify-body">
          <p className="muted small">{t('verify.sendHint')}</p>
          <button className="btn primary" onClick={() => send(false)} disabled={sending}>
            {sending ? <LoaderCircle size={16} className="spin" /> : <Mail size={16} />}
            {t('verify.send')}
          </button>
        </div>
      ) : (
        <div className="verify-body">
          <p className="muted small">
            {t('verify.sentTo')} <b>{masked}</b>
          </p>
          <input
            ref={inputRef}
            className="otp-input"
            value={code}
            onChange={onChange}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d*"
            maxLength={CODE_LENGTH}
            aria-label={t('verify.codeLabel')}
            disabled={checking}
          />
          {error && <p className="field-error">{error}</p>}
          <div className="verify-actions">
            <button
              className="btn primary"
              onClick={confirm}
              disabled={code.length !== CODE_LENGTH || checking}
            >
              {checking ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
              {t('verify.confirm')}
            </button>
            <button
              className="btn ghost"
              onClick={() => send(true)}
              disabled={sending || cooldown > 0}
            >
              <RefreshCw size={15} />
              {cooldown > 0 ? `${t('verify.resendIn')} ${cooldown}s` : t('verify.resend')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
