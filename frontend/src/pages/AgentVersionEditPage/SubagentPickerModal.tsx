import { useState } from 'react';
import { Badge, Icon, Modal } from '../../components';
import type { AgentVersionSummary } from '../../api/agentVersions';
import pageStyles from './AgentVersionEditPage.module.css';
import styles from './SubagentPickerModal.module.css';

type Tab = 'personal' | 'team' | 'favorites';

const TABS: { id: Tab; label: string }[] = [
  { id: 'personal', label: '개인' },
  { id: 'team', label: '팀 공유' },
  { id: 'favorites', label: '즐겨찾기' },
];

export interface SubagentPickerModalProps {
  open: boolean;
  onClose: () => void;
  /** DRAFT — 항상 내 것이다(서버가 이미 그렇게 걸러 준다). */
  personalCandidates: AgentVersionSummary[];
  /** ACTIVE. */
  teamCandidates: AgentVersionSummary[];
  /** 상태 무관, `is_favorite`만. */
  favoriteCandidates: AgentVersionSummary[];
  /** 이미 고른 서브 에이전트의 agent_id들 — 카드에 체크 표시. */
  selectedIds: string[];
  /** 카드를 누르면 토글(추가/제거) — 실제 추가 가능 여부(설명 필수 등)
   * 판단은 호출부(AgentVersionEditPage)가 한다. */
  onToggle: (agent: AgentVersionSummary) => void;
}

/**
 * 서브 에이전트 선택 팝업 — 에이전트 목록 화면과 같은 개인/팀 공유/즐겨찾기
 * 세 탭. 카드 클릭이 곧 토글이라 별도 "추가" 버튼이 없다.
 */
export function SubagentPickerModal({
  open,
  onClose,
  personalCandidates,
  teamCandidates,
  favoriteCandidates,
  selectedIds,
  onToggle,
}: SubagentPickerModalProps) {
  const [tab, setTab] = useState<Tab>('personal');
  const candidates =
    tab === 'personal' ? personalCandidates : tab === 'team' ? teamCandidates : favoriteCandidates;

  return (
    <Modal open={open} onClose={onClose} title="서브 에이전트 선택" width={640}>
      <div className={styles.tabs} role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={[styles.tab, tab === item.id ? styles.tabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className={styles.grid}>
        {candidates.length === 0 && (
          <p className={pageStyles.help}>
            {tab === 'personal'
              ? '아직 활성화 안 한 개인 에이전트가 없습니다.'
              : tab === 'team'
                ? '팀에 공유된 에이전트가 아직 없습니다.'
                : '즐겨찾기한 에이전트가 없습니다.'}
          </p>
        )}
        {candidates.map((agent) => {
          const selected = selectedIds.includes(agent.agent_id);
          return (
            <button
              key={agent.agent_id}
              type="button"
              className={[styles.card, selected ? styles.cardSelected : ''].filter(Boolean).join(' ')}
              onClick={() => onToggle(agent)}
              aria-pressed={selected}
            >
              <div className={styles.cardTop}>
                <strong className={styles.cardName}>{agent.name}</strong>
                {selected ? (
                  <Icon name="check-circle" size={16} color="var(--color-primary)" />
                ) : agent.is_favorite ? (
                  <Icon name="star-filled" size={16} color="#facc15" />
                ) : null}
              </div>
              <p className={styles.cardDesc}>{agent.description || '(설명 없음)'}</p>
              {agent.status === 'DRAFT' && (
                <Badge tone="neutral">개인·미공유</Badge>
              )}
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
