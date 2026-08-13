import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, OpsDataTable, OpsEmpty, OpsPageHeader, OpsSectionCard } from '../../components';
import { attachOpsModel, detachOpsModel, fetchOpsModels } from '../../api/opsModels';
import type { OpsModel } from '../../api/opsModels';
import { fetchOpsTeams } from '../../api/opsTeams';
import type { OpsTeam } from '../../api/opsTeams';
import { PROVIDER_PRESETS } from '../../data/providers';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 팀별 모델 부착.
 *
 * **팀이 스스로 붙이지 않는다.** 회사가 요청하면 운영자가 여기서 붙인다
 * (2026-08-13 멘토링). 설정의 등록 폼을 없애고 이 화면으로 옮긴 이유는
 * `apps/ops/views/models.py` 에 적어 두었다.
 *
 * 붙이는 사람만 바뀌고 **쓸 수 있는 범위는 여전히 그 팀뿐이다.**
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
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

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
  }

  async function attach() {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    try {
      setModels(
        await attachOpsModel(session.token, {
          team_id: teamId,
          label: preset.label,
          base_url: baseUrl.trim(),
          api_key: apiKey.trim(),
          model: model.trim(),
        }),
      );
      // 키는 화면에도 남기지 않는다.
      setApiKey('');
      setModel('');
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '붙이지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function detach(row: OpsModel) {
    const session = loadOpsSession();
    if (!session) return;
    setBusy(true);
    setFormError('');
    try {
      setModels(await detachOpsModel(session.token, row.conn_id));
    } catch (thrown) {
      setFormError(thrown instanceof ApiError ? thrown.message : '떼지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  if (loading && !models) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="모델 부착" description="요청받은 모델을 팀에 붙입니다. 붙인 팀만 그 모델을 고를 수 있습니다." />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title="모델 부착" description="요청받은 모델을 팀에 붙입니다. 붙인 팀만 그 모델을 고를 수 있습니다." />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const rows = models ?? [];
  const canAttach = Boolean(teamId && baseUrl.trim() && apiKey.trim() && model.trim());

  return (
    <div className={styles.page}>
      <OpsPageHeader title="모델 부착" description="요청받은 모델을 팀에 붙입니다. 붙인 팀만 그 모델을 고를 수 있습니다." />

      <OpsSectionCard title="새로 붙이기" subtitle="저장 전에 그 주소와 키로 실제로 한 번 불러 봅니다.">
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

          <div className={styles.fieldGroup}>
            <label htmlFor="model-name">모델 이름</label>
            <input
              id="model-name"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="gemini-3.6-flash"
            />
          </div>
        </div>

        {formError && <p className={styles.inlineEmpty} role="alert">{formError}</p>}

        <div className={styles.formActions}>
          <Button onClick={attach} disabled={!canAttach || busy}>
            {busy ? '확인하는 중…' : '붙이기'}
          </Button>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title={`붙어 있는 모델 ${rows.length}건`}>
        {rows.length === 0 ? (
          <OpsEmpty message="아직 어느 팀에도 붙인 모델이 없습니다." />
        ) : (
          <OpsDataTable minWidth={860}>
            <thead>
              <tr>
                <th>팀</th>
                <th>모델</th>
                <th>제공자</th>
                <th>주소</th>
                <th>붙인 날</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.conn_id}>
                  <td>{row.team_name ?? row.team_id}</td>
                  <td>{row.model}</td>
                  <td>{row.label}</td>
                  <td>{row.base_url}</td>
                  <td>{row.connected_at.slice(0, 10)}</td>
                  <td>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => detach(row)}>
                      떼기
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
