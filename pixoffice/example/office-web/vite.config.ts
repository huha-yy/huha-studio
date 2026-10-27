import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { releaseAssetsPlugin } from '../../scripts/assets/release.mjs'

const root = fileURLToPath(new URL('.', import.meta.url))
const relayUrl = process.env.PIXOFFICE_INTERNAL_API_URL

function insecureContextCryptoPolyfill() {
  const c = globalThis.crypto
  if (!c || typeof c.randomUUID === 'function') return
  const randomUUID = () => {
    if (typeof c.getRandomValues === 'function') {
      const b = new Uint8Array(16)
      c.getRandomValues(b)
      b[6] = (b[6] & 0x0f) | 0x40
      b[8] = (b[8] & 0x3f) | 0x80
      const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('')
      return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
      const r = (Math.random() * 16) | 0
      return (ch === 'x' ? r : (r & 0x3) | 0x8).toString(16)
    })
  }
  try { Object.defineProperty(c, 'randomUUID', { value: randomUUID, configurable: true }) }
  catch { /* 无法定义时静默跳过 */ }
}

export default defineConfig({
  root,
  envDir: path.resolve(root, '../..'),
  publicDir: path.resolve(root, '../../public'),
  plugins: [react(), releaseAssetsPlugin(), {
    // 局域网 HTTP 访问时浏览器视为不安全上下文,crypto.randomUUID 不可用,注入 polyfill
    name: 'crypto-randomuuid-polyfill',
    transformIndexHtml(html: string) {
      return html.replace('<head>', `<head><script>(${insecureContextCryptoPolyfill.toString()})()</script>`)
    },
  }, {
    name: 'character-candidate-preview',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (/^\/\.character-preview\/[a-f0-9]{64}\/[a-zA-Z0-9_./-]+(?:\?.*)?$/.test(req.url ?? '') && !req.url!.includes('..')) {
          req.url = `/@fs${path.resolve(root, '../..')}${req.url}`
        }
        next()
      })
    },
  }],
  resolve: { dedupe: ['pixi.js', 'react', 'react-dom'] },
  server: {
    fs: { allow: [path.resolve(root, '../..')] },
    proxy: relayUrl ? {
      '/api/pixoffice': { target: relayUrl },
      '/pixoffice-config.js': { target: relayUrl },
    } : undefined,
  },
  build: {
    outDir: path.resolve(root, '../../dist'), emptyOutDir: true,
    rolldownOptions: {
      input: {
        website: path.resolve(root, 'index.html'),
        office: path.resolve(root, 'office/index.html'),
        minimal: path.resolve(root, 'minimal/index.html'),
        classroom: path.resolve(root, 'classroom/index.html'),
        farm: path.resolve(root, 'farm/index.html'),
      },
    },
  },
})
