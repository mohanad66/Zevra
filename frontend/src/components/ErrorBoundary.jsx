import { Component } from 'react'
import { getStoredLang } from '../i18n'

const MESSAGES = {
  en: {
    title: 'Something went wrong',
    body: 'An unexpected error interrupted this page. Please reload to continue.',
    reload: 'Reload',
  },
  ar: {
    title: 'حدث خطأ ما',
    body: 'أوقف خطأ غير متوقّع هذه الصفحة. يرجى إعادة التحميل للمتابعة.',
    reload: 'إعادة التحميل',
  },
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) {
      console.error('Unhandled UI error:', error, info)
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children
    const msg = MESSAGES[getStoredLang() === 'ar' ? 'ar' : 'en']
    return (
      <div className="loader">
        <div style={{ textAlign: 'center', maxWidth: 360 }}>
          <h2 style={{ marginBottom: 8 }}>{msg.title}</h2>
          <p className="muted" style={{ marginBottom: 16 }}>{msg.body}</p>
          <button className="btn" onClick={() => window.location.reload()}>
            {msg.reload}
          </button>
        </div>
      </div>
    )
  }
}
