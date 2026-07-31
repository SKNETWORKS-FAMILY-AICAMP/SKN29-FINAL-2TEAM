import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  OpsPageHeader,
  OpsStatusBadge,
  OpsSummaryCard,
  OpsSummaryGrid,
} from '../../components';
import type { OpsTone } from '../../components';
import { fetchOverview } from '../../api/opsOverview';
import type { OpsOverview } from '../../api/opsOverview';
import { ApiError } from '../../api/client';
import { actionLabel } from '../../utils/auditActions';
import { loadOpsSession } from '../../utils/opsSession';
import { pct } from '../../utils/percent';
import { timeAgo } from '../../utils/relativeTime';
import styles from '../OpsShared/OpsPages.module.css';

interface ActionItem {
  tone: OpsTone;
  badge: string;
  title: string;
  to: string;
  actionLabel: string;
}

function actorLabel(activity: OpsOverview['recent_activity'][number]) {
  return activity.actor_display_name ?? activity.actor_email ?? '시스템';
}

function buildActionItems(data: OpsOverview): ActionItem[] {
  const items: ActionItem[] = [];

  if (data.accounts.needs_review > 0) {
    items.push({
      tone: 'danger',
      badge: '확인',
      title: `확인 필요 계정 ${data.accounts.needs_review}건`,
      to: '/ops/accounts',
      actionLabel: '계정 보기',
    });
  }

  const connectorIssues = data.connectors.expired + data.connectors.error;
  if (connectorIssues > 0) {
    items.push({
      tone: 'warning',
      badge: '확인',
      title: `연결 서비스 확인 필요 ${connectorIssues}건`,
      to: '/ops/connectors',
      actionLabel: '연결 보기',
    });
  }

  if (data.invites.expiring_today > 0) {
    items.push({
      tone: 'info',
      badge: '예정',
      title: `오늘 만료 예정 초대 ${data.invites.expiring_today}건`,
      to: '/ops/mappings',
      actionLabel: '초대 보기',
    });
  }

  return items;
}

