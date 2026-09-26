import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    // The packaged Capacitor app must NOT register a service worker: its assets
    // are bundled inside the APK and updates ship through the Play Store, so a
    // SW cache can only pin the visitor to a stale build. Keep it for the
    // browser build, where it makes the site installable.
    ...(mode === 'mobile'
      ? []
      : [
          VitePWA({
            registerType: 'autoUpdate',
            includeAssets: ['favicon.svg', 'icons.svg'],
            manifest: {
              name: 'Miyar Trading — Invest & Trade Stablecoins',
              short_name: 'Miyar Trading',
              description:
                'Invest in stablecoins, track live market prices, invite friends and earn three-level referral rewards.',
              lang: 'en',
              dir: 'ltr',
              categories: ['finance', 'business', 'productivity'],
              theme_color: '#0b0f1a',
              background_color: '#0b0f1a',
              display: 'standalone',
              orientation: 'portrait',
              start_url: '/',
              icons: [
                {
                  src: '/icons/icon-192.png',
                  sizes: '192x192',
                  type: 'image/png',
                },
                {
                  src: '/icons/icon-512.png',
                  sizes: '512x512',
                  type: 'image/png',
                },
              ],
            },
            workbox: {
              globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
              navigateFallbackDenylist: [/^\/api/],
              runtimeCaching: [
                {
                  urlPattern: /^https:\/\/api\.coingecko\.com\/.*/i,
                  handler: 'NetworkFirst',
                  options: {
                    cacheName: 'coingecko-cache',
                    expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 },
                    cacheableResponse: { statuses: [0, 200] },
                  },
                },
              ],
            },
          }),
        ]),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
}))