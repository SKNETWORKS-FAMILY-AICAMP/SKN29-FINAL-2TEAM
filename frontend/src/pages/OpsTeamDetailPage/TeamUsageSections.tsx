import { useCallback, useEffect, useState } from 'react';
import { Badge, OpsDataTable, OpsEmpty, OpsSectionCard } from '../../components';
import type { BadgeTone } from '../../components';
import { fetchOpsTeamDefaultModel, saveOpsTeamDefaultModel } from '../../api/opsModels';
import type { OpsTeamDefaultModel } from '../../api/opsModels';
import { fetchOpsMcpServers } from '../../api/opsMcp';
import type { OpsMcpServer } from '../../api/opsMcp';
import { fetchOpsGuardrails, setTeamActiveGuardrail } from '../../api/opsGuardrails';
import type { GuardrailKind, OpsGuardrailProvider } from '../../api/opsGuardrails';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 이 팀이 **사용 중인 것** — 모델, 커스텀 도구, 가드레일.
 *
 * 모델과 가드레일은 **고를 수 있고**(이 팀이 무엇으로 도나), 커스텀 도구는
 * **보여만 준다**. 등록은 각자의 페이지다(`/ops/models`·`/ops/mcp`·
 * `/ops/guardrails`) — 등록은 「무엇을 새로 붙이나」라 주제로 시작하는 일이고,
 * 여기는 「이 팀이 지금 무엇을 쓰나」다.
 *
 * **가드레일을 고르는 자리가 여기인 이유**(2026-08-20 PM 지적): 등록 목록은 전
 * 팀의 등록물이라 거기서 켜면 「어느 팀의 무엇을 켜는가」가 흐려진다. 모델이 이미
 * 같은 길을 갔다 — 등록은 `/ops/models`, 고르는 것은 여기다.
 *
 * 팀 상세의 나머지(에이전트·최근 실행)와 성격이 같다 — **「에이전트가 이상해요」에
 * 답하는 자리**라, 문의가 왔을 때 이 팀이 무엇으로 도는지 한 화면에서 보인다.
 */

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<OpsMcpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  // 등록만 하고 아직 도구를 못 읽은 상태. 실패와 다르다.
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

const GUARDRAIL_KIND_LABELS: Record<GuardrailKind, string> = {
  OPENAI_GUARDRAILS: 'OpenAI Guardrails',
  BEDROCK_GUARDRAILS: 'AWS Bedrock Guardrails',
  AZURE_CONTENT_SAFETY: 'Azure Content Safety',
};

