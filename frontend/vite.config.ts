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

  // Vercel 빌드 시: process.env.VITE_API_URL이 자동으로 import.meta.env.VITE_API_URL로 주입됨
  // 로컬 개발 시: .env 파일의 VITE_API_URL 또는 proxy 사용

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    // Vercel에서 VITE_* 환경변수를 자동으로 import.meta.env에 주입하도록 envPrefix 설정
    envPrefix: 'VITE_',
    // 로컬 개발용 환경변수 디렉토리 (루트의 .env 파일 사용)
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
  }
})
