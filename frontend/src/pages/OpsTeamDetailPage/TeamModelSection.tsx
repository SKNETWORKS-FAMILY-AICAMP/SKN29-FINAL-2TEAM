import { useCallback, useEffect, useState } from 'react';
import { Button, OpsDataTable, OpsEmpty, OpsSectionCard } from '../../components';
import {
  fetchOpsModels,
  fetchOpsTeamDefaultModel,
  probeOpsModels,
  registerOpsModel,
  removeOpsModel,
  saveOpsTeamDefaultModel,
} from '../../api/opsModels';
import type { OpsModel, OpsTeamDefaultModel } from '../../api/opsModels';
import { PROVIDER_PRESETS } from '../../data/providers';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 이 팀의 모델 — 등록과 기본 모델.
 *
 * **팀 상세로 옮겨 왔다**(2026-08-18 PM). 전에는 `/ops/models` 한 페이지에서
 * 팀을 고르고 다뤘는데, 운영자가 실제로 하는 일은 「회사 A 가 요청했다」로
 * 시작한다 — 그런데 화면은 「모델이라는 주제」로 시작하라고 했다. 한 팀을
 * 세팅하려면 페이지 둘을 돌며 **같은 팀을 두 번 골라야** 했다.
 *
 * 그래서 팀 선택 드롭다운이 없다. 이미 그 팀 안이다.
 *
 * 전 팀 목록은 없앴다 — 「어느 팀이 무엇을 쓰나」는 실제로 묻지 않는 질문이었고,
 * 정말 필요한 「어디가 깨졌나」는 목록이 아니라 **운영 현황**이 답할 일이다.
 */
