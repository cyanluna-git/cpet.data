import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 현재 디렉토리에서 .env 파일 로드 (prebuild가 생성한 .env.production.local 포함)
  const env = loadEnv(mode, '.', '')

  // API URL: loadEnv()로 읽은 값 사용
  const apiUrl = env.VITE_API_URL || ''
  console.log('[vite.config] mode:', mode)
  console.log('[vite.config] VITE_API_URL:', apiUrl || '(empty - will use /api proxy)')

  const frontendPort = parseInt(env.FRONTEND_PORT || '3100')
  const backendPort = parseInt(env.BACKEND_PORT || '8100')

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
    // loadEnv()로 읽은 값을 클라이언트 코드에 주입
    // Vite의 자동 env 로딩이 작동하지 않아 define으로 명시적 주입
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
    },
  }
})
