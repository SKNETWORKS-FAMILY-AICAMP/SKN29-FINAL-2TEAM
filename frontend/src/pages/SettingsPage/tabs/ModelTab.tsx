import { useCallback, useEffect, useState } from 'react';
import { Badge, Icon, InfoNote, useToast } from '../../../components';
import { ApiError } from '../../../api/client';
import { fetchMainModel, listCustomModels, saveMainModel } from '../../../api/agents';
import type { CustomModel } from '../../../api/agents';
import { MODEL_OPTIONS } from '../../../data/models';
import { useSession } from '../../../utils/session';
import styles from './tabs.module.css';

/**
 * 메인 모델 — 오케스트레이션하는 정문 에이전트가 쓰는 모델.
 *
 * **여기서 고른 것이 실제로 저장된다.** 예전에는 라디오가 `useState` 뿐이라 눌러도
 * 아무 일이 없었고, 목록에는 계정에 없는 모델(`gpt-5-mini`)이 「쿼터 제한」이라는
 * 지어낸 상태로 있었으며 「평균 응답 2.4초」 같은 근거 없는 수치가 붙어 있었다
 * (2026-08-12 확인). 전부 걷어냈다.
 *
 * 목록은 **키가 가진 것을 그대로 뿌리지 않는다.** 실제로 불러 보면 OpenAI 키가
 * `whisper-1`·`tts-1`·`sora-2` 까지 100 개 넘게 돌려준다 — 고를 수 없는 목록이
 * 된다. 우리가 제공하는 것은 **호출 방식까지 확인한 것**만 올린다. 그 밖의 모델은
 * 팀이 요청하면 운영자가 등록한다(`/ops/models`) — 여기서는 등록된 것을 보기만 한다.
 */
