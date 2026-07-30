import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Icon,
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
} from '../../components';
import { fetchOrganizations } from '../../api/opsOrganizations';
import type { OpsOrganization } from '../../api/opsOrganizations';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import { pct } from '../../utils/percent';
import styles from '../OpsShared/OpsPages.module.css';

const ORG_TYPE_LABELS: Record<string, string> = {
  COMPANY: '회사',
  DEPARTMENT: '본부',
  SUPERVISORY: '팀',
  COST_CENTER: '비용 센터',
};

function orgTypeLabel(type: string) {
  return ORG_TYPE_LABELS[type] ?? type;
}

/**
 * `up_org_id` 체인을 실제로 따라 올라가며 깊이를 센다(검색 결과처럼 평면
 * 목록을 보여줄 때 씀). 순환 참조가 생겨도(FK 제약이 없는 컬럼이라 이론상
 * 가능) 방문한 조직을 기억해 무한 루프에 빠지지 않는다.
 */
function orgDepth(startId: string, byId: Map<string, OpsOrganization>): number {
  const visited = new Set<string>([startId]);
  let depth = 0;
  let currentId = byId.get(startId)?.up_org_id ?? null;

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId);
    depth += 1;
    currentId = byId.get(currentId)?.up_org_id ?? null;
  }

  return Math.min(depth, 2);
}

interface TreeRow {
  item: OpsOrganization;
  depth: number;
  hasChildren: boolean;
}

/** 접힌 조직 아래는 내려가지 않는, 깊이 우선 트리 목록을 만든다. 순환 참조 방지 포함. */
function buildTreeRows(
  roots: OpsOrganization[],
  childrenOf: Map<string, OpsOrganization[]>,
  collapsedIds: Set<string>,
): TreeRow[] {
  const rows: TreeRow[] = [];

  function visit(node: OpsOrganization, depth: number, ancestors: Set<string>) {
    if (ancestors.has(node.org_id)) return;
    const children = childrenOf.get(node.org_id) ?? [];
    rows.push({ item: node, depth: Math.min(depth, 2), hasChildren: children.length > 0 });
    if (children.length === 0 || collapsedIds.has(node.org_id)) return;

    const nextAncestors = new Set(ancestors);
    nextAncestors.add(node.org_id);
    for (const child of children) visit(child, depth + 1, nextAncestors);
  }

  for (const root of roots) visit(root, 0, new Set());
  return rows;
}

