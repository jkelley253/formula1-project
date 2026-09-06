import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/drivers': {
        target: 'https://8bp62sfmta.execute-api.us-west-2.amazonaws.com',
        changeOrigin: true,
      },
      '/api/driver-stats': {
        target: 'https://s4uacl7c5h.execute-api.us-west-2.amazonaws.com',
        changeOrigin: true,
      },
    },
  },
})
