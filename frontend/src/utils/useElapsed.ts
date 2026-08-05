import { useEffect, useState } from 'react';

/**
 * `key` 가 바뀐 뒤 흐른 시간(초). `key` 가 null 이면 세지 않는다.
 *
 * 오래 걸리는 작업에서 **살아 있다는 증거**로 쓴다. 진행률이 안 움직이는 동안에도
 * 이 숫자는 1초마다 올라가므로, 사용자가 「멈춘 것」과 「오래 걸리는 것」을 구분할
 * 수 있다. 실제로 RunPod 워커 콜드 스타트로 몇 분을 기다리는 화면이 멈춘 것으로
 * 읽혔다(2026-08-05).
 */
export function useElapsed(key: string | number | null): number {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (key === null) return;
    setSeconds(0);
    const started = Date.now();
    const timer = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [key]);

  return seconds;
}

/** 「1분 12초 경과」. 분 단위가 넘어가야 분을 보여준다. */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}초 경과`;
  return `${Math.floor(seconds / 60)}분 ${seconds % 60}초 경과`;
}