export default function OpsOverviewPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OpsOverview | null>(null);
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
      setData(await fetchOverview(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '운영 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !data) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="운영 현황" description="플랫폼에 연결된 범위와 운영상 확인이 필요한 항목을 한눈에 확인합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="운영 현황" description="플랫폼에 연결된 범위와 운영상 확인이 필요한 항목을 한눈에 확인합니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  if (!data) return null;

  const actionItems = buildActionItems(data);
  const accountOkRatio = pct(data.accounts.total - data.accounts.needs_review, data.accounts.total);
  const accountReviewRatio = pct(data.accounts.needs_review, data.accounts.total);

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="운영 현황"
        description="플랫폼에 연결된 범위와 운영상 확인이 필요한 항목을 한눈에 확인합니다."
      />

      <OpsSummaryGrid>
        <OpsSummaryCard
          label="사용 중인 팀"
          value={data.team_count}
          detail="플랫폼을 쓰는 단위"
          onClick={() => navigate('/ops/teams')}
        />
        <OpsSummaryCard
          label="전체 계정"
          value={data.accounts.total}
          detail={`정상 ${data.accounts.total - data.accounts.needs_review} · 확인 필요 ${data.accounts.needs_review}`}
          tone={data.accounts.needs_review > 0 ? 'danger' : 'success'}
          onClick={() => navigate('/ops/accounts')}
        />
        <OpsSummaryCard
          label="연결 확인 필요"
          value={data.connectors.expired + data.connectors.error}
          detail={`확인 필요 ${data.connectors.expired} · 오류 ${data.connectors.error}`}
          tone={data.connectors.expired + data.connectors.error > 0 ? 'warning' : 'success'}
          onClick={() => navigate('/ops/connectors')}
        />
        <OpsSummaryCard
          label="수락 대기 초대"
          value={data.invites.pending}
          detail={`오늘 만료 예정 ${data.invites.expiring_today}개`}
          tone={data.invites.expiring_today > 0 ? 'info' : 'success'}
          onClick={() => navigate('/ops/mappings')}
        />
      </OpsSummaryGrid>

      <div className={styles.overviewVisuals}>
        <section className={styles.panel}>
          <h2>계정 운영 상태</h2>
          <div className={styles.largeValue}>
            <strong>{data.accounts.total}</strong>
            <span>전체 계정</span>
          </div>
          {data.accounts.total > 0 ? (
            <>
              <div
                className={styles.stackedBar}
                aria-label={`정상 계정 ${data.accounts.total - data.accounts.needs_review}개, 확인 필요 계정 ${data.accounts.needs_review}개`}
              >
                <span className={styles.barSuccess} style={{ width: `${accountOkRatio}%` }} />
                <span className={styles.barDanger} style={{ width: `${accountReviewRatio}%` }} />
              </div>
              <div className={styles.legend}>
                <button type="button" className={styles.statusLink} onClick={() => navigate('/ops/accounts?status=정상')}>
                  <span className={styles.successText}>● 정상 {data.accounts.total - data.accounts.needs_review}개</span>
                </button>
                <button type="button" className={styles.statusLink} onClick={() => navigate('/ops/accounts?status=확인 필요')}>
                  <span className={styles.dangerText}>● 확인 필요 {data.accounts.needs_review}개</span>
                </button>
              </div>
              <p className={styles.panelSubtitle}>상태를 누르면 계정 관리의 해당 목록으로 이동합니다.</p>
            </>
          ) : (
            <p className={styles.inlineEmpty}>등록된 계정이 없습니다.</p>
          )}
        </section>

        <section className={styles.panel}>
          <h2>연결 서비스 상태</h2>
          <p className={styles.panelSubtitle}>플랫폼 연결 {data.connectors.total}개의 최근 확인 결과</p>
          {data.connectors.total > 0 ? (
            <div className={styles.barRows}>
              {(
                [
                  ['연결됨', data.connectors.connected, styles.barSuccess, styles.successText],
                  ['확인 필요', data.connectors.expired, styles.barWarning, styles.warningText],
                  ['오류', data.connectors.error, styles.barDanger, styles.dangerText],
                ] as const
              ).map(([label, count, barClass, textClass]) => (
                <button
                  type="button"
                  className={[styles.barRow, styles.barRowButton].join(' ')}
                  key={label}
                  onClick={() => navigate(`/ops/connectors?status=${encodeURIComponent(label)}`)}
                >
                  <span>{label}</span>
                  <div className={styles.barTrack}>
                    <span className={barClass} style={{ width: `${pct(count, data.connectors.total)}%` }} />
                  </div>
                  <strong className={textClass}>{count}</strong>
                </button>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>연결된 서비스가 없습니다.</p>
          )}
        </section>
      </div>

      <div className={styles.overviewBottom}>
        <section className={styles.panel}>
          <h2>오늘 확인할 일 · {actionItems.length}건</h2>
          <p className={styles.panelSubtitle}>관련 화면에서 원인과 현재 상태를 확인하세요.</p>
          {actionItems.length > 0 ? (
            <div className={styles.actionList}>
              {actionItems.map((item) => (
                <div key={item.title} className={[styles.actionItem, styles[`action_${item.tone}`]].join(' ')}>
                  <OpsStatusBadge tone={item.tone}>{item.badge}</OpsStatusBadge>
                  <div className={styles.actionCopy}>
                    <strong>{item.title}</strong>
                  </div>
                  <button type="button" className={styles.outlineAction} onClick={() => navigate(item.to)}>
                    {item.actionLabel}
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>확인이 필요한 항목이 없습니다.</p>
          )}
        </section>

        <section className={styles.panel}>
          <h2>최근 운영 활동</h2>
          {data.recent_activity.length > 0 ? (
            <div className={styles.activityList}>
              {data.recent_activity.map((activity) => (
                <div className={styles.activityItem} key={activity.audit_id}>
                  <span className={styles.activityDot} />
                  <strong>{actorLabel(activity)} · {actionLabel(activity.action)}</strong>
                  <span>{timeAgo(activity.occurred_at)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className={styles.inlineEmpty}>최근 운영 활동이 없습니다.</p>
          )}
          <button type="button" className={styles.linkAction} onClick={() => navigate('/ops/audit?view=operations')}>
            감사 로그에서 전체 보기 →
          </button>
        </section>
      </div>
    </div>
  );
}
