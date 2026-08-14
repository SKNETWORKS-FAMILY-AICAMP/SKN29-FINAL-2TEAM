import { useEffect, useState } from 'react';
import { Badge, Button, Icon, InfoNote, Input, useToast } from '../../../components';
import type { BadgeTone } from '../../../components';
import {
  ApiError,
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  testMcpServer,
  updateMcpServer,
} from '../../../api/mcp';
import type { McpServer } from '../../../api/mcp';
import { loadSessionToken, useSession } from '../../../utils/session';
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
  // 등록·삭제·연결 확인은 서버가 팀장만 받는다(`require_leader`). 화면도 같은 말을
  // 해야 한다 — 눌러 보고 나서 토스트로 알려 주는 것은 안내가 아니다(2026-08-13).
  const session = useSession();
  const isLeader = session?.account.role === 'leader';

  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** 수정 중인 서버. 저장된 토큰은 서버가 안 주므로 칸을 비워 두고 시작한다. */
  const [editing, setEditing] = useState<{ id: string; name: string; url: string; token: string } | null>(null);

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

  async function save() {
    if (!token || !editing || !editing.name.trim() || !editing.url.trim()) return;
    setBusy(editing.id);
    setError(null);
    try {
      const updated = await updateMcpServer(token, editing.id, {
        name: editing.name.trim(),
        endpoint_url: editing.url.trim(),
        // 비워 두면 저장된 토큰을 그대로 둔다. 바꾸려는 의사를 명시할 때만 보낸다.
        ...(editing.token.trim() ? { auth_token: editing.token.trim(), replace_token: true } : {}),
      });
      setServers((prev) => prev.map((s) => (s.mcp_server_id === updated.mcp_server_id ? updated : s)));
      setEditing(null);
      // 주소가 바뀌었으면 서버가 도구를 지우고 UNCHECKED 로 되돌렸다 — 그 사실을 말한다.
      showToast(
        updated.status === 'UNCHECKED'
          ? `${updated.name} 을 수정했습니다. 주소가 바뀌어 도구를 다시 읽어야 합니다.`
          : `${updated.name} 을 수정했습니다.`,
        'success',
      );
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '수정하지 못했습니다.');
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
      {session && !isLeader && (
        <p className={`${styles.notice} ${styles.noticeNeutral}`} role="alert">
          <Icon name="info" size={16} color="var(--color-muted)" />
          <span>
            팀장만 MCP 서버를 등록할 수 있습니다. 팀원은 팀장이 붙인 서버의 도구를 에이전트에서
            그대로 고를 수 있습니다.
          </span>
        </p>
      )}

      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            MCP
            <InfoNote title="MCP">
              <p>
                <strong>직접 만들거나 운영하는 서버</strong>를 붙이는 곳입니다. 주소와 인증 정보를 넣으면
                그 서버가 제공하는 도구를 에이전트가 쓸 수 있습니다.
              </p>
              <p>
                Connector 탭과는 <strong>인증 주체</strong>로 갈립니다 — Connector는 우리가 미리 등록해 둔
                통로이고, MCP는 사용자 소유 서버입니다. 「읽기는 Connector, 쓰기는 MCP」가 아닙니다(Jira는
                읽기도 쓰기도 합니다).
              </p>
              <p>
                주소는 <strong>https</strong>만 받고 사내망·로컬 주소는 거절합니다. 토큰은 암호화해 저장하고
                화면에 다시 보여주지 않습니다.
              </p>
              <p>연결 상태가 나쁜 서버의 도구는 에이전트 편집 화면에서 고를 수 없습니다.</p>
            </InfoNote>
          </h2>
        </div>

        <div className={styles.list}>
          {servers.length === 0 && <p className={styles.cardSub}>아직 등록한 MCP 서버가 없습니다.</p>}

          {servers.map((server) => {
            const chip = STATUS[server.status];

            if (editing?.id === server.mcp_server_id) {
              return (
                <div key={server.mcp_server_id} className={styles.row}>
                  <div className={styles.rowBody}>
                    <div className={styles.formRow}>
                      <Input
                        label="서버 이름"
                        id={`mcp-edit-name-${server.mcp_server_id}`}
                        name="mcpEditName"
                        value={editing.name}
                        onChange={(event) => setEditing({ ...editing, name: event.target.value })}
                      />
                      <Input
                        label="서버 주소 (https)"
                        id={`mcp-edit-url-${server.mcp_server_id}`}
                        name="mcpEditUrl"
                        value={editing.url}
                        onChange={(event) => setEditing({ ...editing, url: event.target.value })}
                      />
                      <Input
                        label={server.has_token ? '인증 토큰 (비워 두면 그대로)' : '인증 토큰 (없으면 비워 두세요)'}
                        id={`mcp-edit-token-${server.mcp_server_id}`}
                        name="mcpEditToken"
                        type="password"
                        placeholder={server.has_token ? '저장된 토큰 유지' : '••••••••••••'}
                        value={editing.token}
                        onChange={(event) => setEditing({ ...editing, token: event.target.value })}
                      />
                    </div>
                    <span className={styles.rowMeta}>
                      주소를 바꾸면 지금 읽어 둔 도구는 지워집니다 — 다른 서버의 도구이기 때문입니다.
                      「연결 확인」을 다시 눌러야 에이전트가 고를 수 있습니다.
                    </span>
                  </div>
                  <div className={styles.rowActions}>
                    <Button
                      size="sm"
                      disabled={busy === server.mcp_server_id || !editing.name.trim() || !editing.url.trim()}
                      onClick={save}
                    >
                      {busy === server.mcp_server_id ? '저장 중…' : '저장'}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                      취소
                    </Button>
                  </div>
                </div>
              );
            }

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
                    disabled={!isLeader || busy !== null}
                    onClick={() =>
                      setEditing({
                        id: server.mcp_server_id,
                        name: server.name,
                        url: server.endpoint_url,
                        // 저장된 토큰은 서버가 안 준다. 비워 두면 그대로 유지된다.
                        token: '',
                      })
                    }
                  >
                    수정
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!isLeader || busy === server.mcp_server_id}
                    onClick={() => test(server.mcp_server_id, server.name)}
                  >
                    {busy === server.mcp_server_id ? '확인 중…' : '연결 확인'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!isLeader || busy === server.mcp_server_id}
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

      {isLeader && (
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>MCP 서버 추가</h2>
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
      )}
    </div>
  );
}
