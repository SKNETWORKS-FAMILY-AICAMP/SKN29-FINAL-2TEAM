import { useState } from 'react';
import { Badge } from '../Badge/Badge';
import { Button } from '../Button/Button';
import { Checkbox } from '../Checkbox/Checkbox';
import { Icon } from '../Icon/Icon';
import { Modal } from '../Modal/Modal';
import type { BadgeTone } from '../Badge/Badge';
import type { ToolChoice } from '../../api/agents';
import type { McpServer } from '../../api/mcp';
import styles from './ToolPickerModal.module.css';

type Tab = 'builtin' | 'mcp' | 'create';

const TABS: { id: Tab; label: string }[] = [
  { id: 'builtin', label: '툴 선택' },
  { id: 'mcp', label: '커스텀 도구 선택' },
  { id: 'create', label: '툴 생성' },
];

const SERVER_STATUS: Record<McpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

export interface ToolPickerModalProps {
  open: boolean;
  onClose: () => void;
  /** MCP 도구(`mcp:` 접두사)는 빼고 넘긴다 — 이 목록은 「툴 선택」 탭 전용이다. */
  builtinTools: ToolChoice[];
  mcpServers: McpServer[];
  toolRefs: string[];
  onToggle: (ref: string) => void;
  /**
   * 카테고리 카드 헤더의 「전체 선택」 마스터 체크박스. `onToggle`을 여러 번
   * 부르지 않는다 — 부모의 토글 함수가 `toolRefs` 스냅샷을 읽어 하나씩
   * 계산하는 구조라, 연달아 부르면 뒤 호출이 앞 호출을 덮어써 마지막 도구만
   * 반영된다. 그룹 전체를 한 번에 계산하는 별도 콜백으로 받는다.
   */
  onToggleGroup: (refs: string[], turnOn: boolean) => void;
}

/** `ToolChoice.category`가 없으면(MCP 등) 이 이름으로 묶는다. */
const UNCATEGORIZED = '기타';

/**
 * 카테고리 카드에 보여줄 한 줄 설명 — 개별 도구 설명과 달리 백엔드에 안
 * 둔다(화면 전용 문구라 도구마다 중복시킬 이유가 없다). 없으면 이름만
 * 보인다(카드 자체는 뜬다).
 */
const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  Jira: 'Jira 이슈를 조회하고, 확인을 거쳐 새 이슈로 등록합니다.',
  문서: '팀에 등록된 문서를 검색하고 목록을 확인합니다.',
  '업무 추출(AI)': '문서에서 업무 후보를 찾아 근거 문장과 함께 정리합니다.',
  '업무 관리': '등록된 업무를 조회·수정하고, 새 업무를 등록합니다.',
  프로젝트: '팀의 프로젝트 목록과 진행률을 확인합니다.',
  // 팀원 조회·부하 리포트·부재 조회를 하나로 묶었다 — 셋 다 같은 HR 데이터
  // (팀원 명부·역량·부재)가 원본이다.
  HR: '팀원의 이름·직책·기술 스택, 업무 부하, 부재(휴가 등) 현황을 조회합니다.',
  '웹 검색': '인터넷에서 정보를 찾아 출처 URL과 함께 알려줍니다.',
  [UNCATEGORIZED]: '카테고리가 지정되지 않은 도구입니다.',
};

/**
 * 개별 도구의 사람용 한 줄 설명. 백엔드의 `description`을 그대로 보여주면
 * 안 된다 — 그건 모델에게 쓴 지시문이라 내부 이름과 명령문이 그대로
 * 노출된다. 없으면 백엔드 설명으로 물러선다(MCP 도구 등).
 */
const TOOL_DESCRIPTIONS: Record<string, string> = {
  document_search: '문서에서 질문과 관련된 문장을 찾아 근거로 보여줍니다.',
  document_list: '팀에 어떤 문서가 있는지 목록으로 보여줍니다. 아직 읽지 않은 파일도 함께 알려줍니다.',
  people_list: '팀원의 이름·직책·기술 스택을 조회합니다.',
  workload_report: '팀원별로 남은 업무 시간을 계산해 보여줍니다.',
  absence_list: '팀원의 휴가 등 부재 일정을 조회합니다.',
  task_extraction: '문서에서 해야 할 일을 찾아 근거 문장과 함께 정리합니다.',
  project_list: '팀의 프로젝트 목록과 진행률을 조회합니다.',
  task_list: '등록된 업무를 조회합니다.',
  task_register: '정리된 업무를 시스템에 등록합니다.',
  task_update: '등록된 업무의 상태·담당자·마감을 고칩니다.',
  web_search: '인터넷에서 정보를 찾아 출처와 함께 알려줍니다.',
  jira_get_issues: 'Jira 이슈를 조회합니다.',
  jira_create_issues: 'Jira 에 새 이슈를 등록합니다.',
};

/** 카테고리 등장 순서를 그대로 유지해 그룹으로 묶는다. */
function groupByCategory(items: ToolChoice[]): [string, ToolChoice[]][] {
  const order: string[] = [];
  const byCategory = new Map<string, ToolChoice[]>();
  for (const item of items) {
    const category = item.category ?? UNCATEGORIZED;
    if (!byCategory.has(category)) {
      order.push(category);
      byCategory.set(category, []);
    }
    byCategory.get(category)!.push(item);
  }
  return order.map((category) => [category, byCategory.get(category)!]);
}

