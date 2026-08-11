import { useEffect, useState } from 'react';
import { Badge, Button, Icon, Input, useToast } from '../../../components';
import type { BadgeTone } from '../../../components';
import {
  ApiError,
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  testMcpServer,
} from '../../../api/mcp';
import type { McpServer } from '../../../api/mcp';
import { loadSessionToken } from '../../../utils/session';
import styles from './tabs.module.css';

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<McpServer['status'], { tone: BadgeTone; label: string; hint: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨', hint: '' },
  UNCHECKED: {
    tone: 'neutral',
    label: '미확인',
    // 등록만 하고 아직 도구를 못 읽은 상태. 실패와 다르다.
    hint: '아직 연결 확인을 하지 않았습니다. 도구 목록이 비어 있습니다.',
  },
  ERROR: {
    tone: 'warning',
    label: '연결 실패',
    hint: '주소나 토큰을 고친 뒤 다시 확인해 주세요. 이 서버의 도구는 에이전트 편집에서 고를 수 없습니다.',
  },
};

/** MCP 탭 — 서버 목록·등록·연결 테스트·삭제 (개발지시_3차 단계 4). */
export function McpTab() {
  const { showToast } = useToast();
  const token = loadSessionToken();

  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    listMcpServers(token)
      .then(setServers)
      .catch((exc) => setError(exc instanceof ApiError ? exc.message : '목록을 불러오지 못했습니다.'));
  }, [token]);

  async function add() {
    if (!token || !name.trim() || !url.trim()) return;
    setBusy('add');
    setError(null);
    try {
      const created = await createMcpServer(token, {
        name: name.trim(),
        endpoint_url: url.trim(),
        auth_token: authToken.trim() || undefined,
      });
      setServers((prev) => [...prev, created]);
      setName('');
      setUrl('');
      setAuthToken('');
      // 등록과 연결 테스트는 다른 일이다. 등록되자마자 바로 확인해 준다.
      await test(created.mcp_server_id, created.name);
    } catch (exc) {
      // 주소 검사(SSRF·https 아님)는 저장 전에 400 으로 온다.
      setError(exc instanceof ApiError ? exc.message : '등록하지 못했습니다.');
    } finally {
      setBusy(null);
    }
  }

  async function test(serverId: string, serverName: string) {
    if (!token) return;
    setBusy(serverId);
    try {
      const outcome = await testMcpServer(token, serverId);
      if (outcome.ok) {
        showToast(`${serverName}: 도구 ${outcome.result.tool_count}종을 읽었습니다.`, 'success');
      } else {
        // 등록은 남기고 ERROR 로 표시한다 — 고쳐 쓸 값이다.
        showToast(`${serverName}: ${outcome.detail} (${outcome.errorCode})`, 'error');
      }
      setServers(await listMcpServers(token));
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '연결 확인에 실패했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  async function remove(server: McpServer) {
    if (!token) return;
    setBusy(server.mcp_server_id);
    try {
      await deleteMcpServer(token, server.mcp_server_id);
      setServers((prev) => prev.filter((item) => item.mcp_server_id !== server.mcp_server_id));
      // 이 서버의 도구를 쓰던 에이전트에서도 함께 빠진다(서버가 정리한다).
      showToast(`${server.name} 연결을 지웠습니다. 에이전트에 붙어 있던 도구도 함께 빠집니다.`, 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '지우지 못했습니다.', 'error');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.tab}>
      <p className={`${styles.notice} ${styles.noticeNeutral}`}>
        <Icon name="info" size={16} color="var(--color-muted)" />
        <span>
          여기서 연결한 서비스가 에이전트의 “할 수 있는 일”이 됩니다. 읽기만 하는 연결(Drive·HR)은 Connector 탭에,
          실제로 무언가를 만드는 연결은 여기에 둡니다. 주소는 <strong>https</strong>만 받고, 사내망·로컬 주소는
          거절합니다.
        </span>
      </p>

      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>연결된 MCP 서버</h2>
          <p className={styles.cardSub}>
            에이전트가 행동할 수 있는 경로입니다. 연결 상태가 나쁘면 해당 도구는 에이전트 편집 화면에서 선택할 수 없습니다.
          </p>
        </div>

        <div className={styles.list}>
          {servers.length === 0 && <p className={styles.cardSub}>아직 등록한 MCP 서버가 없습니다.</p>}

          {servers.map((server) => {
            const chip = STATUS[server.status];
            return (
              <div key={server.mcp_server_id} className={styles.row}>
                <span className={styles.rowIcon}>
                  <Icon name="link" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>
                    {server.name}
                    <Badge tone={chip.tone}>{chip.label}</Badge>
                  </span>
                  <span className={styles.rowMeta}>{server.endpoint_url}</span>
                  {server.tools.length > 0 && (
                    <span className={styles.chips}>
                      {server.tools.map((tool) => (
                        <span key={tool.mcp_tool_id} className={styles.chip}>
                          {tool.name}
                        </span>
                      ))}
                    </span>
                  )}
                  <span className={styles.rowMeta}>
                    {server.last_checked_at
                      ? `${new Date(server.last_checked_at).toLocaleString('ko-KR')} 확인`
                      : '확인한 적 없음'}
                    {server.has_token ? ' · 토큰 저장됨' : ' · 토큰 없음'}
                  </span>
                  {chip.hint && <span className={styles.rowMeta}>{chip.hint}</span>}
                </div>
                <div className={styles.rowActions}>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy === server.mcp_server_id}
                    onClick={() => test(server.mcp_server_id, server.name)}
                  >
                    {busy === server.mcp_server_id ? '확인 중…' : '연결 확인'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy === server.mcp_server_id}
                    onClick={() => remove(server)}
                  >
                    지우기
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>MCP 서버 추가</h2>
          <p className={styles.cardSub}>
            서버 주소와 인증 정보를 넣으면 제공 도구를 자동으로 읽어옵니다. 토큰은 암호화해서 저장하고 화면에는 다시
            보여주지 않습니다.
          </p>
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
            label="서버 주소 (https)"
            id="mcp-url"
            name="mcpUrl"
            placeholder="https://mcp.example.com/v1/sse"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Input
            label="인증 토큰 (없으면 비워 두세요)"
            id="mcp-token"
            name="mcpToken"
            type="password"
            placeholder="••••••••••••"
            value={authToken}
            onChange={(event) => setAuthToken(event.target.value)}
          />
        </div>

        <div className={styles.formActions}>
          <Button onClick={add} disabled={busy === 'add' || !name.trim() || !url.trim()}>
            {busy === 'add' ? '확인하는 중…' : '연결 테스트 후 추가'}
          </Button>
        </div>
      </section>
    </div>
  );
}
