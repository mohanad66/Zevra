import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { client } from '../api/client'
import { TrendingUp, Wallet, Users, ShieldCheck, LineChart, Smartphone } from 'lucide-react'

export default function Landing() {
  const [market, setMarket] = useState([])

  useEffect(() => {
    client.get('/market/').then((res) => setMarket(res.data.data?.slice(0, 5) ?? [])).catch(() => {})
  }, [])

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="brand">
          <img src="/logo.png" alt="Zevra" className="brand-mark" />
          <span className="brand-name">zevra</span>
        </div>
        <div className="landing-cta">
          <Link to="/login" className="btn ghost">Log in</Link>
          <Link to="/register" className="btn primary">Get started</Link>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h1>Invest in the coins you trust.<br /><span>Watch your rewards grow.</span></h1>
          <p>
            Zevra lets you invest in carefully selected stablecoins, track live market prices,
            and grow your balance through three levels of referral rewards —
            all in one secure mobile-friendly app.
          </p>
          <div className="hero-buttons">
            <Link to="/register" className="btn primary lg">Create free account</Link>
            <Link to="/market" className="btn ghost lg">See the market</Link>
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
        <div className="feature">
          <TrendingUp />
          <h3>Invest in stablecoins</h3>
          <p>
            Pay instantly from your crypto wallet into coins the administration adds and approves.
            Your investment is credited straight to your investment balance.
          </p>
        </div>
        <div className="feature">
          <Users />
          <h3>3-level referral awards</h3>
          <p>
            Invite friends and earn a percentage of their investments — for your direct invites,
            their invites, and the next level. Awards land in your withdrawable balance.
          </p>
        </div>
        <div className="feature">
          <Wallet />
          <h3>Withdrawable balance</h3>
          <p>
            Referral awards and admin payouts are separate from your invested balance.
            Withdraw them to your own crypto account whenever you wish.
          </p>
        </div>
        <div className="feature">
          <LineChart />
          <h3>Live market monitor</h3>
          <p>Track the current price of every supported coin with 24h change, refreshed live.</p>
        </div>
        <div className="feature">
          <ShieldCheck />
          <h3>Verified & protected</h3>
          <p>KYC verification for every investor, admin-controlled payout timing, and fee transparency.</p>
        </div>
        <div className="feature">
          <Smartphone />
          <h3>Works on any device</h3>
          <p>Install Zevra on your phone like a native app — Android and iOS supported.</p>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="brand">
          <img src="/logo.png" alt="Zevra" className="brand-mark" />
          <span className="brand-name">zevra</span>
        </div>
        <nav>
          <Link to="/terms">Terms of Service</Link>
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/kyc-policy">AML / KYC Policy</Link>
        </nav>
        <p>© {new Date().getFullYear()} Zevra. Not licensed as financial advice. Trading involves risk.</p>
      </footer>
    </div>
  )
}