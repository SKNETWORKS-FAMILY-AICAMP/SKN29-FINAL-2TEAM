import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, OpsDataTable, OpsEmpty, OpsPageHeader, OpsSectionCard } from '../../components';
import { fetchOpsModels, probeOpsModels, registerOpsModel, removeOpsModel } from '../../api/opsModels';
import type { OpsModel } from '../../api/opsModels';
import { fetchOpsTeams } from '../../api/opsTeams';
import type { OpsTeam } from '../../api/opsTeams';
import { PROVIDER_PRESETS } from '../../data/providers';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 팀별 모델 등록. **등록만 한다**(2026-08-18 PM).
 *
 * **팀이 스스로 등록하지 않는다.** 회사가 요청하면 운영자가 여기서 등록한다
 * (2026-08-13 멘토링). 설정의 등록 폼을 없애고 이 화면으로 옮긴 이유는
 * `apps/ops/views/models.py` 에 적어 두었다.
 *
 * **기본 채팅 모델을 고르는 것은 여기가 아니다** — 팀 상세에 있다. 등록은
 * 「무엇을 새로 붙이나」라 주제로 시작하는 일이고, 고르는 것은 「이 팀이 무엇으로
 * 도나」다.
 *
 * 등록하는 사람만 바뀌고 **쓸 수 있는 범위는 여전히 그 팀뿐이다.**
 */
