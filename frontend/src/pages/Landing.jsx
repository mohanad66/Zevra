import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { useI18n } from '../i18n'
import { TrendingUp, Wallet, Users, ShieldCheck, LineChart, Smartphone, Globe } from 'lucide-react'

export default function Landing() {
  const [market, setMarket] = useState([])
  const { t, lang, changeLang } = useI18n()

  useEffect(() => {
    client.get('/market/').then((res) => setMarket(res.data.data?.slice(0, 5) ?? [])).catch(() => {})
  }, [])

  const features = [
    { icon: TrendingUp, title: t('land.f1t'), desc: t('land.f1d') },
    { icon: Users, title: t('land.f2t'), desc: t('land.f2d') },
    { icon: Wallet, title: t('land.f3t'), desc: t('land.f3d') },
    { icon: LineChart, title: t('land.f4t'), desc: t('land.f4d') },
    { icon: ShieldCheck, title: t('land.f5t'), desc: t('land.f5d') },
    { icon: Smartphone, title: t('land.f6t'), desc: t('land.f6d') },
  ]

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="brand">
          <img src="/logo.png" alt="Miyar Trading" className="brand-mark" />
          <span className="brand-name">Miyar Trading</span>
        </div>
        <div className="landing-cta">
          <button className="icon-btn lang-btn" title={t('nav.language')} onClick={() => changeLang(lang === 'ar' ? 'en' : 'ar')}>
            <Globe size={18} />
            <span className="lang-label">{lang === 'ar' ? 'EN' : 'عربي'}</span>
          </button>
          <Link to="/login" className="btn ghost">{t('land.login')}</Link>
          <Link to="/register" className="btn primary">{t('land.ctaJoin')}</Link>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h1>{t('land.heroH1a')}<br /><span>{t('land.heroH1b')}</span></h1>
          <p>{t('land.heroP')}</p>
          <div className="hero-buttons">
            <Link to="/register" className="btn primary lg">{t('land.create')}</Link>
            <Link to="/market" className="btn ghost lg">{t('land.seeMarket')}</Link>
          </div>
        </div>
        <div className="hero-cards">
          {market.map((m) => (
            <div className="mkt-mini" key={m.coin.symbol}>
              <span className="mkt-symbol">{m.coin.symbol}</span>
              <span className="mkt-price">${parseFloat(m.price).toLocaleString()}</span>
              <span className={parseFloat(m.change_24h) >= 0 ? 'pos' : 'neg'}>
                {parseFloat(m.change_24h).toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="features">
        {features.map((f) => (
          <div className="feature" key={f.title}>
            <f.icon />
            <h3>{f.title}</h3>
            <p>{f.desc}</p>
          </div>
        ))}
      </section>

      <footer className="landing-footer">
        <div className="brand">
          <img src="/logo.png" alt="Miyar Trading" className="brand-mark" />
          <span className="brand-name">Miyar Trading</span>
        </div>
        <nav>
          <Link to="/terms">{t('auth.register.terms')}</Link>
          <Link to="/privacy">{t('auth.register.privacy')}</Link>
          <Link to="/kyc-policy">AML / KYC Policy</Link>
        </nav>
        <p>{t('land.disclaimer', { year: new Date().getFullYear() })}</p>
      </footer>
    </div>
  )
}