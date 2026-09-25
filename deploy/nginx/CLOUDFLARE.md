# ---------------------------------------------------------------------------
# Miyar Trading — Cloudflare CDN / WAF deployment
#
# Architecture (after this is installed):
#
#   Visitor -> Cloudflare edge (TLS, WAF, Bot Fight, rate limits)
#            -> origin host nginx (TLS, Cloudflare-only allow-list)
#            -> docker main nginx (SPA + /api proxy)
#            -> Django gunicorn (real client IP via middleware)
#
# Install on the server (run once):
#
#   sudo cp deploy/nginx/cloudflare-realip.conf /etc/nginx/conf.d/cloudflare.conf
#   sudo cp deploy/nginx/cloudflare.allow     /etc/nginx/conf.d/cloudflare.allow
#   sudo nginx -t && sudo systemctl reload nginx
#
# Then in the Cloudflare dashboard:
#   1. Add the zone (miyartrading.com) and proxy the A/AAAA records (orange
#      cloud) for miyartrading.com, api.miyartrading.com, payram.miyartrading.com.
#   2. SSL/TLS -> mode: Full (strict). The origin keeps its certbot cert.
#   3. Security -> WAF: enable the managed ruleset. Consider Bot Fight Mode and
#      a rate-limiting rule on /api/auth/* and /api/withdraw/*.
#
# Notes:
#   - real_ip only trusts connections arriving from the Cloudflare ranges, so
#     CF-Connecting-IP cannot be spoofed by a direct visitor.
#   - cloudflare.allow refuses everything except Cloudflare at the origin
#     listeners; Let's Encrypt HTTP-01 renewal still works because it arrives
#     via Cloudflare (use DNS-01 if your provider does not proxy the
#     /.well-known/acme-challenge path).
#   - Keep both files' ranges in sync; refresh from cloudflare.com/ips-v4 & -v6.
# ---------------------------------------------------------------------------