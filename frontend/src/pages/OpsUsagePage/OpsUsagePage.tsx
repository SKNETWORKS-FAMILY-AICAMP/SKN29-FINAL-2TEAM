import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  OpsDataTable,
  OpsEmpty,
  OpsPageHeader,
  OpsSectionCard,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import type { OpsTone } from '../../components';
import { fetchUsage } from '../../api/opsUsage';
import type { OpsUsage } from '../../api/opsUsage';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { pct } from '../../utils/percent';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 사용 현황 — **얼마나 쓰고 있고, 얼마나 잘 되고 있나.**
 *
 * 감사 로그(`/ops/audit`)와 성격이 다르다. 그쪽은 「누가 무엇을 했나」(사람의
 * 조치)이고 여기는 「시스템이 얼마나 돌았나」(실행의 집계)다. 한 화면에 섞으면
 * 둘 다 흐려진다.
 *
 * **기간은 30일 고정이다.** 고르게 하면 「지금 얼마나 쓰나」라는 물음의 답이
 * 「무엇을 골랐느냐에 따라 다르다」가 된다. 필요해지면 그때 넓힌다.
 *
 * **실행 하나를 따라가는 화면은 여기가 아니다.** 그 층은 Langfuse 로 보낸다
 * (`services/agent_runtime/tracing/callbacks.py`) — watsonx Orchestrate 도
 * 같은 구성이고, 표준 규격으로 뱉어 기성 도구에 꽂는 것이 업계 관행이다.
 */

/** 성공률에 색을 입힌다. 숫자만 있으면 훑을 때 어디를 봐야 할지 안 보인다. */
function rateTone(value: number): OpsTone {
  if (value >= 90) return 'success';
  if (value >= 70) return 'warning';
  return 'danger';
}

function rate(part: number, total: number): string {
  return total > 0 ? `${pct(part, total).toFixed(0)}%` : '-';
}

/** 토큰은 자릿수가 커서 그냥 찍으면 표에서 읽히지 않는다. */
function num(value: number): string {
  return value.toLocaleString('ko-KR');
}

