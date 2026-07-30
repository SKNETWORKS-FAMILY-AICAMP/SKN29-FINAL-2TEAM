import { useMemo, useState } from 'react';
import {
  OpsPageHeader,
  OpsSearchField,
  OpsStatusBadge,
} from '../../components';
import { OPS_ORGANIZATIONS } from '../../data/opsMockData';
import styles from '../OpsShared/OpsPages.module.css';

function organizationDepth(parentId: string | null) {
  if (!parentId) return 0;
  return parentId === 'ORG-001' ? 1 : 2;
}

export default function OpsOrganizationsPage() {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState('ORG-010');

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return OPS_ORGANIZATIONS;
    return OPS_ORGANIZATIONS.filter((item) =>
      [item.id, item.name, item.managerId ?? ''].some((value) => value.toLowerCase().includes(normalized)),
    );
  }, [query]);

  const selected = filtered.find((item) => item.id === selectedId) ?? filtered[0] ?? null;
  const children = selected ? OPS_ORGANIZATIONS.filter((item) => item.parentId === selected.id) : [];

  return (
    <div className={styles.page}>
      <OpsPageHeader
        title="연결 조직 현황"
        description="People DB에 적재된 조직 계층과 그 안의 팀·구성원 상태를 확인합니다."
      />
      <div className={styles.notice}>
        운영자는 플랫폼에 적재된 조직 전체를 조회합니다. 미연결 고객사의 원본 조직도는 포함하지 않습니다.
      </div>
      <OpsSearchField value={query} onChange={setQuery} placeholder="연결 조직·계정 검색" />

      <div className={styles.twoColumns} style={{ marginTop: 16 }}>
        <section className={styles.panel}>
          <h2>플랫폼 연결 조직</h2>
          <p className={styles.panelSubtitle}>조직 {OPS_ORGANIZATIONS.length} · 연결 구성원 26 · 확인 필요 1</p>
          <div className={styles.treeList}>
            {filtered.length > 0 ? filtered.map((item) => {
              const depth = organizationDepth(item.parentId);
              return (
                <button
                  key={item.id}
                  type="button"
                  className={[
                    styles.treeButton,
                    depth === 1 ? styles.treeIndent1 : '',
                    depth === 2 ? styles.treeIndent2 : '',
                    selected?.id === item.id ? styles.treeButtonActive : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => setSelectedId(item.id)}
                >
                  {item.name}
                  <span className={styles.treeMeta}>
                    구성원 {item.memberCount} · {item.issueCount ? `확인 필요 ${item.issueCount}` : '최근 확인 정상'}
                  </span>
                </button>
              );
            }) : <div className={styles.inlineEmpty}>조건에 맞는 연결 조직이 없습니다.</div>}
          </div>
        </section>

        {selected ? <section className={styles.panel}>
          <div className={styles.detailTitleRow}>
            <div>
              <h2>{selected.name}</h2>
              <p className={styles.panelSubtitle}>플랫폼 연결 범위 · 하위 조직 {children.length}개</p>
            </div>
            <OpsStatusBadge tone={selected.issueCount ? 'warning' : 'success'}>
              {selected.issueCount ? `확인 필요 ${selected.issueCount}` : '최근 확인 정상'}
            </OpsStatusBadge>
          </div>

          <div className={styles.detailGrid}>
            <div className={styles.infoCard}><span>조직 ID</span><strong>{selected.id}</strong></div>
            <div className={styles.infoCard}><span>상위 조직 ID</span><strong>{selected.parentId ?? '없음'}</strong></div>
            <div className={styles.infoCard}><span>관리자 ID</span><strong>{selected.managerId ?? '미지정'}</strong></div>
            <div className={styles.infoCard}><span>조직 유형</span><strong>{selected.type}</strong></div>
          </div>

          <h3>연결된 하위 조직</h3>
          <div className={styles.teamList}>
            {children.length > 0 ? children.map((item) => (
              <button type="button" className={styles.teamItem} key={item.id} onClick={() => setSelectedId(item.id)}>
                <strong>{item.name}</strong>
                <span>연결 구성원 {item.memberCount}명</span>
                <OpsStatusBadge tone={item.issueCount ? 'warning' : 'success'}>
                  {item.issueCount ? `매핑 확인 ${item.issueCount}건` : '최근 확인 정상'}
                </OpsStatusBadge>
              </button>
            )) : <p className={styles.detailText}>연결된 하위 조직이 없습니다.</p>}
          </div>
        </section> : (
          <section className={styles.panel}>
            <div className={styles.inlineEmpty}>검색 조건을 변경하면 조직 상세를 확인할 수 있습니다.</div>
          </section>
        )}
      </div>
    </div>
  );
}
