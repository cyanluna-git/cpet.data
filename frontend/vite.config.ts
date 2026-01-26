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

  // API URL 결정:
  // 1. Vercel 빌드 시: process.env.VITE_API_URL 사용
  // 2. 로컬 .env 파일: env.VITE_API_URL 사용
  // 3. 기본값: 로컬 백엔드 (프록시 사용)
  const apiUrl = process.env.VITE_API_URL || env.VITE_API_URL || ''

  console.log('[vite.config] Building with API URL:', apiUrl || '(empty - will use /api)')

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    envDir: rootDir,
    server: {
      port: frontendPort,
      proxy: {
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    // 빌드 시 환경변수를 코드에 주입
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
    },
  }
})
