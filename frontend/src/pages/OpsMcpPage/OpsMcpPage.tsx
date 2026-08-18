import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, OpsDataTable, OpsEmpty, OpsPageHeader, OpsSectionCard } from '../../components';
import type { BadgeTone } from '../../components';
import {
  fetchOpsMcpServers,
  probeOpsMcpServer,
  registerOpsMcpServer,
  removeOpsMcpServer,
  testOpsMcpServer,
} from '../../api/opsMcp';
import type { OpsMcpServer } from '../../api/opsMcp';
import { fetchOpsTeams } from '../../api/opsTeams';
import type { OpsTeam } from '../../api/opsTeams';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 팀별 커스텀 도구 등록.
 *
 * **팀이 스스로 등록하지 않는다.** 요청을 받으면 운영자가 여기서 등록한다
 * (2026-08-18 멘토링). 설정의 등록 폼을 없애고 이 화면으로 옮긴 이유는
 * `apps/ops/views/mcp.py` 에 적어 두었다 — 모델(8/13)과 같은 길이다.
 *
 * 등록하는 사람만 바뀌고 **쓸 수 있는 범위는 여전히 그 팀뿐이다.**
 */

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<OpsMcpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  // 등록만 하고 아직 도구를 못 읽은 상태. 실패와 다르다.
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

const TITLE = '커스텀 도구';

export default function OpsMcpPage() {
  const navigate = useNavigate();
  const [servers, setServers] = useState<OpsMcpServer[] | null>(null);
  const [teams, setTeams] = useState<OpsTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [teamId, setTeamId] = useState('');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [note, setNote] = useState('');
  /** 「연결 확인」으로 읽어 온 도구 이름들. 등록 전에 무엇이 들어오는지 보여준다. */
  const [found, setFound] = useState<string[] | null>(null);

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [rows, teamRows] = await Promise.all([
        fetchOpsMcpServers(session.token),
        fetchOpsTeams(session.token),
      ]);
      setServers(rows);
      setTeams(teamRows);
      if (!teamId && teamRows.length > 0) setTeamId(teamRows[0].team_id);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function register() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
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
      // **등록과 연결 확인은 다른 일이다**(2026-08-18 PM). 등록은 행을 만들고,
      // 연결 확인은 그 주소를 실제로 두드린다 — 한 버튼에 묶으면 둘 중 어느
      // 쪽이 실패했는지 화면이 말해 줄 수 없다.
      setNote(created.name + ' 연결을 등록했습니다. 도구는 목록에서 ‘연결 확인’을 눌러 읽습니다.');
      await load();
    } catch (thrown) {
      // 주소 검사(SSRF·https 아님)는 저장 전에 400 으로 온다.
      setFormError(thrown instanceof ApiError ? thrown.message : '등록하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  /** 저장하기 전에 그 주소로 도구를 읽어 본다. 행은 만들지 않는다. */
  async function probe() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    setNote('');
    setFound(null);
    try {
      const result = await probeOpsMcpServer(session.token, url.trim(), authToken.trim());
      if (result.detail) {
        setFormError(result.detail);
      } else {
        setFound(result.tools);
      }
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '연결 확인에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function test(serverId: string, ofTeam: string, serverName: string) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    try {
      const result = await testOpsMcpServer(session.token, serverId, ofTeam);
      setNote(serverName + ': 도구 ' + result.tool_count + '종을 읽었습니다.');
    } catch (thrown) {
      // 등록은 남기고 ERROR 로 표시한다 — 고쳐 쓸 값이다.
      setNote('');
      setFormError(thrown instanceof ApiError ? thrown.message : '연결 확인에 실패했습니다.');
    } finally {
      await load();
      setBusy(false);
    }
  }

  async function remove(row: OpsMcpServer) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    setNote('');
    try {
      await removeOpsMcpServer(session.token, row.mcp_server_id, row.team_id);
      // 이 서버의 도구를 쓰던 에이전트에서도 함께 빠진다(서버가 정리한다).
      setNote(row.name + ' 연결을 지웠습니다. 에이전트에 붙어 있던 도구도 함께 빠집니다.');
      await load();
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '지우지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  if (loading && !servers) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const rows = servers ?? [];
  const canRegister = Boolean(teamId && name.trim() && url.trim());

  return (
    <div className={styles.page}>
      <OpsPageHeader title={TITLE} />

      <OpsSectionCard
        title="새로 등록"
      >
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="mcp-team">팀</label>
            <select id="mcp-team" value={teamId} onChange={(event) => setTeamId(event.target.value)}>
              {teams.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {team.name} ({team.team_id})
                </option>
              ))}
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="mcp-name">서버 이름</label>
            <input
              id="mcp-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="사내 이슈 트래커"
            />
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="mcp-url">서버 주소 (https)</label>
            <input
              id="mcp-url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://mcp.example.com/v1/sse"
            />
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="mcp-token">인증 토큰 (없으면 비워 두세요)</label>
            <input
              id="mcp-token"
              type="password"
              value={authToken}
              onChange={(event) => setAuthToken(event.target.value)}
            />
          </div>
        </div>

        {found && (
          <p className={styles.inlineEmpty}>
            {found.length > 0
              ? `도구 ${found.length}종을 읽었습니다: ${found.join(', ')}`
              : '연결은 됐지만 이 서버는 제공하는 도구가 없습니다.'}
          </p>
        )}
        {note && <p className={styles.inlineEmpty}>{note}</p>}
        {formError && <p className={styles.inlineEmpty} role="alert">{formError}</p>}

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
      </OpsSectionCard>

      <OpsSectionCard title={'등록된 서버 ' + rows.length + '건'}>
        {rows.length === 0 ? (
          <OpsEmpty message="아직 어느 팀에도 등록한 서버가 없습니다." />
        ) : (
          <OpsDataTable minWidth={960}>
            <thead>
              {/* `table-layout: fixed` 라 폭을 안 주면 7칸이 균등하게 갈린다 —
                  정작 긴 주소만 굶는다. */}
              <tr>
                <th style={{ width: 130 }}>팀</th>
                <th style={{ width: 150 }}>이름</th>
                <th>주소</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 70 }}>도구</th>
                <th style={{ width: 110 }}>확인</th>
                {/* **버튼 둘이 한 줄에 들어갈 폭을 준다.** 150 이었을 때 표
                    화면에서 「연결 확인」과 「지우기」가 세로로 접혔다
                    (2026-08-18 PM · 좁은 화면의 쌓기와 구분이 안 된다). */}
                <th style={{ width: 210 }} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.mcp_server_id}>
                  <td>{row.team_name ?? row.team_id}</td>
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
                      {/* `data-button` — 운영자 표는 안에 든 버튼의 테두리를
                          벗겨 글씨처럼 만든다(`OpsUi.module.css`). 여기는
                          버튼으로 보여야 해서 빠져나간다. */}
                      <Button
                        size="sm"
                        variant="outline"
                        data-button
                        disabled={busy}
                        onClick={() => test(row.mcp_server_id, row.team_id, row.name)}
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
    </div>
  );
}
