import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 開発時は /api を FastAPI(localhost:8080)へプロキシする
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
