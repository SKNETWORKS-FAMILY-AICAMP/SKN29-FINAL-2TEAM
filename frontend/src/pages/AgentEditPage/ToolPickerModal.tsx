import { useState } from 'react';
import { Badge, Button, Checkbox, Modal } from '../../components';
import type { BadgeTone } from '../../components';
import type { ToolChoice } from '../../api/agents';
import type { McpServer } from '../../api/mcp';
import pageStyles from './AgentEditPage.module.css';
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
}: ToolPickerModalProps) {
  const [tab, setTab] = useState<Tab>('builtin');

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
        <div className={pageStyles.toolList}>
          {builtinTools.map((toolItem) => {
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
          {builtinTools.length === 0 && <p className={pageStyles.help}>기본 제공 도구가 없습니다.</p>}
        </div>
      )}

      {tab === 'mcp' && (
        <div className={styles.serverList}>
          {mcpServers.length === 0 && <p className={pageStyles.help}>아직 이 팀에 붙어 있는 서버가 없습니다.</p>}
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
          {/* 설정으로 보내던 버튼은 걷었다(2026-08-18) — 그 탭이 없어졌고,
              팀이 스스로 붙일 수도 없다. 대신 **어디로 말하면 되는지**를
              남긴다. 문구는 Model 탭(8/13)과 같은 말이다. */}
          <p className={pageStyles.help}>
            필요한 서버가 있으시면 저희에게 요청하시면 이 팀에만 등록해 드립니다.
          </p>
        </div>
      )}

      {tab === 'create' && (
        <div className={styles.createTab}>
          <p className={pageStyles.help}>
            팀에서 직접 도구를 만드는 기능은 아직 준비 중입니다. 지금은 기본 제공 도구와 이 팀에
            붙어 있는 커스텀 도구만 쓸 수 있습니다.
          </p>
          <Button variant="outline" disabled>
            새 도구 만들기 (준비 중)
          </Button>
        </div>
      )}
    </Modal>
  );
}
