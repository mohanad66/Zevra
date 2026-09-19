import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const SITE = 'Miyar Trading'
const DEFAULT_DESC =
  'Miyar Trading is a secure platform to invest in stablecoins, track live crypto market prices, and earn three-level referral rewards — on web, Android and iOS.'

const ROUTES = {
  '/': { title: `${SITE} — Invest & Trade Stablecoins`, desc: DEFAULT_DESC, private: false },
  '/login': { title: `Log in — ${SITE}`, desc: `Log in to your ${SITE} account.`, private: false },
  '/register': {
    title: `Create an account — ${SITE}`,
    desc: `Create a ${SITE} account to invest in stablecoins and earn referral rewards.`,
    private: false,
  },
  '/terms': { title: `Terms of Service — ${SITE}`, desc: `${SITE} Terms of Service.`, private: false },
  '/privacy': { title: `Privacy Policy — ${SITE}`, desc: `${SITE} Privacy Policy.`, private: false },
  '/kyc-policy': {
    title: `KYC & AML Policy — ${SITE}`,
    desc: `${SITE} identity verification (KYC) and anti-money-laundering policy.`,
    private: false,
  },
}

const DEFAULT_META = {
  title: `${SITE} — Invest & Trade Stablecoins`,
  desc: DEFAULT_DESC,
  private: true,
}

function setMeta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setCanonical(href) {
  let el = document.head.querySelector('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', 'canonical')
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

export default function Seo() {
  const { pathname } = useLocation()

  useEffect(() => {
    const meta = ROUTES[pathname] || DEFAULT_META
    const robots = meta.private ? 'noindex, nofollow' : 'index, follow'

    document.title = meta.title
    setMeta('name', 'description', meta.desc)
    setMeta('name', 'robots', robots)
    setMeta('property', 'og:title', meta.title)
    setMeta('property', 'og:description', meta.desc)
    setMeta('name', 'twitter:title', meta.title)
    setMeta('name', 'twitter:description', meta.desc)

    const origin = window.location.origin
    setCanonical(`${origin}${pathname}`)
    if (!meta.private) setMeta('property', 'og:url', `${origin}${pathname}`)
  }, [pathname])

  return null
}
