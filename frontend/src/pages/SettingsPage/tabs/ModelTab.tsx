import { useCallback, useEffect, useState } from 'react';
import { Badge, Button, Icon, InfoNote, Input, useToast } from '../../../components';
import { ApiError } from '../../../api/client';
import {
  addCustomModel,
  fetchMainModel,
  listCustomModels,
  probeCustomModels,
  removeCustomModel,
  saveMainModel,
} from '../../../api/agents';
import type { CustomModel } from '../../../api/agents';
import { MODEL_OPTIONS } from '../../../data/models';
import { PROVIDER_PRESETS } from '../../../data/providers';
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
 * 된다. 우리가 제공하는 것은 **호출 방식까지 확인한 것**만 올리고, 그 밖의 모델은
 * 아래 「커스텀 모델 API」로 붙인다.
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
      {/* **등록이 먼저, 목록이 그다음.** 커스텀으로 붙인 것이 아래 목록에 그대로
          섞여 들어가므로 순서가 그 인과를 따른다(2026-08-12 PM 지적). */}
      <CustomModelCard rows={customs} onChanged={reloadCustoms} />

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
    </div>
  );
}

/**
 * 커스텀 모델 API — **목록으로 관리한다.**
 *
 * 기본은 우리가 제공하는 모델이다. 다만 자기 계약으로만 데이터를 흘려야 하는 팀,
 * 사용량이 우리 플랜을 넘는 팀, 사내에 모델을 띄운 팀이 있어 **필요한 만큼 여러
 * 개** 붙일 수 있게 한다(2026-08-12 PM 결정).
 */
function CustomModelCard({
  rows,
  onChanged,
}: {
  rows: CustomModel[];
  onChanged: () => Promise<void>;
}) {
  const session = useSession();
  const token = session?.token;
  const { showToast } = useToast();

  const [preset, setPreset] = useState('');
  const [label, setLabel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [available, setAvailable] = useState<string[]>([]);
  const [probeNote, setProbeNote] = useState('');
  const [busy, setBusy] = useState(false);

  async function probe() {
    if (!token || !baseUrl.trim() || !apiKey.trim()) return;
    setBusy(true);
    try {
      const result = await probeCustomModels(token, baseUrl.trim(), apiKey.trim());
      setAvailable(result.models);
      setProbeNote(result.detail ?? '');
      if (result.models.length) showToast(`모델 ${result.models.length}개를 찾았습니다.`, 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '모델을 불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!token || busy) return;
    setBusy(true);
    try {
      await addCustomModel(token, {
        label: label.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
      });
      setPreset('');
      setLabel('');
      setBaseUrl('');
      setApiKey('');
      setModel('');
      setAvailable([]);
      setProbeNote('');
      await onChanged();
      showToast('모델 API 를 등록했습니다.', 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '등록하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove(connId: string) {
    if (!token || busy) return;
    setBusy(true);
    try {
      await removeCustomModel(token, connId);
      await onChanged();
      showToast('지웠습니다.', 'success');
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : '지우지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  const keyHint = PROVIDER_PRESETS.find((row) => row.id === preset)?.keyHint ?? '';
  const ready = Boolean(label.trim() && baseUrl.trim() && apiKey.trim() && model.trim());

  return (
    <section className={styles.card}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>
          커스텀 모델 API
          <InfoNote title="커스텀 모델 API">
            <p>
              <strong>등록하지 않으면 저희가 제공하는 모델로 돕니다.</strong> 대부분의 팀은 이대로 쓰면
              됩니다.
            </p>
            <p>
              회사 규정상 <strong>자기 계약으로만 데이터를 보내야 하거나</strong>, 사용량이 많아 직접
              결제하려는 팀, 사내에 모델을 띄운 팀은 여기에 등록합니다.
            </p>
            <p>
              주소는 <strong>OpenAI 호환</strong>이어야 합니다 — OpenRouter·Groq·Together·Azure·사내
              vLLM 이 여기 해당합니다. 등록한 모델은 위 「메인 모델」과 에이전트 빌더에서 고를 수
              있습니다.
            </p>
            <p>키는 암호화해 저장하고 화면에 다시 보여주지 않습니다.</p>
          </InfoNote>
        </h2>
      </div>

      {/* **한 줄이다.** 제공자를 고르면 주소가 채워지므로 사용자가 적을 것은
          이름과 키뿐이다 — 두 줄로 나눌 이유가 없었다(2026-08-12 PM 지적). */}
      <div className={styles.keyForm}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>제공자</span>
          <select
            className={styles.modelSelect}
            value={preset}
            onChange={(e) => {
              const found = PROVIDER_PRESETS.find((row) => row.id === e.target.value);
              setPreset(e.target.value);
              setBaseUrl(found?.baseUrl ?? '');
              if (found && !label.trim()) setLabel(found.label);
              setAvailable([]);
              setProbeNote('');
            }}
          >
            <option value="">선택하세요</option>
            {PROVIDER_PRESETS.map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <Input label="이름" placeholder="사내 vLLM" value={label} onChange={(e) => setLabel(e.target.value)} />
        <Input
          label={`API 키${keyHint ? ` — ${keyHint}` : ''}`}
          type="password"
          placeholder="sk-..."
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={busy || !baseUrl.trim() || !apiKey.trim()}
          onClick={() => void probe()}
        >
          {busy ? '확인 중…' : '모델 불러오기'}
        </Button>
      </div>

      {/* 사내 서버처럼 우리가 주소를 모르는 경우에만 적게 한다. */}
      {preset === 'custom' && (
        <div className={styles.keyForm}>
          <Input
            label="주소"
            placeholder="http://vllm.내부주소/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>
      )}

      {/* **폼 아래에 둔다.** 등록하면 여기 쌓이는 순서라 그렇게 읽힌다
          (2026-08-12 PM 지적). */}
      {rows.length === 0 ? (
        <p className={styles.cardSub}>아직 등록한 모델 API 가 없습니다.</p>
      ) : (
        <div className={styles.list}>
          {rows.map((row) => (
            <div key={row.conn_id} className={styles.row}>
              <span className={styles.rowIcon}>
                <Icon name="link" size={20} color="var(--color-primary)" />
              </span>
              <div className={styles.rowBody}>
                <span className={styles.rowName}>{row.label}</span>
                <span className={styles.rowVendor}>{row.model}</span>
                <span className={styles.rowDesc}>{row.base_url}</span>
              </div>
              <div className={styles.rowActions}>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => void remove(row.conn_id)}
                >
                  지우기
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* **모델 이름을 직접 적게 하지 않는다.** 불러온 것 중에서 고른다 —
          외워 적게 하면 오타 하나가 실행 시점 404 가 된다. */}
      {available.length > 0 && (
        <div className={styles.keyForm}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>모델</span>
            <select
              className={styles.modelSelect}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">선택하세요</option>
              {available.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <Button disabled={busy || !ready} onClick={() => void add()}>
            등록
          </Button>
        </div>
      )}

      {probeNote && <p className={styles.cardSub}>{probeNote}</p>}
    </section>
  );
}
