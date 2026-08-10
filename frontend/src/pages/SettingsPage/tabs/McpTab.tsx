import { useState } from 'react';
import { Badge, Button, Icon, Input, useToast } from '../../../components';
import type { BadgeTone } from '../../../components';
import styles from './tabs.module.css';

interface McpServer {
  name: string;
  tone: BadgeTone;
  status: string;
  url: string;
  tools: string[];
  checked: string;
  connected: boolean;
}

/**
 * MCP 탭 (P0). 서버 목록·등록 폼·연결 상태.
 *
 * 백엔드 단계 6(MCP Server API)이 붙기 전이라 목록은 mock이다. API 계약이
 * 정해지면 이 배열만 교체한다 — 상태 칩·도구 목록의 모양은 그대로 쓴다.
 */
const MOCK_SERVERS: McpServer[] = [
  {
    name: 'Jira',
    tone: 'success',
    status: '연결됨',
    url: 'https://mcp.atlassian.com/v1/sse',
    tools: ['이슈 생성', '이슈 조회', '프로젝트 생성'],
    checked: '08.10 09:24 확인',
    connected: true,
  },
  {
    name: 'Slack',
    tone: 'warning',
    status: '확인 필요',
    url: 'https://mcp.slack.example/v1/sse',
    tools: ['메시지 보내기'],
    checked: '08.07 18:02 확인 · 토큰 만료 임박',
    connected: true,
  },
  {
    name: 'Notion',
    tone: 'neutral',
    status: '미연결',
    url: '—',
    tools: [],
    checked: '연결한 적 없음',
    connected: false,
  },
];

export function McpTab() {
  const { showToast } = useToast();
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');

  function handleAdd() {
    showToast('MCP Server 등록은 백엔드 단계 6 연결 후 동작합니다.', 'error');
  }

  return (
    <div className={styles.tab}>
      <p className={`${styles.notice} ${styles.noticeNeutral}`}>
        <Icon name="info" size={16} color="var(--color-muted)" />
        <span>
          여기서 연결한 서비스가 에이전트의 “할 수 있는 일”이 됩니다. 읽기만 하는 연결(Drive·HR)은 Connector 탭에,
          실제로 무언가를 만드는 연결(Jira 이슈 생성 등)은 여기에 둡니다.
        </span>
      </p>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>연결된 MCP 서버</h2>
          <p className={styles.cardSub}>
            에이전트가 행동할 수 있는 경로입니다. 연결 상태가 나쁘면 해당 도구는 에이전트 편집 화면에서 선택할 수 없습니다.
          </p>
        </div>

        <div className={styles.list}>
          {MOCK_SERVERS.map((server) => (
            <div key={server.name} className={styles.row}>
              <span className={styles.rowIcon}>
                <Icon name="link" size={20} color="var(--color-primary)" />
              </span>
              <div className={styles.rowBody}>
                <span className={styles.rowName}>
                  {server.name}
                  <Badge tone={server.tone}>{server.status}</Badge>
                </span>
                <span className={styles.rowMeta}>{server.url}</span>
                {server.tools.length > 0 && (
                  <span className={styles.chips}>
                    {server.tools.map((tool) => (
                      <span key={tool} className={styles.chip}>
                        {tool}
                      </span>
                    ))}
                  </span>
                )}
                <span className={styles.rowMeta}>{server.checked}</span>
              </div>
              <div className={styles.rowActions}>
                <Button size="sm" variant="outline" onClick={() => showToast('연결 확인은 단계 6 연결 후 동작합니다.', 'error')}>
                  연결 확인
                </Button>
                <Button size="sm" variant="ghost">
                  {server.connected ? '설정' : '연결하기'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>MCP 서버 추가</h2>
          <p className={styles.cardSub}>서버 주소와 인증 정보를 넣으면 제공 도구를 자동으로 읽어옵니다.</p>
        </div>

        <div className={styles.formRow}>
          <Input
            label="서버 이름"
            id="mcp-name"
            name="mcpName"
            placeholder="Jira"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            label="서버 주소 (SSE endpoint)"
            id="mcp-url"
            name="mcpUrl"
            placeholder="https://mcp.example.com/v1/sse"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Input
            label="인증 토큰"
            id="mcp-token"
            name="mcpToken"
            type="password"
            placeholder="••••••••••••"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </div>

        <div className={styles.formActions}>
          <Button onClick={handleAdd}>연결 테스트 후 추가</Button>
        </div>
      </section>
    </div>
  );
}
