import { useCallback, useEffect, useState } from 'react';
import { Badge, OpsDataTable, OpsEmpty, OpsSectionCard } from '../../components';
import type { BadgeTone } from '../../components';
import { fetchOpsModels, fetchOpsTeamDefaultModel } from '../../api/opsModels';
import type { OpsModel, OpsTeamDefaultModel } from '../../api/opsModels';
import { fetchOpsMcpServers } from '../../api/opsMcp';
import type { OpsMcpServer } from '../../api/opsMcp';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 이 팀이 **쓰고 있는 것** — 모델과 커스텀 도구.
 *
 * **읽기만 한다**(2026-08-18 PM). 등록은 각자의 페이지에 그대로 있다
 * (`/ops/models`·`/ops/mcp`) — 등록은 「무엇을 새로 붙이나」라 주제로 시작하는
 * 일이고, 여기는 「이 팀이 지금 무엇을 들고 있나」다. 둘은 다른 질문이다.
 *
 * 팀 상세의 나머지(에이전트·최근 실행)와 성격이 같다 — **「에이전트가 이상해요」에
 * 답하는 자리**라, 문의가 왔을 때 이 팀이 무엇으로 도는지 한 화면에서 보인다.
 * 그 답을 하려고 페이지 둘을 열어 팀을 골라 가며 찾을 이유가 없다.
 */

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<OpsMcpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  // 등록만 하고 아직 도구를 못 읽은 상태. 실패와 다르다.
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

export function TeamUsageSections({ teamId }: { teamId: string }) {
  const [models, setModels] = useState<OpsModel[]>([]);
  const [servers, setServers] = useState<OpsMcpServer[]>([]);
  const [defaultModel, setDefaultModel] = useState<OpsTeamDefaultModel | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session) return;
    try {
      const [modelRows, serverRows, current] = await Promise.all([
        fetchOpsModels(session.token),
        fetchOpsMcpServers(session.token),
        fetchOpsTeamDefaultModel(session.token, teamId),
      ]);
      // 두 목록 API 는 전 팀을 준다. 여기서는 이 팀 것만 본다.
      setModels(modelRows.filter((row) => row.team_id === teamId));
      setServers(serverRows.filter((row) => row.team_id === teamId));
      setDefaultModel(current);
    } catch {
      // 팀 상세의 본체(에이전트·실행 기록)는 이미 떠 있다. 곁다리가 안 왔다고
      // 화면 전체를 오류로 덮지 않는다 — 여기서만 말한다.
      setError('이 팀이 쓰는 모델·도구를 불러오지 못했습니다.');
    }
  }, [teamId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <OpsSectionCard
        title={`쓰는 모델 ${models.length}건`}
        subtitle="등록과 기본 모델 변경은 「모델 등록」에서 합니다."
      >
        {error && <p className={styles.inlineEmpty} role="alert">{error}</p>}

        {/* 기본 모델을 목록보다 먼저 보여준다. 「이 팀이 무엇으로 도나」가
            문의를 받았을 때 가장 먼저 필요한 값이다. */}
        {defaultModel !== null &&
          (defaultModel.agent_name === null ? (
            /* 정문이 없는 것은 **빈 상태가 맞다** — 아직 아무것도 없다. */
            <p className={styles.inlineEmpty}>
              기본 에이전트가 아직 없습니다. 팀이 처음 대화를 시작하면 만들어집니다.
            </p>
          ) : (
            <p className={styles.usageFact}>
              기본 채팅은 <strong>{defaultModel.agent_name}</strong> 이{' '}
              <strong>{defaultModel.model ?? '아직 고르지 않은 모델'}</strong> 로 돕니다.
            </p>
          ))}

        {models.length === 0 ? (
          <OpsEmpty message="이 팀에 등록한 모델이 없습니다. 기본 제공 모델만 씁니다." />
        ) : (
          <OpsDataTable minWidth={700}>
            <thead>
              <tr>
                <th style={{ width: 210 }}>모델</th>
                <th style={{ width: 130 }}>제공자</th>
                <th>주소</th>
                <th style={{ width: 100 }}>등록일</th>
              </tr>
            </thead>
            <tbody>
              {models.map((row) => (
                <tr key={row.conn_id}>
                  <td>{row.model}</td>
                  <td>{row.label}</td>
                  <td className={styles.cellEllipsis} title={row.base_url}>
                    {row.base_url}
                  </td>
                  <td>{row.connected_at.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>

      <OpsSectionCard
        title={`쓰는 커스텀 도구 ${servers.length}건`}
        subtitle="등록과 연결 확인은 「커스텀 도구」에서 합니다."
      >
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
    </>
  );
}
