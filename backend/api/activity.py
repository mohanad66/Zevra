"""User presence and action tracking.

The SPA authenticates with JWT, which DRF validates per-view — so a plain Django
middleware never sees the authenticated user. Instead we wrap SimpleJWT's
authentication class (``TrackedJWTAuthentication``) to record presence and
state-changing actions once a token is validated, and we record logins directly
in ``LoginView``.

Writes are best-effort and must never break a request, so everything is wrapped
in broad exception handling.
"""
import re

from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication

# How long a presence update is trusted before we touch the DB again. Keeps a
# busy client (polling) from writing on every single request.
PRESENCE_THROTTLE_SECONDS = 30
ONLINE_WINDOW_SECONDS = 300

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_ACTION_RULES = [
    (re.compile(r"/auth/login"), "login"),
    (re.compile(r"/auth/register"), "register"),
    (re.compile(r"/auth/refresh"), "refresh session"),
    (re.compile(r"/auth/change-password"), "change password"),
    (re.compile(r"/invest.*confirm"), "confirm investment"),
    (re.compile(r"/invest"), "invest"),
    (re.compile(r"/withdraw"), "withdraw"),
    (re.compile(r"/payout.*claim"), "claim payout"),
    (re.compile(r"/kyc"), "kyc"),
    (re.compile(r"/referr"), "referrals"),
    (re.compile(r"/profile|/me\b"), "profile"),
    (re.compile(r"/wallet"), "wallet"),
    (re.compile(r"/notifications"), "notifications"),
    (re.compile(r"/support|/ticket"), "support"),
]


def describe_action(method, path):
    """Human-friendly label for a request, e.g. 'invest' or 'POST /api/x'."""
    p = (path or "").lower()
    for rx, label in _ACTION_RULES:
        if rx.search(p):
            return label
    return f"{method} {path}".strip()


def _client_ip(request):
    meta = getattr(request, "META", {}) or {}
    return meta.get("HTTP_X_REAL_IP") or meta.get("REMOTE_ADDR") or None


def _user_agent(request):
    meta = getattr(request, "META", {}) or {}
    return (meta.get("HTTP_USER_AGENT") or "")[:300]


def touch_presence(user, request, action=None, force=False):
    """Update the user's last-seen / current-location fields (throttled)."""
    try:
        path = getattr(request, "path", "") or ""
        action = action or describe_action(getattr(request, "method", ""), path)
        key = f"presence:seen:{user.pk}"
        if not force and cache.get(key):
            return
        from api.models import User

        User.objects.filter(pk=user.pk).update(
            last_seen=timezone.now(),
            last_path=path[:200],
            last_action=action[:120],
            last_ip=_client_ip(request),
        )
        cache.set(key, 1, PRESENCE_THROTTLE_SECONDS)
    except Exception:  # noqa: BLE001 - tracking must never break a request
        pass


def log_action(user, request, action=None, status_code=None):
    """Append an entry to the activity feed."""
    try:
        from api.models import ActivityLog

        path = getattr(request, "path", "") or ""
        method = (getattr(request, "method", "") or "").upper()
        ActivityLog.objects.create(
            user=user,
            action=(action or describe_action(method, path))[:120],
            method=method[:10],
            path=path[:255],
            status_code=status_code,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except Exception:  # noqa: BLE001 - tracking must never break a request
        pass


def track_request(user, request):
    """Record presence for any authenticated request, and log mutations."""
    path = getattr(request, "path", "") or ""
    method = (getattr(request, "method", "") or "").upper()
    is_mutation = method in MUTATION_METHODS
    touch_presence(user, request, force=is_mutation)
    if is_mutation:
        log_action(user, request)


class TrackedJWTAuthentication(JWTAuthentication):
    """JWTAuthentication that records presence/activity for the token's user."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _token = result
            track_request(user, request)
        return result
