"""Trusted-proxy middleware.

The deployment (Cloudflare -> host nginx -> docker nginx -> gunicorn) sets
X-Forwarded-For with the real visitor IP. gunicorn/django normally sees the
immediate peer (a docker gateway) as REMOTE_ADDR, so DRF rate limits and
request logs would all key on the proxy address. This middleware rewrites
REMOTE_ADDR from the left-most X-Forwarded-For entry, but only when the direct
peer is a private/proxy address, so a public client cannot spoof the header.
"""

import ipaddress

PRIVATE_NETS = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "100.64.0.0/10",
]


def _is_private(ip):
    try:
        return any(ipaddress.ip_address(ip) in ipaddress.ip_network(net) for net in PRIVATE_NETS)
    except ValueError:
        return False


class TrustedProxyRealIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        meta = request.META
        peer = meta.get("REMOTE_ADDR", "")
        forwarded = (meta.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if forwarded and _is_private(peer):
            # X-Forwarded-For: client, proxy1, proxy2 — client is first.
            client = forwarded.split(",")[0].strip()
            if _is_private(client):
                client = peer
            meta["REMOTE_ADDR"] = client
            meta["HTTP_X_REAL_IP"] = client
        return self.get_response(request)


class LanguageMiddleware:
    """Activate the response language from the X-Lang header (?lang= also works).

    The SPA sends X-Lang on every request, but Django's own LocaleMiddleware
    negotiates from Accept-Language/session, which never matches the UI toggle.
    Without activation here Django's bundled catalogs (password validators,
    date/number formats) stay English even when the visitor picked Arabic.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.utils import translation
        from django.utils.cache import patch_vary_headers

        requested = (
            request.META.get("HTTP_X_LANG") or request.GET.get("lang") or ""
        ).strip().lower()
        code = requested.split("-")[0][:2]
        available = {c for c, _label in getattr(settings, "LANGUAGES", ())}
        if code and code in available:
            translation.activate(code)
            request.LANGUAGE_CODE = code
        else:
            translation.activate(settings.LANGUAGE_CODE)
            request.LANGUAGE_CODE = settings.LANGUAGE_CODE
        response = self.get_response(request)
        # Every message body is now language-dependent, so caches (nginx/Cloudflare)
        # must key on the language header or one visitor gets the other's text.
        patch_vary_headers(response, ["X-Lang"])
        return response