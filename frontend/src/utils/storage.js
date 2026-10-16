// Lightweight cookie storage for small, client-readable preferences (auth
// tokens, selected language, theme).
//
// These values are read by JavaScript — the access token goes into the
// Authorization header — so they cannot be HttpOnly. The API lives on a
// different origin, so these cookies are only ever sent to the frontend host.
// Values are URL-encoded so characters like ";" or "=" can't break the header.

const DEFAULT_DAYS = 365

function cookieAttrs(days) {
  const attrs = ['path=/', 'SameSite=Lax']
  if (typeof location !== 'undefined' && location.protocol === 'https:') {
    attrs.push('Secure')
  }
  attrs.push(`max-age=${Math.max(0, Math.floor(days * 86400))}`)
  return attrs.join('; ')
}

export function getCookie(name) {
  if (typeof document === 'undefined') return null
  const target = `${encodeURIComponent(name)}=`
  for (const part of document.cookie.split('; ')) {
    if (part.startsWith(target)) {
      return decodeURIComponent(part.slice(target.length))
    }
  }
  return null
}

export function setCookie(name, value, { days = DEFAULT_DAYS } = {}) {
  if (typeof document === 'undefined') return
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; ${cookieAttrs(days)}`
}

export function removeCookie(name) {
  if (typeof document === 'undefined') return
  document.cookie = `${encodeURIComponent(name)}=; ${cookieAttrs(0)}`
}
