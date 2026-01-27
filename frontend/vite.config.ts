import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { existsSync, readFileSync } from 'fs'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 현재 디렉토리에서 .env 파일 로드
  const env = loadEnv(mode, '.', '')

  // 디버깅: 환경변수 및 파일 확인
  console.log('[vite.config] mode:', mode)
  console.log('[vite.config] cwd:', process.cwd())
  console.log('[vite.config] VITE_API_URL from loadEnv:', env.VITE_API_URL)

  const envFile = '.env.production.local'
  if (existsSync(envFile)) {
    console.log('[vite.config] .env.production.local exists!')
    console.log('[vite.config] content:', readFileSync(envFile, 'utf-8'))
  } else {
    console.log('[vite.config] .env.production.local NOT found')
  }

  const frontendPort = parseInt(env.FRONTEND_PORT || '3100')
  const backendPort = parseInt(env.BACKEND_PORT || '8100')

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    // envDir: 현재 디렉토리에서 .env 파일 로드
    envDir: '.',
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