export function ModelTab() {
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [current, setCurrent] = useState<string | null>(null);
  const [customs, setCustoms] = useState<CustomModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const reloadCustoms = useCallback(async () => {
    if (!token) return;
    try {
      setCustoms(await listCustomModels(token));
    } catch {
      setCustoms([]);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchMainModel(token)
      .then((row) => {
        setCurrent(row.model);
      })
      .catch(() => setCurrent(null))
      .finally(() => setLoading(false));
    void reloadCustoms();
  }, [token, reloadCustoms]);

  async function choose(value: string) {
    if (!token || saving || value === current) return;
    setSaving(value);
    try {
      const row = await saveMainModel(token, value);
      setCurrent(row.model);
      showToast('모델을 바꿨습니다.', 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '모델을 바꾸지 못했습니다.', 'error');
    } finally {
      setSaving(null);
    }
  }

  /** 고를 수 있는 전부 — 우리가 제공하는 것 + 팀이 등록한 것. */
  const rows = [
    ...MODEL_OPTIONS.map((model) => ({
      value: model.value,
      label: model.label,
      tier: model.tier as string,
      source: '기본 제공',
    })),
    ...customs.map((row) => ({
      value: row.model,
      label: row.model,
      // 커스텀은 속도를 알 수 없다. **모르는 것을 지어내지 않는다** — 제공자
      // 이름을 속도 칸에 넣어 「Google Gemini」가 속도로 보였다(2026-08-12).
      tier: '',
      source: row.label,
    })),
  ];

  return (
    <div className={styles.tab}>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>
            모델
            <InfoNote title="모델">
              <p>
                대화를 받아 <strong>어떤 도구를 쓸지 정하고 필요하면 팀 에이전트에게 넘기는</strong>{' '}
                에이전트가 쓰는 모델입니다.
              </p>
              <p>
                <strong>개별 에이전트는 자기 모델을 따로 가집니다.</strong> 에이전트를 만들 때 고르며,
                이 값은 거기에 영향을 주지 않습니다.
              </p>
              <p>
                업무 추출처럼 단계가 여러 개인 도구는 <strong>부른 에이전트의 모델</strong>로 돕니다.
                다만 그 도구는 구조화 출력이 필요해 Claude 로는 못 돌고, 그때는 기본 모델로 떨어졌다고
                답에 적습니다.
              </p>
            </InfoNote>
          </h2>
        </div>

        {loading ? (
          <p className={styles.cardSub}>불러오는 중…</p>
        ) : current === null ? (
          <p className={styles.cardSub}>
            아직 기본 에이전트가 없어 쓸 모델을 정할 수 없습니다. 인사 시스템을 연결해 팀을 만들면
            생깁니다.
          </p>
        ) : (
          <div className={styles.table}>
            <div className={styles.tableHead}>
              <span style={{ width: 60 }}>사용 중</span>
              <span style={{ flex: 1 }}>모델</span>
              <span style={{ width: 120 }}>속도</span>
              <span style={{ width: 140 }}>출처</span>
            </div>
            {rows.map((row) => (
              <label key={row.value} className={styles.tableRow}>
                <span style={{ width: 60 }}>
                  <input
                    type="radio"
                    name="main-model"
                    checked={current === row.value}
                    disabled={saving !== null}
                    onChange={() => void choose(row.value)}
                  />
                </span>
                <span style={{ flex: 1 }}>{row.label}</span>
                <span style={{ width: 120 }}>{row.tier || '—'}</span>
                <span style={{ width: 140 }}>
                  <Badge tone={row.source === '기본 제공' ? 'neutral' : 'info'}>{row.source}</Badge>
                </span>
              </label>
            ))}
          </div>
        )}
      </section>

      {/* 목록 뒤에 둔다. 위 표가 「고르는 자리」이고 이건 「그 중 우리 팀에만
          등록된 것이 무엇인가」라, 고른 다음에 읽는 순서가 맞는다. */}
      <CustomModelCard rows={customs} />
    </div>
  );
}

/**
 * 이 팀에 등록된 모델 API — **읽기만 한다.**
 *
 * 예전에는 여기서 팀이 직접 등록했다. 그런데 등록하려면 OpenAI 호환 주소와 키와
 * 모델 식별자를 알아야 한다 — **「코딩 없이」를 내세운 제품이 비개발자에게 요구할
 * 일이 아니다.** 실제로 Google 호환 주소는 AI Studio 화면에 없어서 문서를 뒤져야
 * 나왔다(2026-08-13 멘토링: 회사가 요청하면 우리가 등록한다).
 *
 * 목록은 남긴다. 우리 팀이 지금 무엇으로 도는지는 팀이 알아야 하고, 그건 등록
 * 권한과 다른 이야기다. 등록하고 지우는 것은 운영자 콘솔(`/ops/models`)이 한다.
 */
function CustomModelCard({ rows }: { rows: CustomModel[] }) {
  return (
    <section className={styles.card}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>
          우리 팀에 등록된 모델
          <InfoNote title="우리 팀에 등록된 모델">
            <p>
              <strong>따로 등록한 것이 없으면 저희가 제공하는 모델로 돕니다.</strong> 대부분의 팀은
              이대로 쓰면 됩니다.
            </p>
            <p>
              회사 규정상 <strong>자기 계약으로만 데이터를 보내야 하거나</strong>, 사내에 모델을 띄운
              경우에는 그 모델을 이 팀에만 등록할 수 있습니다. 주소·키를 다루는 일이라
              <strong> 저희에게 요청하시면 저희가 등록해 드립니다.</strong>
            </p>
            <p>등록된 모델은 위 목록에 함께 나오고, 에이전트를 만들 때도 고를 수 있습니다.</p>
          </InfoNote>
        </h2>
      </div>

      {rows.length === 0 ? (
        <p className={styles.cardSub}>따로 등록한 모델이 없습니다 — 저희가 제공하는 모델로 돕니다.</p>
      ) : (
        <div className={styles.list}>
          {rows.map((row) => (
            <div key={row.conn_id} className={styles.row}>
              <span className={styles.rowIcon}>
                <Icon name="link" size={20} color="var(--color-primary)" />
              </span>
              <div className={styles.rowBody}>
                <span className={styles.rowName}>{row.model}</span>
                <span className={styles.rowVendor}>{row.label}</span>
                <span className={styles.rowDesc}>{row.base_url}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
