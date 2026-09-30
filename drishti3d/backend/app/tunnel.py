"""Forward visitors from the showcase's stable address to its fast one.

The stable public address is a Tailscale Funnel name (``*.ts.net``): free and
permanent, but Funnel caps bandwidth, at about 200 KB/s in one stream and
385 KB/s over four (measured 2026-09-29). A full point cloud of up to 72 MB
then takes minutes. A Cloudflare quick tunnel from the same laptop measured
2.6 MB/s, but its free address is random and changes whenever cloudflared
restarts, so it cannot be printed on a slide.

So the stable address is the one people are given, and a page visit arriving
on it is redirected to whatever quick-tunnel hostname cloudflared reports at
that moment (its metrics server's ``/quicktunnel``). Only page navigations
are redirected. A script or data request is always answered where it arrived,
because a page served over Funnel while cloudflared was down would otherwise
have its own requests sent to another origin and refused. When cloudflared is
down or has no hostname yet, nothing is redirected: the site is served over
Funnel, slower but whole.
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import config

#: How long a hostname lookup is trusted. A restarted cloudflared gets a new
#: name; visitors in that window are sent to the old one and get an error page
#: until the next lookup.
TTL_S = 30.0
_cached: tuple[float, str | None] = (float("-inf"), None)


def quick_tunnel_host() -> str | None:
    """The current quick-tunnel hostname, or None if there is none."""
    global _cached
    now = time.monotonic()
    if now - _cached[0] < TTL_S:
        return _cached[1]
    host = None
    try:
        with urllib.request.urlopen(config.QUICKTUNNEL_METRICS, timeout=1.5) as r:
            host = json.load(r).get("hostname") or None
    except (OSError, ValueError):
        host = None
    _cached = (now, host)
    return host


def redirect_target(host: str, path: str, query: str, navigation: bool) -> str | None:
    """Where to send this request, or None to serve it here."""
    if not (config.QUICKTUNNEL_METRICS and config.REDIRECT_HOSTS and navigation):
        return None
    if path.startswith("/api/"):
        return None
    if not host.split(":")[0].lower().endswith(config.REDIRECT_HOSTS):
        return None
    target = quick_tunnel_host()
    if not target:
        return None
    return f"https://{target}{path}" + (f"?{query}" if query else "")
