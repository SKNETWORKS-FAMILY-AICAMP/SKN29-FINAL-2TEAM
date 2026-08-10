import { useState } from 'react';
import { Badge, Icon } from '../../../components';
import type { BadgeTone } from '../../../components';
import styles from './tabs.module.css';

interface ModelRow {
  id: string;
  name: string;
  usage: string;
  tone: BadgeTone;
  status: string;
  latency: string;
}

/**
 * Model 탭. 사용 가능한 모델 목록과 기본값 지정까지만 — 팀별 쿼터·비용 관리는
 * 이번 범위 밖이다(2_아키텍처 §6).
 *
 * 용도 구분은 AS-IS 실측 그대로다: 검색어 생성은 luna(low), 근거 정리는
 * sol(xhigh).
 */
const MODELS: ModelRow[] = [
  { id: 'luna', name: 'gpt-5.6 luna', usage: '검색어 생성 · 짧은 판단 (low)', tone: 'success', status: '사용 가능', latency: '2.4초' },
  { id: 'sol', name: 'gpt-5.6 sol', usage: '근거 정리 · 긴 추론 (xhigh)', tone: 'success', status: '사용 가능', latency: '19.3초' },
  { id: 'mini', name: 'gpt-5-mini', usage: '가벼운 요약 · 분류', tone: 'warning', status: '쿼터 제한', latency: '4.2초' },
];

export function ModelTab() {
  const [defaultModel, setDefaultModel] = useState('luna');

  return (
    <div className={styles.tab}>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>사용 가능한 모델</h2>
          <p className={styles.cardSub}>
            에이전트를 만들 때 고를 수 있는 모델입니다. 기본값은 새 에이전트에 자동으로 적용됩니다.
          </p>
        </div>

        <div className={styles.table}>
          <div className={styles.tableHead}>
            <span style={{ width: 60 }}>기본값</span>
            <span style={{ width: 200 }}>모델</span>
            <span style={{ flex: 1 }}>권장 용도</span>
            <span style={{ width: 120 }}>상태</span>
            <span style={{ width: 90 }}>평균 응답</span>
          </div>
          {MODELS.map((model) => (
            <label key={model.id} className={styles.tableRow}>
              <span style={{ width: 60 }}>
                <input
                  type="radio"
                  name="default-model"
                  value={model.id}
                  checked={defaultModel === model.id}
                  onChange={() => setDefaultModel(model.id)}
                  style={{ margin: 0 }}
                />
              </span>
              <span style={{ width: 200, fontWeight: 600 }}>{model.name}</span>
              <span style={{ flex: 1, color: 'var(--color-muted)', fontSize: 13 }}>{model.usage}</span>
              <span style={{ width: 120 }}>
                <Badge tone={model.tone}>{model.status}</Badge>
              </span>
              <span style={{ width: 90, fontSize: 13 }}>{model.latency}</span>
            </label>
          ))}
        </div>

        <p className={`${styles.notice} ${styles.noticeNeutral}`}>
          <Icon name="info" size={15} color="var(--color-muted)" />
          <span>
            여러 단계로 도는 에이전트는 단계마다 다른 모델을 씁니다 — 업무 추출은 검색어를 luna(low)로, 근거 정리를
            sol(xhigh)로 처리합니다.
          </span>
        </p>
      </section>
    </div>
  );
}