export default function OpsModelsPage() {
  const navigate = useNavigate();
  const [models, setModels] = useState<OpsModel[] | null>(null);
  const [teams, setTeams] = useState<OpsTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [teamId, setTeamId] = useState('');
  const [provider, setProvider] = useState(PROVIDER_PRESETS[0].id);
  const [baseUrl, setBaseUrl] = useState(PROVIDER_PRESETS[0].baseUrl);
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [supportsImageInput, setSupportsImageInput] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  /** 등록은 됐지만(201) 그 서버가 토큰 사용량을 안 준다는 안내 — 막지 않는다. */
  const [registerWarning, setRegisterWarning] = useState('');
  /** 「모델 불러오기」로 받아 온 이름들. 비어 있으면 직접 입력으로 둔다. */
  const [available, setAvailable] = useState<string[]>([]);
  const [probeNote, setProbeNote] = useState('');

  const preset = PROVIDER_PRESETS.find((item) => item.id === provider) ?? PROVIDER_PRESETS[0];

  async function load() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [rows, teamRows] = await Promise.all([
        fetchOpsModels(session.token),
        fetchOpsTeams(session.token),
      ]);
      setModels(rows);
      setTeams(teamRows);
      if (!teamId && teamRows.length > 0) setTeamId(teamRows[0].team_id);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '모델 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    setRegisterWarning('');
    setSupportsImageInput(false);
  }

  /** 그 주소·키가 가진 모델을 받아 온다. 못 받으면 직접 입력으로 남는다. */
  async function probe() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    try {
      const result = await probeOpsModels(session.token, baseUrl.trim(), apiKey.trim());
      setAvailable(result.models);
      setProbeNote(result.detail ?? '');
      if (result.models.length === 1) setModel(result.models[0]);
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '모델을 불러오지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function register() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    setRegisterWarning('');
    try {
      const result = await registerOpsModel(session.token, {
        team_id: teamId,
        label: preset.label,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
        supports_image_input: supportsImageInput,
      });
      // 키는 화면에도 남기지 않는다.
      setApiKey('');
      setModel('');
      setAvailable([]);
      setProbeNote('');
      setRegisterWarning(result.warning ?? '');
      await load();
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '등록하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: OpsModel) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    try {
      await removeOpsModel(session.token, row.conn_id);
      await load();
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '삭제하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  if (loading && !models) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="모델" />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="모델" />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const rows = models ?? [];
  const canRegister = Boolean(teamId && baseUrl.trim() && apiKey.trim() && model.trim());

  return (
    <div className={styles.page}>
      <OpsPageHeader title="모델" />

      <OpsSectionCard title="새로 등록">
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="model-team">팀</label>
            <select id="model-team" value={teamId} onChange={(event) => setTeamId(event.target.value)}>
              {teams.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {team.name} ({team.team_id})
                </option>
              ))}
            </select>
          </div>
          <div className={styles.fieldGroup}>
            {/* 체크박스라 `htmlFor` 로 묶을 하나가 없다 — 묶음에 이름을 준다(팀 상세
                「연결 실패 시」와 같은 짜임). `.radioRow` 로 감싸지 않으면 텍스트 칸용
                `.fieldGroup input` 이 걸려 체크박스가 폭 100%·높이 40px 상자로 부푼다. */}
            <span id="model-image-input-label">입력 기능</span>
            <div className={styles.radioRow} aria-labelledby="model-image-input-label">
              <label>
                <input
                  type="checkbox"
                  checked={supportsImageInput}
                  onChange={(event) => setSupportsImageInput(event.target.checked)}
                />
                이미지 입력 지원
              </label>
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="model-provider">제공자</label>
            <select id="model-provider" value={provider} onChange={(event) => pickProvider(event.target.value)}>
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
              {/* 키를 어디서 받는지는 제공자마다 다르다. 라벨 옆에 붙여 두면
                  운영자가 창을 옮겨 다니며 찾지 않아도 된다. */}
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
            {/* **불러온 것이 있으면 고르게 한다.** 셀렉트여야 목록이 있다는 것이
                보인다 — `datalist` 는 겉이 입력칸이라 뒤에 목록이 있는지 모른다
                (2026-08-13 PM 지적).

                직접 입력은 **목록을 못 받았을 때만**이다. Anthropic 호환 경로는
                `/v1/models` 가 401 이라, 그 경우까지 셀렉트로 두면 고를 것이 없어
                아무것도 등록할 수 없다.

                거르지는 않는다 — 키가 가진 것을 이름으로 걸러 내면 정작 고객이
                요청한 모델이 안 보일 수 있다. */}
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


        {formError && <p className={styles.inlineEmpty} role="alert">{formError}</p>}
        {/* 막지 않는 안내다 — 등록(201)은 이미 끝났다. `role="status"`로 formError의
            `role="alert"`와 구분한다. */}
        {registerWarning && (
          <p className={styles.inlineEmpty} role="status">{registerWarning}</p>
        )}

        <div className={styles.formSubmit}>
          <Button onClick={register} disabled={!canRegister || busy}>
            {busy ? '확인하는 중…' : '등록'}
          </Button>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title={`등록된 모델 ${rows.length}건`}>
        {rows.length === 0 ? (
          <OpsEmpty message="아직 어느 팀에도 등록한 모델이 없습니다." />
        ) : (
          <OpsDataTable minWidth={860}>
            <thead>
              {/* `table-layout: fixed` 라 폭을 안 주면 6칸이 균등하게 갈린다 —
                  팀·등록일이 남아돌고 정작 긴 주소만 굶는다. */}
              <tr>
                <th style={{ width: 130 }}>팀</th>
                <th style={{ width: 210 }}>모델</th>
                <th style={{ width: 130 }}>제공자</th>
                <th>주소</th>
                <th style={{ width: 90 }}>이미지</th>
                <th style={{ width: 100 }}>등록일</th>
                <th style={{ width: 80 }} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.conn_id}>
                  <td>{row.team_name ?? row.team_id}</td>
                  <td>{row.model}</td>
                  <td>{row.label}</td>
                  <td className={styles.cellEllipsis} title={row.base_url}>
                    {row.base_url}
                  </td>
                  <td>{row.supports_image_input ? '지원' : '텍스트'}</td>
                  <td>{row.connected_at.slice(0, 10)}</td>
                  <td>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove(row)}>
                      삭제
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </OpsDataTable>
        )}
      </OpsSectionCard>
    </div>
  );
}
