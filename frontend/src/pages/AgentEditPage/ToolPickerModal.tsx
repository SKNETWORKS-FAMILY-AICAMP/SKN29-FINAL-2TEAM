import { useState } from 'react';
import { Badge, Button, Checkbox, Icon, Modal } from '../../components';
import type { BadgeTone } from '../../components';
import type { ToolChoice } from '../../api/agents';
import type { McpServer } from '../../api/mcp';
import pageStyles from './AgentEditPage.module.css';
import styles from './ToolPickerModal.module.css';

type Tab = 'builtin' | 'mcp' | 'create';

const TABS: { id: Tab; label: string }[] = [
  { id: 'builtin', label: '툴 선택' },
  { id: 'mcp', label: 'MCP 서버 선택' },
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
   * 카테고리 카드 헤더의 「전체 선택」 마스터 체크박스(2026-08-18, 도구
   * 선택 그룹화). **`onToggle`을 여러 번 부르지 않는다** — 부모의 토글
   * 함수가 `toolRefs` 스냅샷을 읽어 하나씩 계산하는 구조라, 같은 렌더
   * 안에서 연달아 부르면 뒤 호출이 앞 호출을 덮어써 마지막 도구 하나만
   * 반영된다(ChatPage의 세션 override가 특히 그렇다 — 상태가 아니라 API
   * 응답을 기다려 갱신한다). 그룹 전체를 한 번에 계산해 한 번만 반영하도록
   * 별도 콜백으로 받는다.
   */
  onToggleGroup: (refs: string[], turnOn: boolean) => void;
  onGoToMcpSettings: () => void;
}

/** `ToolChoice.category`가 없으면(MCP 등) 이 이름으로 묶는다. */
const UNCATEGORIZED = '기타';

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
  onGoToMcpSettings,
}: ToolPickerModalProps) {
  const [tab, setTab] = useState<Tab>('builtin');
  const builtinGroups = groupByCategory(builtinTools);

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
                </div>
                <div className={pageStyles.toolList}>
                  {items.map((toolItem) => {
                    const checked = toolRefs.includes(toolItem.tool_ref);
                    return (
                      <div
                        key={toolItem.tool_ref}
                        className={[pageStyles.toolRow, checked ? pageStyles.toolRowOn : ''].filter(Boolean).join(' ')}
                      >
                        <Checkbox checked={checked} onChange={() => onToggle(toolItem.tool_ref)} />
                        <div className={pageStyles.toolText}>
                          <strong>
                            {toolItem.name}
                            {toolItem.side_effect && <span className={pageStyles.gate}> · 승인 필요</span>}
                          </strong>
                          <span>{toolItem.description}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
          {builtinTools.length === 0 && <p className={pageStyles.help}>기본 제공 도구가 없습니다.</p>}
        </div>
      )}

      {tab === 'mcp' && (
        <div className={styles.serverList}>
          {mcpServers.length === 0 && <p className={pageStyles.help}>아직 연결한 MCP 서버가 없습니다.</p>}
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
                  <span className={pageStyles.help}>{server.endpoint_url}</span>
                </div>
                {!usable && (
                  <p className={pageStyles.help}>
                    {server.status === 'UNCHECKED'
                      ? '설정에서 연결을 확인해야 도구를 고를 수 있습니다.'
                      : '연결이 실패한 서버입니다. 설정에서 다시 확인해 주세요.'}
                  </p>
                )}
                {usable && server.tools.length === 0 && (
                  <p className={pageStyles.help}>이 서버는 제공하는 도구가 없습니다.</p>
                )}
                {usable && server.tools.length > 0 && (
                  <div className={pageStyles.toolList}>
                    {server.tools.map((tool) => {
                      const ref = `mcp:${tool.mcp_tool_id}`;
                      const checked = toolRefs.includes(ref);
                      return (
                        <div
                          key={tool.mcp_tool_id}
                          className={[pageStyles.toolRow, checked ? pageStyles.toolRowOn : ''].filter(Boolean).join(' ')}
                        >
                          <Checkbox checked={checked} disabled={!tool.enabled} onChange={() => onToggle(ref)} />
                          <div className={pageStyles.toolText}>
                            <strong>
                              {tool.name}
                              <span className={pageStyles.gate}> · 승인 필요</span>
                            </strong>
                            <span>{tool.description || (tool.enabled ? '' : '비활성화된 도구입니다.')}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          <button type="button" className={styles.settingsLink} onClick={onGoToMcpSettings}>
            <Icon name="arrow-right" size={14} />
            MCP 서버 관리로 이동
          </button>
        </div>
      )}

      {tab === 'create' && (
        <div className={styles.createTab}>
          <p className={pageStyles.help}>
            팀에서 직접 도구를 만드는 기능은 아직 준비 중입니다. 지금은 기본 제공 도구와 연결한
            MCP 서버의 도구만 쓸 수 있습니다.
          </p>
          <Button variant="outline" disabled>
            새 도구 만들기 (준비 중)
          </Button>
        </div>
      )}
    </Modal>
  );
}
