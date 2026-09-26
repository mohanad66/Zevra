"""DRF exception handler that localises framework-level error text.

Serializer field errors and framework errors are plain English msgids with no
Arabic catalogue upstream, so they reach Arabic visitors untranslated. They are
matched by pattern (see ``api.i18n.FRAMEWORK_AR``) and rewritten here for
``X-Lang: ar`` requests.

Messages the app already translated through ``api.i18n.tr`` are not in that
table, so they pass through untouched. Only *display* strings are touched:
keys listed in MACHINE_KEYS (status codes, tokens, ids) are never rewritten.
"""

from rest_framework.views import exception_handler as drf_exception_handler

from .i18n import lang_of, translate_framework_message

# Keys whose values are machine-readable, never display text.
MACHINE_KEYS = frozenset(
    {
        "code",
        "status",
        "token",
        "access",
        "refresh",
        "id",
        "pk",
        "user_id",
        "coin_id",
        "amount",
        "currency",
        "throttle_code",
    }
)


def _translate_tree(node, key=None):
    if isinstance(node, dict):
        return {k: _translate_tree(v, k) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_translate_tree(v, key) for v in node]
    if key in MACHINE_KEYS:
        return node
    return translate_framework_message(node) or node


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    request = context.get("request") if isinstance(context, dict) else None
    if lang_of(request).startswith("ar"):
        response.data = _translate_tree(response.data)
    return response
