import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 이 파일만 Node에서 실행되므로 process가 존재한다. @types/node를 추가하면
// 팀원 전원이 재설치하고 프론트 이미지도 다시 빌드해야 해서, 필요한 최소한만 선언한다.
declare const process: { env: Record<string, string | undefined> }

export default defineConfig({
  plugins: [react()],
  server: {
    // Caddy가 app.halil-ai.site로 온 요청을 이 서버로 넘긴다. Vite는 모르는
    // Host 헤더를 기본으로 거절하므로 여기 적어 두지 않으면 AWS에서만 막힌다.
    allowedHosts: ['app.halil-ai.site'],
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
