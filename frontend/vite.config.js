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
    ...(mode.startsWith('mobile')
      ? []
      : [
          VitePWA({
            registerType: 'autoUpdate',
            includeAssets: ['favicon.png', 'icons/icon-192.png', 'icons/icon-512.png', 'logo.png'],
            manifest: {
              name: 'MYX app — Invest & Trade Stablecoins',
              short_name: 'MYX app',
              description:
                'Invest in stablecoins, track live market prices, invite friends and earn three-level referral rewards.',
              lang: 'en',
              dir: 'ltr',
              categories: ['finance', 'business', 'productivity'],
              theme_color: '#060504',
              background_color: '#060504',
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
              globPatterns: ['**/*.{js,css,html,svg,png,jpg,jpeg,ico}'],
              navigateFallbackDenylist: [/^\/api/],
              maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
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
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('recharts')) return 'vendor-charts'
            if (id.includes('lucide-react')) return 'vendor-icons'
            if (id.includes('@capacitor')) return 'vendor-capacitor'
            if (id.includes('react')) return 'vendor-react'
            return 'vendor'
          }
        },
      },
    },
  },
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