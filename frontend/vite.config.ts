import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // BACKEND_PORT is read from frontend/.env (see frontend/.env.example) so
  // the dev-server proxy always points at wherever the backend is actually
  // listening -- kept in sync by scripts/set_port.sh.
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = env.BACKEND_PORT || '8585'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
      },
    },
    build: {
      outDir: 'dist',
    },
  }
})
