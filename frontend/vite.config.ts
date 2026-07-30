import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Docker 바인드 마운트(특히 Windows 호스트)에서는 파일 변경 이벤트가
    // 컨테이너까지 전달되지 않아 HMR이 동작하지 않는다. 컨테이너로 띄울
    // 때만 폴링으로 감시한다(호스트에서 npm run dev 할 때는 불필요).
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': {
        target: 'http://web:8000',
      },
    },
  },
})
