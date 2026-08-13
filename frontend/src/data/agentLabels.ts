import type { BadgeTone } from '../components';
import type { Agent } from '../api/agents';

/**
 * 에이전트 상태를 **한 곳에서만** 말한다.
 *
 * 목록과 편집 화면이 같은 표를 각자 들고 있었다. 지금은 글자가 같지만 그건
 * 우연이다 — 이 저장소는 이미 커넥터 상태에서 한쪽만 고쳐져 두 화면이 다른
 * 말을 하는 것을 겪었다(2026-08-13).
 */
export const AGENT_STATUS: Record<Agent['status'], { tone: BadgeTone; label: string }> = {
  DRAFT: { tone: 'neutral', label: '초안' },
  ACTIVE: { tone: 'success', label: '활성' },
  DISABLED: { tone: 'warning', label: '비활성' },
};