export default function OpsUsagePage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OpsUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setData(await fetchUsage(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '사용 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const header = <OpsPageHeader title="사용 현황" />;

  if (loading && !data) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={styles.page}>
        {header}
        <p className={styles.inlineEmpty}>{error || '사용 현황을 불러오지 못했습니다.'}</p>
      </div>
    );
  }

  const { runs, tools, guardrail } = data;
  const runRate = pct(runs.runs_done, runs.runs);
  const toolRate = pct(tools.calls_ok, tools.calls);

  return (
    <div className={styles.page}>
      {header}

      <p className={styles.resultSummary}>최근 {data.window_days}일</p>

      <OpsSummaryGrid>
        <OpsSummaryCard
          label="실행"
          value={num(runs.runs)}
          detail={runs.runs_failed > 0 ? `실패 ${num(runs.runs_failed)}건` : '실패 없음'}
          tone={runs.runs_failed > 0 ? 'warning' : 'success'}
        />
        <OpsSummaryCard
          label="실행 성공률"
          value={rate(runs.runs_done, runs.runs)}
          detail={`${num(runs.runs_done)} / ${num(runs.runs)}건`}
          tone={rateTone(runRate)}
        />
        <OpsSummaryCard
          label="도구 호출 성공률"
          value={rate(tools.calls_ok, tools.calls)}
          detail={`${num(tools.calls_ok)} / ${num(tools.calls)}회`}
          tone={rateTone(toolRate)}
        />
        <OpsSummaryCard
          label="가드레일 발동"
          value={num(guardrail.events)}
          detail={`차단 ${num(guardrail.blocked)}건`}
          tone={guardrail.blocked > 0 ? 'warning' : 'neutral'}
        />
      </OpsSummaryGrid>

      {/* **못 잰 실행을 숨기지 않는다.** 토큰 합계만 보이면 「적게 썼다」와
          「못 쟀다」가 같은 모양이 된다 — 2026-08-21 이전 새 엔진 실행은 전부
          NULL 이었고, 커스텀 엔드포인트는 지금도 제공자가 usage 를 안 주면
          NULL 로 남는다. */}
      {runs.runs_without_tokens > 0 && (
        <p className={styles.inlineEmpty}>
          이 중 {num(runs.runs_without_tokens)}건은 토큰을 재지 못했습니다. 아래 합계에서 빠져 있습니다.
        </p>
      )}

      <OpsSectionCard title="팀별">
        {data.by_team.length === 0 ? (
          <OpsEmpty message="이 기간에 실행이 없습니다." />
        ) : (
          <OpsDataTable minWidth={760}>
            <thead>
              <tr>
                <th>팀</th>
                <th style={{ width: 90 }}>실행</th>
                <th style={{ width: 110 }}>성공률</th>
                <th style={{ width: 130 }}>입력 토큰</th>
                <th style={{ width: 130 }}>출력 토큰</th>
              </tr>
            </thead>
            <tbody>
              {data.by_team.map((row) => (
                <tr key={row.team_id ?? 'unknown'}>
                  {/* 팀을 못 찾는 실행이 있다 — 지워진 에이전트의 옛 기록이다.
                      빼지 않고 「알 수 없음」으로 남긴다(합계가 안 맞으면 더 헷갈린다). */}
                  <td>{row.team_name ?? '알 수 없음'}</td>
                  <td>{num(row.runs)}</td>
                  <td>{rate(row.runs_done, row.runs)}</td>
                  <td>{num(row.token_in)}</td>
                  <td>{num(row.token_out)}</td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>

      <OpsSectionCard title="모델별">
        {data.by_model.length === 0 ? (
          <OpsEmpty message="이 기간에 실행이 없습니다." />
        ) : (
          <OpsDataTable minWidth={760}>
            <thead>
              <tr>
                <th>모델</th>
                <th style={{ width: 150 }}>연결</th>
                <th style={{ width: 90 }}>실행</th>
                <th style={{ width: 130 }}>입력 토큰</th>
                <th style={{ width: 130 }}>출력 토큰</th>
              </tr>
            </thead>
            <tbody>
              {data.by_model.map((row) => (
                <tr key={`${row.model}-${row.resolved_provider ?? ''}`}>
                  <td>{row.model}</td>
                  {/* 레거시 harness 실행은 이 값을 안 남겼다. 「-」가 정직하다. */}
                  <td>{row.resolved_provider ?? '-'}</td>
                  <td>{num(row.runs)}</td>
                  <td>{num(row.token_in)}</td>
                  <td>{num(row.token_out)}</td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>

      <OpsSectionCard title="도구별">
        {data.by_tool.length === 0 ? (
          <OpsEmpty message="이 기간에 도구 호출이 없습니다." />
        ) : (
          <OpsDataTable minWidth={760}>
            <thead>
              <tr>
                <th>도구</th>
                <th style={{ width: 90 }}>호출</th>
                <th style={{ width: 110 }}>성공률</th>
                <th style={{ width: 110 }}>평균 소요</th>
                <th style={{ width: 120 }}>안 닫힌 호출</th>
              </tr>
            </thead>
            <tbody>
              {data.by_tool.map((row) => (
                <tr key={row.tool_ref}>
                  <td>{row.tool_ref}</td>
                  <td>{num(row.calls)}</td>
                  <td>{rate(row.calls_ok, row.calls)}</td>
                  <td>{row.avg_ms === null ? '-' : `${num(row.avg_ms)}ms`}</td>
                  {/* PENDING 은 성공도 실패도 아니다. 0 이 아니면 스트림이 중간에
                      끊긴 것이라 배선을 봐야 한다 — 성공률에 섞으면 안 보인다. */}
                  <td>{row.calls_pending > 0 ? num(row.calls_pending) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>
    </div>
  );
}