export function TeamModelSection({ teamId }: { teamId: string }) {
  const [models, setModels] = useState<OpsModel[]>([]);
  const [defaultModel, setDefaultModel] = useState<OpsTeamDefaultModel | null>(null);

  const [provider, setProvider] = useState(PROVIDER_PRESETS[0].id);
  const [baseUrl, setBaseUrl] = useState(PROVIDER_PRESETS[0].baseUrl);
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  /** 「모델 불러오기」로 받아 온 이름들. 비어 있으면 직접 입력으로 둔다. */
  const [available, setAvailable] = useState<string[]>([]);
  const [probeNote, setProbeNote] = useState('');

  const preset = PROVIDER_PRESETS.find((item) => item.id === provider) ?? PROVIDER_PRESETS[0];

  const load = useCallback(async () => {
    const session = loadOpsSession();
    if (!session) return;
    try {
      const [rows, current] = await Promise.all([
        fetchOpsModels(session.token),
        fetchOpsTeamDefaultModel(session.token, teamId),
      ]);
      // 목록 API 는 전 팀을 준다. 여기서는 이 팀 것만 본다.
      setModels(rows.filter((row) => row.team_id === teamId));
      setDefaultModel(current);
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '모델을 불러오지 못했습니다.');
    }
  }, [teamId]);

  useEffect(() => {
    void load();
  }, [load]);

  function pickProvider(id: string) {
    setProvider(id);
    const found = PROVIDER_PRESETS.find((item) => item.id === id);
    // 직접 입력은 주소를 비워 둔다 — 프리셋 주소가 남아 있으면 사내 서버를
    // 넣으려던 사람이 남의 주소를 그대로 저장한다.
    if (found) setBaseUrl(found.baseUrl);
    // 주소가 바뀌면 앞서 불러온 목록은 다른 곳의 것이다.
    setAvailable([]);
    setProbeNote('');
    setModel('');
  }

  /** 그 주소·키가 가진 모델을 받아 온다. 못 받으면 직접 입력으로 남는다. */
  async function probe() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const result = await probeOpsModels(session.token, baseUrl.trim(), apiKey.trim());
      setAvailable(result.models);
      setProbeNote(result.detail ?? '');
      if (result.models.length === 1) setModel(result.models[0]);
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '모델을 불러오지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function register() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await registerOpsModel(session.token, {
        team_id: teamId,
        label: preset.label,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
      });
      // 키는 화면에도 남기지 않는다.
      setApiKey('');
      setModel('');
      setAvailable([]);
      setProbeNote('');
      await load();
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '등록하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: OpsModel) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await removeOpsModel(session.token, row.conn_id);
      await load();
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '지우지 못했습니다.');
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
      setNote(`${saved.agent_name} 이 ${saved.model} 로 돕니다.`);
    } catch (thrown) {
      setError(thrown instanceof ApiError ? thrown.message : '바꾸지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const canRegister = Boolean(baseUrl.trim() && apiKey.trim() && model.trim());

  return (
    <>
      <OpsSectionCard
        title="기본 채팅 모델"
        subtitle="이 팀이 아무 에이전트도 고르지 않고 말을 걸었을 때 도는 모델입니다."
      >
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
              <label htmlFor="team-default-model">{defaultModel.agent_name} 이 쓰는 모델</label>
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
            {note && <p className={styles.inlineEmpty}>{note}</p>}
          </div>
        )}
      </OpsSectionCard>

      <OpsSectionCard
        title={`이 팀에 등록된 모델 ${models.length}건`}
        subtitle="요청받은 모델을 등록합니다. 저장 전에 그 주소와 키로 실제로 한 번 불러 봅니다."
      >
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="model-provider">제공자</label>
            <select
              id="model-provider"
              value={provider}
              onChange={(event) => pickProvider(event.target.value)}
            >
              {PROVIDER_PRESETS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="model-base-url">주소 (OpenAI 호환)</label>
            <input
              id="model-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://…/v1"
            />
          </div>

          {/* **키 옆에 둔다.** 불러오기가 쓰는 재료가 주소와 이 키라서, 아래
              줄에 떼어 놓으면 무엇으로 불러오는지 안 보인다. */}
          <div className={styles.inlineField}>
            <div className={styles.fieldGroup}>
              <label htmlFor="model-key">API 키 · {preset.keyHint}</label>
              <input
                id="model-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            </div>
            <Button
              variant="outline"
              onClick={probe}
              disabled={busy || !baseUrl.trim() || !apiKey.trim()}
            >
              {busy ? '불러오는 중…' : '모델 불러오기'}
            </Button>
          </div>

          {probeNote && <p className={styles.inlineEmpty}>{probeNote}</p>}

          <div className={styles.fieldGroup}>
            <label htmlFor="model-name">모델</label>
            {/* 불러온 것이 있으면 고르게 한다 — 셀렉트여야 목록이 있다는 것이
                보인다. 직접 입력은 **목록을 못 받았을 때만**이다(Anthropic 호환
                경로는 `/v1/models` 가 401 이라 고를 것이 없어진다). */}
            {available.length > 0 ? (
              <select id="model-name" value={model} onChange={(event) => setModel(event.target.value)}>
                <option value="">모델 {available.length}개 중에서 고르세요</option>
                {available.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id="model-name"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder="gemini-3.6-flash"
              />
            )}
          </div>
        </div>

        {error && <p className={styles.inlineEmpty} role="alert">{error}</p>}

        <div className={styles.formSubmit}>
          <Button onClick={register} disabled={!canRegister || busy}>
            {busy ? '확인하는 중…' : '등록'}
          </Button>
        </div>

        {models.length === 0 ? (
          <OpsEmpty message="이 팀에 등록한 모델이 없습니다. 기본 제공 모델만 씁니다." />
        ) : (
          <OpsDataTable minWidth={720}>
            <thead>
              <tr>
                <th style={{ width: 210 }}>모델</th>
                <th style={{ width: 130 }}>제공자</th>
                <th>주소</th>
                <th style={{ width: 100 }}>등록일</th>
                <th style={{ width: 90 }} />
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
                  <td>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove(row)}>
                      지우기
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>
    </>
  );
}
