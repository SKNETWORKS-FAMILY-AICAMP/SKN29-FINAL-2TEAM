import { useCallback, useEffect, useState } from 'react';
import { Badge, Button, OpsDataTable, OpsEmpty, OpsSectionCard } from '../../components';
import type { BadgeTone } from '../../components';
import {
  fetchOpsMcpServers,
  probeOpsMcpServer,
  registerOpsMcpServer,
  removeOpsMcpServer,
  testOpsMcpServer,
} from '../../api/opsMcp';
import type { OpsMcpServer } from '../../api/opsMcp';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 이 팀의 커스텀 도구 — 등록·연결 확인·지우기.
 *
 * **팀 상세로 옮겨 왔다**(2026-08-18 PM). 이유는 `TeamModelSection` 과 같다 —
 * 한 팀을 세팅하는데 페이지 둘을 돌며 같은 팀을 두 번 골라야 했다.
 *
 * 팀이 스스로 등록하지 않는 것은 그대로다(8/18 멘토링). 주소와 토큰을 다루는
 * 일이라 「코딩 없이」를 내세운 제품이 비개발자에게 시킬 일이 아니다.
 */

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<OpsMcpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  // 등록만 하고 아직 도구를 못 읽은 상태. 실패와 다르다.
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

export function TeamToolSection({ teamId }: { teamId: string }) {
  const [servers, setServers] = useState<OpsMcpServer[]>([]);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  /** 「연결 확인」으로 읽어 온 도구 이름들. 등록 전에 무엇이 들어오는지 보여준다. */
  const [found, setFound] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session) return;
    try {
      const rows = await fetchOpsMcpServers(session.token);
      // 목록 API 는 전 팀을 준다. 여기서는 이 팀 것만 본다.
      setServers(rows.filter((row) => row.team_id === teamId));
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '목록을 불러오지 못했습니다.');
    }
  }, [teamId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 저장하기 전에 그 주소로 도구를 읽어 본다. 행은 만들지 않는다. */
  async function probe() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    setNote('');
    setFound(null);
    try {
      const result = await probeOpsMcpServer(session.token, url.trim(), authToken.trim());
      if (result.detail) setError(result.detail);
      else setFound(result.tools);
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '연결 확인에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function register() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    setNote('');
    try {
      const created = await registerOpsMcpServer(session.token, {
        team_id: teamId,
        name: name.trim(),
        endpoint_url: url.trim(),
        auth_token: authToken.trim() || undefined,
      });
      // 토큰은 화면에도 남기지 않는다.
      setName('');
      setUrl('');
      setAuthToken('');
      setFound(null);
      // **등록과 연결 확인은 다른 일이다.** 한 버튼에 묶으면 실패했을 때 등록이
      // 안 된 것인지 연결이 안 된 것인지 화면이 말해 줄 수 없다.
      setNote(`${created.name} 연결을 등록했습니다. 도구는 목록에서 「연결 확인」을 눌러 읽습니다.`);
      await load();
    } catch (thrown) {
      // 주소 검사(SSRF·https 아님)는 저장 전에 400 으로 온다.
      setError(thrown instanceof ApiError ? thrown.message : '등록하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function test(row: OpsMcpServer) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const result = await testOpsMcpServer(session.token, row.mcp_server_id, teamId);
      setNote(`${row.name}: 도구 ${result.tool_count}종을 읽었습니다.`);
    } catch (thrown) {
      // 등록은 남기고 ERROR 로 표시한다 — 고쳐 쓸 값이다.
      setNote('');
      setError(thrown instanceof ApiError ? thrown.message : '연결 확인에 실패했습니다.');
    } finally {
      await load();
      setBusy(false);
    }
  }

  async function remove(row: OpsMcpServer) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await removeOpsMcpServer(session.token, row.mcp_server_id, teamId);
      // 이 서버의 도구를 쓰던 에이전트에서도 함께 빠진다(서버가 정리한다).
      setNote(`${row.name} 연결을 지웠습니다. 에이전트에 붙어 있던 도구도 함께 빠집니다.`);
      await load();
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '지우지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const canRegister = Boolean(name.trim() && url.trim());

  return (
    <OpsSectionCard
      title={`이 팀의 커스텀 도구 ${servers.length}건`}
      subtitle="https 주소만 받고 사내망·로컬 주소는 저장 전에 거절합니다. 토큰은 암호화해 저장하고 다시 보여주지 않습니다."
    >
      <div className={styles.formGrid}>
        <div className={styles.fieldGroup}>
          <label htmlFor="tool-name">서버 이름</label>
          <input
            id="tool-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="사내 이슈 트래커"
          />
        </div>

        <div className={styles.fieldGroup}>
          <label htmlFor="tool-url">서버 주소 (https)</label>
          <input
            id="tool-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://mcp.example.com/v1/sse"
          />
        </div>

        <div className={styles.fieldGroup}>
          <label htmlFor="tool-token">인증 토큰 (없으면 비워 두세요)</label>
          <input
            id="tool-token"
            type="password"
            value={authToken}
            onChange={(event) => setAuthToken(event.target.value)}
          />
        </div>
      </div>

      {found && (
        <p className={styles.inlineEmpty}>
          {found.length > 0
            ? `도구 ${found.length}종을 읽었습니다 — ${found.join(', ')}`
            : '연결은 됐지만 이 서버는 제공하는 도구가 없습니다.'}
        </p>
      )}
      {note && <p className={styles.inlineEmpty}>{note}</p>}
      {error && <p className={styles.inlineEmpty} role="alert">{error}</p>}

      {/* **둘을 따로 놓는다**(2026-08-18 PM). 연결 확인은 저장하지 않고 주소만
          두드려 보고, 등록은 행을 만든다 — 한 버튼에 묶여 있으면 실패했을 때
          등록이 안 된 것인지 연결이 안 된 것인지 화면이 말해 줄 수 없다. */}
      <div className={styles.formSubmit}>
        <Button variant="outline" onClick={probe} disabled={!url.trim() || busy}>
          {busy ? '확인하는 중…' : '연결 확인'}
        </Button>
        <Button onClick={register} disabled={!canRegister || busy}>
          등록
        </Button>
      </div>

      {servers.length === 0 ? (
        <OpsEmpty message="이 팀에 붙어 있는 서버가 없습니다." />
      ) : (
        <OpsDataTable minWidth={820}>
          <thead>
            <tr>
              <th style={{ width: 150 }}>이름</th>
              <th>주소</th>
              <th style={{ width: 90 }}>상태</th>
              <th style={{ width: 70 }}>도구</th>
              <th style={{ width: 110 }}>확인</th>
              {/* 버튼 둘이 한 줄에 들어갈 폭을 준다 — 좁으면 세로로 접혀
                  좁은 화면의 쌓기와 구분이 안 된다(2026-08-18 PM 지적). */}
              <th style={{ width: 210 }} />
            </tr>
          </thead>
          <tbody>
            {servers.map((row) => (
              <tr key={row.mcp_server_id}>
                <td>{row.name}</td>
                <td className={styles.cellEllipsis} title={row.endpoint_url}>
                  {row.endpoint_url}
                </td>
                <td>
                  <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                </td>
                <td>{row.tool_count}종</td>
                <td>{row.last_checked_at ? row.last_checked_at.slice(0, 10) : '없음'}</td>
                <td>
                  <div className={styles.cellActions}>
                    {/* `data-button` — 운영자 표는 안에 든 버튼의 테두리를 벗겨
                        글씨처럼 만든다(`OpsUi.module.css`). 여기는 버튼으로
                        보여야 해서 빠져나간다. */}
                    <Button
                      size="sm"
                      variant="outline"
                      data-button
                      disabled={busy}
                      onClick={() => test(row)}
                    >
                      연결 확인
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      data-button
                      disabled={busy}
                      onClick={() => remove(row)}
                    >
                      지우기
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </OpsDataTable>
      )}
    </OpsSectionCard>
  );
}