/**
 * 도구 선택 팝업 — 기본 제공 도구와 MCP 서버 도구를 탭으로 나눠 고른다.
 *
 * 한 화면에 다 늘어놓으면 MCP 서버가 늘수록(서버마다 도구 여러 개) 목록이
 * 한없이 길어진다. 탭으로 나누면 「지금 뭘 고르고 있는지」가 분명해진다.
 */
export function ToolPickerModal({
  open,
  onClose,
  builtinTools,
  mcpServers,
  toolRefs,
  onToggle,
  onToggleGroup,
}: ToolPickerModalProps) {
  const [tab, setTab] = useState<Tab>('builtin');
  const builtinGroups = groupByCategory(builtinTools);
  /** "세부 툴 확인"으로 펼친 카테고리 — 기본은 다 접혀 있다. 먼저 카테고리
   * 단위로만 고르게 하고, 안에 뭐가 있는지는 필요할 때만 보게 한다. */
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  function toggleExpanded(category: string) {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="도구 선택"
      width={640}
      footer={<Button onClick={onClose}>완료</Button>}
    >
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

      {tab === 'builtin' && (
        <div className={styles.serverList}>
          {builtinGroups.map(([category, items]) => {
            const allOn = items.every((toolItem) => toolRefs.includes(toolItem.tool_ref));
            const expanded = expandedCategories.has(category);
            return (
              <div key={category} className={styles.serverGroup}>
                <div className={styles.serverHead}>
                  <span className={styles.serverName}>
                    <Checkbox
                      checked={allOn}
                      onChange={(next) =>
                        onToggleGroup(
                          items.map((toolItem) => toolItem.tool_ref),
                          next,
                        )
                      }
                      label={category}
                    />
                  </span>
                  {CATEGORY_DESCRIPTIONS[category] && (
                    <p className={styles.categoryDesc}>{CATEGORY_DESCRIPTIONS[category]}</p>
                  )}
                </div>

                <button
                  type="button"
                  className={styles.expandToggle}
                  onClick={() => toggleExpanded(category)}
                  aria-expanded={expanded}
                >
                  <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={13} />
                  세부 툴 확인 ({items.length})
                </button>

                {expanded && (
                  <div className={styles.toolList}>
                    {items.map((toolItem) => {
                      const checked = toolRefs.includes(toolItem.tool_ref);
                      return (
                        <div
                          key={toolItem.tool_ref}
                          className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                        >
                          <Checkbox checked={checked} onChange={() => onToggle(toolItem.tool_ref)} />
                          <div className={styles.toolText}>
                            <strong>
                              {toolItem.name}
                              {toolItem.side_effect && <span className={styles.gate}> · 승인 필요</span>}
                            </strong>
                            <span>
                              {TOOL_DESCRIPTIONS[toolItem.tool_ref] ?? toolItem.description}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {builtinTools.length === 0 && <p className={styles.help}>기본 제공 도구가 없습니다.</p>}
        </div>
      )}

      {tab === 'mcp' && (
        <div className={styles.serverList}>
          {mcpServers.length === 0 && <p className={styles.help}>아직 이 팀에 붙어 있는 서버가 없습니다.</p>}
          {mcpServers.map((server) => {
            const chip = SERVER_STATUS[server.status];
            const usable = server.status === 'CONNECTED';
            return (
              <div key={server.mcp_server_id} className={styles.serverGroup}>
                <div className={styles.serverHead}>
                  <span className={styles.serverName}>
                    {server.name}
                    <Badge tone={chip.tone}>{chip.label}</Badge>
                  </span>
                  <span className={styles.help}>{server.endpoint_url}</span>
                </div>
                {!usable && (
                  <p className={styles.help}>
                    {server.status === 'UNCHECKED'
                      ? '설정에서 연결을 확인해야 도구를 고를 수 있습니다.'
                      : '연결이 실패한 서버입니다. 설정에서 연결 상태를 확인하세요.'}
                  </p>
                )}
                {usable && server.tools.length === 0 && (
                  <p className={styles.help}>이 서버는 제공하는 도구가 없습니다.</p>
                )}
                {usable && server.tools.length > 0 && (
                  <div className={styles.toolList}>
                    {server.tools.map((tool) => {
                      const ref = `mcp:${tool.mcp_tool_id}`;
                      const checked = toolRefs.includes(ref);
                      return (
                        <div
                          key={tool.mcp_tool_id}
                          className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                        >
                          <Checkbox checked={checked} disabled={!tool.enabled} onChange={() => onToggle(ref)} />
                          <div className={styles.toolText}>
                            <strong>
                              {tool.name}
                              <span className={styles.gate}> · 승인 필요</span>
                            </strong>
                            <span>{tool.description || (tool.enabled ? '' : '사용 중지된 도구입니다.')}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {/* 팀이 스스로 서버를 못 붙이므로, 어디로 말하면 되는지 남긴다. */}
          <p className={styles.help}>
            서버 등록은 운영자에게 요청하세요. 주소·키를 다루는 작업이라 운영자가 대신 등록합니다.
          </p>
        </div>
      )}

      {tab === 'create' && (
        <div className={styles.createTab}>
          <p className={styles.help}>
            팀에서 직접 도구를 만드는 기능은 아직 준비 중입니다. 지금은 기본 제공 도구와 이 팀에
            붙어 있는 커스텀 도구만 쓸 수 있습니다.
          </p>
          <Button variant="outline" disabled>
            새 도구 등록 (준비 중)
          </Button>
        </div>
      )}
    </Modal>
  );
}