export default function OpsOrganizationsPage() {
  const navigate = useNavigate();
  const [organizations, setOrganizations] = useState<OpsOrganization[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setLoading(true);
    setError('');
    try {
      setOrganizations(await fetchOrganizations(session.token));
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '연결 조직 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const byId = useMemo(() => {
    const map = new Map<string, OpsOrganization>();
    for (const item of organizations ?? []) map.set(item.org_id, item);
    return map;
  }, [organizations]);

  const childrenOf = useMemo(() => {
    const map = new Map<string, OpsOrganization[]>();
    for (const item of organizations ?? []) {
      if (!item.up_org_id) continue;
      const siblings = map.get(item.up_org_id) ?? [];
      siblings.push(item);
      map.set(item.up_org_id, siblings);
    }
    return map;
  }, [organizations]);

  const roots = useMemo(
    () => (organizations ?? []).filter((item) => !item.up_org_id || !byId.has(item.up_org_id)),
    [organizations, byId],
  );

  const filtered = useMemo(() => {
    const all = organizations ?? [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return all;
    return all.filter((item) =>
      [item.org_id, item.name, item.mgr_id ?? ''].some((value) => value.toLowerCase().includes(normalized)),
    );
  }, [organizations, query]);

  // 검색 중에는 트리 접기/펼치기 대신 매칭된 조직을 평면 목록으로 보여준다.
  const treeRows = useMemo(
    () => (query.trim() ? null : buildTreeRows(roots, childrenOf, collapsedIds)),
    [roots, childrenOf, collapsedIds, query],
  );

  const selected = filtered.find((item) => item.org_id === selectedId) ?? filtered[0] ?? null;

  const totalMembers = (organizations ?? []).reduce((sum, item) => sum + item.member_count, 0);
  const totalIssues = (organizations ?? []).reduce((sum, item) => sum + item.issue_count, 0);

  function toggleCollapsed(orgId: string) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(orgId)) next.delete(orgId);
      else next.add(orgId);
      return next;
    });
  }

  function renderRow(item: OpsOrganization, depth: number, hasChildren: boolean) {
    return (
      <div
        key={item.org_id}
        className={[
          styles.treeRow,
          depth === 1 ? styles.treeIndent1 : '',
          depth === 2 ? styles.treeIndent2 : '',
        ].filter(Boolean).join(' ')}
      >
        {hasChildren ? (
          <button
            type="button"
            className={styles.treeToggle}
            aria-label={collapsedIds.has(item.org_id) ? `${item.name} 하위 조직 펼치기` : `${item.name} 하위 조직 접기`}
            onClick={() => toggleCollapsed(item.org_id)}
          >
            <Icon name={collapsedIds.has(item.org_id) ? 'chevron-right' : 'chevron-down'} size={14} />
          </button>
        ) : (
          <span className={styles.treeToggleSpacer} aria-hidden="true" />
        )}
        <button
          type="button"
          className={[styles.treeButton, selected?.org_id === item.org_id ? styles.treeButtonActive : '']
            .filter(Boolean).join(' ')}
          onClick={() => setSelectedId(item.org_id)}
        >
          {item.name}
          <span className={styles.treeMeta}>
            구성원 {item.total_member_count} · {item.issue_count > 0 ? `확인 필요 ${item.issue_count}` : '최근 확인 정상'}
          </span>
        </button>
      </div>
    );
  }

  if (loading && !organizations) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 조직 현황" description="People DB에 적재된 조직 계층과 그 안의 팀·구성원 상태를 확인합니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="연결 조직 현황" description="People DB에 적재된 조직 계층과 그 안의 팀·구성원 상태를 확인합니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  if ((organizations ?? []).length === 0) {
    return (
      <div className={styles.page}>
        <OpsPageHeader
          title="연결 조직 현황"
          description="People DB에 적재된 조직 계층과 그 안의 팀·구성원 상태를 확인합니다."
        />
        <div className={styles.notice}>
          운영자는 플랫폼에 적재된 조직 전체를 조회합니다. 미연결 고객사의 원본 조직도는 포함하지 않습니다.
        </div>
        <p className={styles.inlineEmpty}>연결된 조직이 없습니다.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="연결 조직 현황"
        description="People DB에 적재된 조직 계층과 그 안의 팀·구성원 상태를 확인합니다."
      />
      <div className={styles.notice}>
        운영자는 플랫폼에 적재된 조직 전체를 조회합니다. 미연결 고객사의 원본 조직도는 포함하지 않습니다.
      </div>
      <OpsSearchField value={query} onChange={setQuery} placeholder="연결 조직·관리자 ID 검색" />

      <div className={styles.twoColumns} style={{ marginTop: 16 }}>
        <section className={styles.panel}>
          <h2>플랫폼 연결 조직</h2>
          <p className={styles.panelSubtitle}>
            조직 {(organizations ?? []).length} · 연결 구성원 {totalMembers} · 확인 필요 {totalIssues}
          </p>
          <div className={styles.treeList}>
            {treeRows
              ? (treeRows.length > 0
                  ? treeRows.map(({ item, depth, hasChildren }) => renderRow(item, depth, hasChildren))
                  : <div className={styles.inlineEmpty}>조건에 맞는 연결 조직이 없습니다.</div>)
              : (filtered.length > 0
                  ? filtered.map((item) => renderRow(item, orgDepth(item.org_id, byId), false))
                  : <div className={styles.inlineEmpty}>조건에 맞는 연결 조직이 없습니다.</div>)}
          </div>
        </section>

        {selected ? <section className={styles.panel}>
          <div className={styles.detailTitleRow}>
            <div>
              <h2>{selected.name}</h2>
              <p className={styles.panelSubtitle}>{orgTypeLabel(selected.org_type)} · 전체 인원 {selected.total_member_count}명</p>
            </div>
            <OpsStatusBadge tone={selected.issue_count > 0 ? 'warning' : 'success'}>
              {selected.issue_count > 0 ? `확인 필요 ${selected.issue_count}` : '최근 확인 정상'}
            </OpsStatusBadge>
          </div>

          <div className={styles.detailGrid}>
            <div className={styles.infoCard}><span>조직 ID</span><strong>{selected.org_id}</strong></div>
            <div className={styles.infoCard}><span>상위 조직 ID</span><strong>{selected.up_org_id ?? '없음'}</strong></div>
            <div className={styles.infoCard}><span>관리자 ID</span><strong>{selected.mgr_id ?? '미지정'}</strong></div>
            <div className={styles.infoCard}><span>조직 유형</span><strong>{orgTypeLabel(selected.org_type)}</strong></div>
          </div>

          <h3>계정 연동 현황</h3>
          <div className={styles.detailCards}>
            <div className={styles.detailCard}>
              <strong>직속 인원</strong>
              <p>
                {selected.member_count}명
                {selected.total_member_count !== selected.member_count
                  ? ` (하위 조직 포함 전체 ${selected.total_member_count}명)`
                  : ''}
              </p>
            </div>
            <div className={styles.detailCard}>
              <strong>계정 연결(직속 기준)</strong>
              <p>
                {selected.member_count > 0
                  ? `${selected.mapped_count}명 / ${selected.member_count}명 (${Math.round(pct(selected.mapped_count, selected.member_count))}%)`
                  : '소속 직원이 없습니다.'}
              </p>
            </div>
            <div className={styles.detailCard}>
              <strong>확인 필요 계정</strong>
              <p>{selected.issue_count > 0 ? `${selected.issue_count}건 · 잠김 또는 중복 연결` : '없음'}</p>
            </div>
          </div>
          {selected.issue_count > 0 && (
            <div className={styles.rowActions}>
              <Button variant="outline" onClick={() => navigate('/ops/accounts')}>계정 관리에서 확인</Button>
            </div>
          )}
        </section> : (
          <section className={styles.panel}>
            <div className={styles.inlineEmpty}>검색 조건을 변경하면 조직 상세를 확인할 수 있습니다.</div>
          </section>
        )}
      </div>
    </div>
  );
}