export function TeamUsageSections({ teamId }: { teamId: string }) {
  const [servers, setServers] = useState<OpsMcpServer[]>([]);
  const [guardrails, setGuardrails] = useState<OpsGuardrailProvider[]>([]);
  const [defaultModel, setDefaultModel] = useState<OpsTeamDefaultModel | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session) return;
    try {
      const [serverRows, guardrailRows, current] = await Promise.all([
        fetchOpsMcpServers(session.token),
        fetchOpsGuardrails(session.token),
        fetchOpsTeamDefaultModel(session.token, teamId),
      ]);
      // 목록 API 는 전 팀을 준다. 여기서는 이 팀 것만 본다.
      setServers(serverRows.filter((row) => row.team_id === teamId));
      setGuardrails(guardrailRows.filter((row) => row.team_id === teamId));
      setDefaultModel(current);
    } catch {
      // 팀 상세의 본체(에이전트·실행 기록)는 이미 떠 있다. 곁다리가 안 왔다고
      // 화면 전체를 오류로 덮지 않는다 — 여기서만 말한다.
      setError('이 팀이 사용 중인 모델·도구·가드레일을 불러오지 못했습니다.');
    }
  }, [teamId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function chooseGuardrail(next: string) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await setTeamActiveGuardrail(session.token, teamId, next || null);
      await load();
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function saveDefault(next: string) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const saved = await saveOpsTeamDefaultModel(session.token, teamId, next);
      setDefaultModel((prev) => (prev ? { ...prev, model: saved.model } : prev));
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <OpsSectionCard title="사용 중 모델">
        {error && <p className={styles.inlineEmpty} role="alert">{error}</p>}

        {defaultModel === null ? (
          <p className={styles.inlineEmpty}>불러오는 중…</p>
        ) : defaultModel.agent_name === null ? (
          /* 정문이 없으면 「없다」고 말한다. 임의의 기본값을 저장된 것처럼
             보여주면 안 된다 — 팀 화면에서 지켜 온 규칙 그대로다. */
          <p className={styles.inlineEmpty}>
            이 팀에는 아직 기본 에이전트가 없습니다. 팀이 처음 대화를 시작하면 만들어집니다.
          </p>
        ) : (
          <div className={styles.formGrid}>
            <div className={styles.fieldGroup}>
              <label htmlFor="team-default-model">{defaultModel.agent_name}</label>
              {/* 이름을 외워 적게 하지 않는다 — 오타는 실행 시점 404 가 되고,
                  그때 죽는 것은 우리가 아니라 이 팀의 대화다. */}
              <select
                id="team-default-model"
                value={defaultModel.model ?? ''}
                disabled={busy}
                onChange={(event) => saveDefault(event.target.value)}
              >
                {defaultModel.model === null && <option value="">고르세요</option>}
                {defaultModel.choices.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </OpsSectionCard>

      <OpsSectionCard title="사용 중 커스텀 도구">
        {servers.length === 0 ? (
          <OpsEmpty message="이 팀에 붙어 있는 서버가 없습니다." />
        ) : (
          <OpsDataTable minWidth={760}>
            <thead>
              <tr>
                <th style={{ width: 150 }}>이름</th>
                <th>주소</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 70 }}>도구</th>
                <th style={{ width: 110 }}>확인</th>
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
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>

      <OpsSectionCard title="사용 중 가드레일">
        {guardrails.length === 0 ? (
          <OpsEmpty message="이 팀에 등록된 가드레일이 없습니다." />
        ) : (
          <>
            <div className={styles.formGrid}>
              <div className={styles.fieldGroup}>
                <label htmlFor="team-guardrail">이 팀 대화가 거쳐 갈 가드레일</label>
                {/* 연결 확인을 통과하지 않은 것은 고를 수 없다 — 고르게 두면 그
                    팀의 대화가 매번 실패하는 검사를 거치고, 화면만 「사용 중」
                    이라고 말한다. 서버도 같은 이유로 막는다. */}
                <select
                  id="team-guardrail"
                  value={guardrails.find((row) => row.is_active)?.provider_id ?? ''}
                  disabled={busy}
                  onChange={(event) => chooseGuardrail(event.target.value)}
                >
                  {/* 등록을 지우지 않고 검사만 끄는 자리 */}
                  <option value="">사용 안 함</option>
                  {guardrails.map((row) => (
                    <option
                      key={row.provider_id}
                      value={row.provider_id}
                      disabled={row.status !== 'CONNECTED'}
                    >
                      {row.name} ({GUARDRAIL_KIND_LABELS[row.kind] ?? row.kind})
                      {row.status !== 'CONNECTED' ? ' — 연결 확인 필요' : ''}
                    </option>
                  ))}
                </select>
              </div>
            </div>

          <OpsDataTable minWidth={760}>
            <thead>
              <tr>
                <th style={{ width: 180 }}>이름</th>
                <th style={{ width: 200 }}>종류</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 80 }}>사용</th>
                <th style={{ width: 110 }}>확인</th>
              </tr>
            </thead>
            <tbody>
              {guardrails.map((row) => (
                <tr key={row.provider_id}>
                  <td>{row.name}</td>
                  <td>{GUARDRAIL_KIND_LABELS[row.kind] ?? row.kind}</td>
                  <td>
                    <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                  </td>
                  <td>
                    {/* 등록만 해 둔 것과 실제로 거쳐 가는 것을 가른다 — 「이 팀
                        대화가 무엇을 거치나」가 이 카드의 질문이다. */}
                    {row.is_active ? <Badge tone="success">사용 중</Badge> : '—'}
                  </td>
                  <td>{row.last_checked_at ? row.last_checked_at.slice(0, 10) : '없음'}</td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
          </>
        )}
      </OpsSectionCard>
    </>
  );
}
