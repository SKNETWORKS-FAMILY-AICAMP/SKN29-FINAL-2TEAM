import { useEffect, useState } from 'react';
import { Badge, Icon, InfoNote } from '../../../components';
import type { BadgeTone } from '../../../components';
import { ApiError, listMcpServers } from '../../../api/mcp';
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
    hint: '이 서버의 도구는 에이전트 편집에서 고를 수 없습니다. 저희에게 알려 주시면 확인하겠습니다.',
  },
};

/**
 * 커스텀 도구 탭 — **보기만 한다**(2026-08-18 멘토링).
 *
 * 등록·수정·삭제·연결 확인은 운영자 콘솔로 옮겼다. 붙이려면 https 주소와 인증
 * 토큰을 알아야 하는데, 그건 「코딩 없이」를 내세운 제품이 비개발자에게 요구할
 * 일이 아니다 — 8/13 에 모델로 이미 밟은 길이다(`ModelTab.tsx`).
 *
 * **화면에서만 감춘 것이 아니다.** 팀 쪽 쓰기 API 자체를 걷어냈다
 * (`apps/mcp/api_urls.py`) — 폼만 없애면 API 를 그대로 부를 수 있어서 그건
 * 규칙이 아니라 장식이다.
 */
export function McpTab() {
  const token = loadSessionToken();

  const [servers, setServers] = useState<McpServer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    listMcpServers(token)
      .then(setServers)
      .catch((exc) => setError(exc instanceof ApiError ? exc.message : '목록을 불러오지 못했습니다.'));
  }, [token]);

  return (
    <div className={styles.tab}>
      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            커스텀 도구
            <InfoNote title="커스텀 도구">
              <p>
                <strong>직접 만들거나 운영하는 서버</strong>를 붙이는 곳입니다. 붙여 두면 그 서버가
                제공하는 도구를 에이전트가 쓸 수 있습니다. MCP·FastAPI 둘 다 됩니다.
              </p>
              <p>
                Connector 탭과는 <strong>인증 주체</strong>로 갈립니다 — Connector는 우리가 미리 등록해 둔
                통로이고, 여기는 사용자 소유 서버입니다. 「읽기는 Connector, 쓰기는 이쪽」이 아닙니다(Jira는
                읽기도 쓰기도 합니다).
              </p>
              {/* 문구는 8/13 에 Model 탭에 붙인 안내와 같은 말이다 — 같은 일을
                  다른 말로 설명하면 사용자가 다른 절차로 읽는다. */}
              <p>
                <strong>붙이는 일은 저희가 대신 합니다.</strong> 주소와 인증 토큰을 다루는 일이라
                직접 넣게 하지 않습니다.
              </p>
              <p>연결 상태가 나쁜 서버의 도구는 에이전트 편집 화면에서 고를 수 없습니다.</p>
            </InfoNote>
          </h2>
        </div>

        <div className={styles.list}>
          {servers.length === 0 && (
            <p className={styles.cardSub}>아직 이 팀에 붙어 있는 서버가 없습니다.</p>
          )}

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
                  </span>
                  {chip.hint && <span className={styles.rowMeta}>{chip.hint}</span>}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* **폼이 있던 자리를 비워 두지 않는다.** 없애기만 하면 「기능이
          사라졌다」로 읽힌다 — 어디로 말하면 되는지가 남아야 한다.
          말은 Model 탭(8/13)과 맞춘다. */}
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>서버를 붙이고 싶다면</h2>
        </div>
        <p className={styles.cardSub}>
          사내에 띄운 서버나 직접 만든 도구가 있으시면 —{' '}
          <strong>저희에게 요청하시면 이 팀에만 등록해 드립니다.</strong> 주소·토큰을 다루는 일이라
          저희가 대신 합니다. 등록해 드리면 이 목록에 바로 보이고, 에이전트 편집에서 그 도구를 고를
          수 있습니다.
        </p>
      </section>
    </div>
  );
}
