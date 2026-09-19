"""Automatic gateway reconciliation poller.

PayRam pushes webhooks for payments and payouts, but polling is kept as a
reliable fallback (missed webhooks, retry exhaustion, final confirmation of
``processed``). This module runs ``reconcile_gateway()`` on a timer inside the
app process whenever ``payment_mode == "provider"`` — no external cron required.

Controls (env vars):
    MIYARTRADING_DISABLE_POLLER=1  - never start the poller (e.g. in a scheduler setup)
    MIYARTRADING_POLL_INTERVAL=30  - seconds between polls (default 60, min 10)
"""
import os
import threading
import time

_poller_thread = None
_poller_stop = threading.Event()


def _say(message):
    print(f"[poller] {message}", flush=True)


def _run():
    if os.environ.get("MIYARTRADING_DISABLE_POLLER") == "1":
        _say("disabled (MIYARTRADING_DISABLE_POLLER=1)")
        return
    try:
        interval = max(10, int(os.environ.get("MIYARTRADING_POLL_INTERVAL", "60")))
    except ValueError:
        interval = 60
    _say(f"started (every {interval}s)")
    time.sleep(3)
    while not _poller_stop.wait(interval):
        try:
            from api.services import reconcile_gateway

            paid, transfers = reconcile_gateway()
            if paid or transfers:
                _say(
                    f"finalized {paid} payment(s), {transfers} withdrawal/payout(s)"
                )
        except Exception as exc:  # noqa: BLE001
            _say(f"poll error: {exc}")
            class_name = type(exc).__name__
            if "OperationalError" in class_name or "ProgrammingError" in class_name:
                _say("database not ready; poller stopped")
                return
    _say("stopped")


def start_poller():
    """Start the background poller thread once (idempotent)."""
    global _poller_thread
    if _poller_thread is not None and _poller_thread.is_alive():
        return
    _poller_stop.clear()
    _poller_thread = threading.Thread(
        target=_run, name="gateway-poller", daemon=True
    )
    _poller_thread.start()


def stop_poller():
    _poller_stop.set()