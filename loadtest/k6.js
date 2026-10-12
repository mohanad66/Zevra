/*
 * k6 load test for the Miyar Trading API.
 *
 * Run it from a machine OTHER than the VPS (the generator competes for the
 * same 4GB if you run it on the server, which skews the results).
 *
 *   k6 run loadtest/k6.js
 *
 * Configure with -e / environment variables:
 *   BASE_URL      API base (default https://api.miyartrading.com/api)
 *   TEST_EMAIL    login for the authenticated scenario (optional;
 *                 omit it and only the public scenario runs)
 *   TEST_PASSWORD password for TEST_EMAIL
 *   VUS           target virtual users per scenario (default 100)
 *   RAMP          ramp-up duration (default 30s)
 *   DURATION      hold duration (default 1m)
 *
 * Example:
 *   k6 run -e VUS=300 -e DURATION=2m \
 *          -e TEST_EMAIL=load@example.com -e TEST_PASSWORD='...' \
 *          loadtest/k6.js
 *
 * No k6 installed? Use Docker instead:
 *   docker run --rm -i grafana/k6 run -e BASE_URL=https://api.miyartrading.com/api - < loadtest/k6.js
 *
 * IMPORTANT - throttling:
 *   The API rate-limits per IP (anon 120/min) and per user (6000/min), and
 *   login is scoped to 20/min. A real load test will hit 429s well before the
 *   app is saturated, so the results reflect the throttle, not capacity. For a
 *   meaningful run, temporarily raise the limits in .env and recreate the api:
 *       THROTTLE_ANON=100000/min
 *       THROTTLE_USER=1000000/min
 *       THROTTLE_AUTH=1000/min
 *       docker compose up -d --force-recreate api
 *   Revert them afterwards.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || 'https://api.miyartrading.com/api').replace(/\/+$/, '');
const EMAIL = __ENV.TEST_EMAIL || '';
const PASSWORD = __ENV.TEST_PASSWORD || '';
const VUS = Number(__ENV.VUS || 100);
const RAMP = __ENV.RAMP || '30s';
const DURATION = __ENV.DURATION || '1m';
const HALF = Math.max(1, Math.round(VUS / 2));

const jsonHeaders = { 'Content-Type': 'application/json', Accept: 'application/json' };

const stages = [
  { duration: RAMP, target: HALF },
  { duration: DURATION, target: VUS },
  { duration: '10s', target: 0 },
];

export const options = {
  scenarios: {
    public_browse: {
      executor: 'ramping-vus',
      exec: 'publicBrowse',
      startVUs: 0,
      stages,
    },
    ...(EMAIL
      ? {
          auth_browse: {
            executor: 'ramping-vus',
            exec: 'authBrowse',
            startVUs: 0,
            stages,
          },
        }
      : {}),
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<800', 'p(99)<2000'],
  },
};

export function setup() {
  if (!EMAIL) {
    return { token: null };
  }
  const res = http.post(
    `${BASE}/auth/login/`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: jsonHeaders },
  );
  check(res, { 'login succeeded': (r) => r.status === 200 });
  if (res.status !== 200) {
    console.warn(`login failed: ${res.status} ${res.body}`);
    return { token: null };
  }
  return { token: res.json('access') };
}

export function publicBrowse() {
  http.get(`${BASE}/settings/`, { headers: { Accept: 'application/json' } });
  http.get(`${BASE}/coins/`, { headers: { Accept: 'application/json' } });
  const market = http.get(`${BASE}/market/`, { headers: { Accept: 'application/json' } });
  check(market, { 'market 200': (r) => r.status === 200 });
  sleep(1 + Math.random() * 2);
}

export function authBrowse(data) {
  if (!data || !data.token) {
    return;
  }
  const headers = { Authorization: `Bearer ${data.token}`, Accept: 'application/json' };
  http.get(`${BASE}/auth/me/`, { headers });
  http.get(`${BASE}/dashboard/`, { headers });
  const notif = http.get(`${BASE}/notifications/unread-count/`, { headers });
  check(notif, { 'notifications 200': (r) => r.status === 200 });
  sleep(1 + Math.random() * 2);
}
