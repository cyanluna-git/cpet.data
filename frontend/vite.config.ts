import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 루트 디렉토리의 .env 파일 로드 (로컬 개발용)
  const rootDir = path.resolve(__dirname, '..')
  const env = loadEnv(mode, rootDir, '')

  const frontendPort = parseInt(env.FRONTEND_PORT || '3100')
  const backendPort = parseInt(env.BACKEND_PORT || '8100')

  // Vercel 환경변수 또는 .env 파일에서 API URL 가져오기
  const apiUrl = process.env.VITE_API_URL || env.VITE_API_URL || `http://localhost:${backendPort}`

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: frontendPort,
      proxy: {
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
    },
  }
})
