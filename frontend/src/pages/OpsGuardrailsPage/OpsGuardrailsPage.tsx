import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, OpsDataTable, OpsEmpty, OpsPageHeader, OpsSectionCard } from '../../components';
import type { BadgeTone } from '../../components';
import {
  fetchOpsGuardrails,
  registerOpsGuardrail,
  removeOpsGuardrail,
  updateOpsGuardrail,
} from '../../api/opsGuardrails';
import type { GuardrailKind, OpsGuardrailProvider } from '../../api/opsGuardrails';
import { fetchOpsTeams } from '../../api/opsTeams';
import type { OpsTeam } from '../../api/opsTeams';
import { ApiError } from '../../api/client';
import { loadOpsSession } from '../../utils/opsSession';
import styles from '../OpsShared/OpsPages.module.css';

/**
 * 팀별 외부 가드레일 등록.
 *
 * 고객이 이미 가진 가드레일을 등록해서 그 팀의 대화가 그걸 거쳐 돌게 한다.
 * **팀이 스스로 등록하지 않는다** — 엔드포인트와 키를 알아야 하는 일이라
 * 커스텀 도구(`OpsMcpPage`)·모델과 같은 자리에 둔다.
 */

/** 상태 칩. 세 상태를 뭉개지 않는다 — 사람이 할 행동이 각각 다르다. */
const STATUS: Record<OpsGuardrailProvider['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  // 등록만 하고 아직 확인을 안 한 상태. 실패와 다르다.
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

const KIND_LABELS: Record<GuardrailKind, string> = {
  OPENAI_GUARDRAILS: 'OpenAI Guardrails',
  BEDROCK_GUARDRAILS: 'AWS Bedrock Guardrails',
  AZURE_CONTENT_SAFETY: 'Azure Content Safety',
};

const TITLE = '가드레일';

/** 종류마다 받는 값이 다르다 — 화면이 그 차이를 그대로 그린다. */
interface FieldSpec {
  key: string;
  label: string;
  placeholder?: string;
  multiline?: boolean;
  /** 비밀값은 `config` 가 아니라 `credential` 로 간다. */
  secret?: boolean;
}

const FIELDS: Record<GuardrailKind, FieldSpec[]> = {
  AZURE_CONTENT_SAFETY: [
    { key: 'endpoint', label: '엔드포인트 (https)', placeholder: 'https://example.cognitiveservices.azure.com' },
    { key: 'api_key', label: '키', secret: true },
  ],
  BEDROCK_GUARDRAILS: [
    { key: 'guardrail_id', label: 'Guardrail ID', placeholder: 'abcd1234efgh' },
    { key: 'guardrail_version', label: '버전', placeholder: 'DRAFT' },
    { key: 'region', label: '리전', placeholder: 'ap-northeast-2' },
    { key: 'access_key_id', label: 'Access Key ID', secret: true },
    { key: 'secret_access_key', label: 'Secret Access Key', secret: true },
  ],
  OPENAI_GUARDRAILS: [
    {
      key: 'pipeline',
      label: '설정 JSON (Guardrails 위저드에서 받은 것)',
      placeholder: '{"version": 1, "input": {...}}',
      multiline: true,
    },
    { key: 'api_key', label: 'OpenAI 키', secret: true },
  ],
};

/**
 * 설정을 처음부터 만들지 않아도 되게 두는 기본값.
 *
 * **가진 게 없는 고객이 대부분이다.** OpenAI Guardrails 는 아직 Preview 라
 * 위저드(guardrails.openai.com)에서 미리 만들어 둔 고객이 사실상 없다 —
 * 등록 화면이 「가진 것을 붙여넣으세요」로만 되어 있으면 그 고객은 가드레일
 * 없이 돈다. 그래서 위저드가 실제로 뽑아 주는 것과 **같은 형식**의 시작점을
 * 한 벌 넣어 둔다(2026-08-20 에 위저드에서 직접 뽑아 확인한 값이다).
 *
 * 직접 만든 설정이 있으면 그대로 붙여넣으면 된다 — 이건 시작점일 뿐이다.
 *
 * 고른 둘의 근거: Moderation 은 **API 호출이 무료**고 300ms 다. Jailbreak 은
 * 우리가 프롬프트 문구로만 막던 자리이고 1000ms 다. 나머지는 우리 배선이
 * 없거나(출력 단계), 영어 전용이거나(PII), 벡터스토어가 필요하다(할루시네이션).
 */
const OPENAI_GUARDRAILS_PRESET = JSON.stringify(
  {
    version: 1,
    pre_flight: {
      version: 1,
      guardrails: [
        {
          name: 'Moderation',
          config: {
            categories: [
              'sexual',
              'sexual/minors',
              'hate',
              'hate/threatening',
              'harassment',
              'harassment/threatening',
              'self-harm',
              'self-harm/intent',
              'self-harm/instructions',
              'violence',
              'violence/graphic',
              'illicit',
              'illicit/violent',
            ],
          },
        },
      ],
    },
    input: {
      version: 1,
      guardrails: [
        {
          name: 'Jailbreak',
          config: { confidence_threshold: 0.7, model: 'gpt-4.1-mini', include_reasoning: false },
        },
      ],
    },
    output: { version: 1, guardrails: [] },
  },
  null,
  2,
);

/** 종류별 시작점. 없는 종류는 버튼도 안 뜬다 — 빈 버튼을 두면 눌러도 아무 일이 없다. */
const PRESETS: Partial<Record<GuardrailKind, { field: string; value: string }>> = {
  OPENAI_GUARDRAILS: { field: 'pipeline', value: OPENAI_GUARDRAILS_PRESET },
};

/** 저장된 비밀값은 돌려받지 못한다 — 화면은 있는지 여부만 안다. */
function secretHint(editing: OpsGuardrailProvider | null, label: string) {
  if (editing && editing.has_credential) return `${label} (비워 두면 저장된 값을 그대로 둡니다)`;
  return label;
}

export default function OpsGuardrailsPage() {
  const navigate = useNavigate();
  const [providers, setProviders] = useState<OpsGuardrailProvider[] | null>(null);
  const [teams, setTeams] = useState<OpsTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [teamId, setTeamId] = useState('');
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GuardrailKind>('OPENAI_GUARDRAILS');
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState<OpsGuardrailProvider | null>(null);

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
        fetchOpsGuardrails(session.token),
        fetchOpsTeams(session.token),
      ]);
      setProviders(rows);
      setTeams(teamRows);
      if (!teamId && teamRows.length > 0) setTeamId(teamRows[0].team_id);
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setError(thrown instanceof ApiError ? thrown.message : '가드레일 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetForm() {
    setEditing(null);
    setName('');
    setValues({});
    setFormError('');
    setNote('');
  }

  function startEdit(row: OpsGuardrailProvider) {
    setEditing(row);
    setTeamId(row.team_id);
    setName(row.name);
    setKind(row.kind);
    // 설정값은 되돌려 받지만 비밀값은 아니다 — 비밀 칸은 빈 채로 시작한다.
    const next: Record<string, string> = {};
    for (const field of FIELDS[row.kind]) {
      if (field.secret) continue;
      const value = row.config?.[field.key];
      next[field.key] = value == null ? '' : String(value);
    }
    setValues(next);
    setFormError('');
    setNote('');
  }

  /** 화면 값을 `config`(공개)와 `credential`(비밀)로 가른다. */
  function split() {
    const config: Record<string, unknown> = {};
    const credential: Record<string, unknown> = {};
    for (const field of FIELDS[kind]) {
      const raw = (values[field.key] ?? '').trim();
      if (!raw) continue;
      if (field.secret) credential[field.key] = raw;
      else config[field.key] = raw;
    }
    return { config, credential };
  }

  async function submit() {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    const { config, credential } = split();
    setBusy(true);
    setFormError('');
    setNote('');
    try {
      if (editing) {
        // 비밀 칸을 채웠을 때만 교체한다 — 비워 두면 저장된 값이 남는다.
        const replace = Object.keys(credential).length > 0;
        await updateOpsGuardrail(session.token, editing.provider_id, {
          name: name.trim(),
          kind,
          config,
          credential: replace ? credential : null,
          replace_credential: replace,
        });
        setNote('수정했습니다.');
      } else {
        await registerOpsGuardrail(session.token, {
          team_id: teamId,
          name: name.trim(),
          kind,
          config,
          credential: Object.keys(credential).length > 0 ? credential : null,
        });
        setNote('등록했습니다.');
      }
      resetForm();
      await load();
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setFormError(thrown instanceof ApiError ? thrown.message : '요청을 처리하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: OpsGuardrailProvider) {
    const session = loadOpsSession();
    if (!session) {
      navigate('/ops/login', { replace: true });
      return;
    }

    setBusy(true);
    setFormError('');
    try {
      await removeOpsGuardrail(session.token, row.provider_id);
      if (editing?.provider_id === row.provider_id) resetForm();
      setNote(`‘${row.name}’을 삭제했습니다.`);
      await load();
    } catch (thrown) {
      if (thrown instanceof ApiError && thrown.status === 401) {
        navigate('/ops/login', { replace: true });
        return;
      }
      setFormError(thrown instanceof ApiError ? thrown.message : '삭제하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  if (loading && !providers) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} />
        <p className={styles.inlineEmpty}>불러오는 중…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <OpsPageHeader title={TITLE} />
        <p className={styles.inlineEmpty} role="alert">{error}</p>
        <Button variant="outline" onClick={load}>다시 시도</Button>
      </div>
    );
  }

  const rows = providers ?? [];
  const canSubmit = Boolean(name.trim() && (editing || teamId));

  return (
    <div className={styles.page}>
      <OpsPageHeader title={TITLE} />

      <OpsSectionCard title={editing ? '가드레일 수정 · ' + editing.name : '새로 등록'}>
        <div className={styles.formGrid}>
          <div className={styles.fieldGroup}>
            <label htmlFor="guardrail-team">팀</label>
            {/* 수정할 때는 팀을 잠근다 — 팀을 옮기는 것은 다른 팀 대화의 검사
                경로를 바꾸는 일이라, 지우고 다시 등록하는 편이 기록에도 정확하다. */}
            <select
              id="guardrail-team"
              value={teamId}
              disabled={Boolean(editing)}
              onChange={(event) => setTeamId(event.target.value)}
            >
              {teams.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {team.name} ({team.team_id})
                </option>
              ))}
            </select>
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="guardrail-name">이름</label>
            <input
              id="guardrail-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="우리 회사 가드레일"
            />
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="guardrail-kind">종류</label>
            <select
              id="guardrail-kind"
              value={kind}
              onChange={(event) => {
                // 종류가 바뀌면 받는 값이 통째로 달라진다 — 이전 값을 남기면
                // 안 쓰는 칸의 값이 조용히 함께 저장된다.
                setKind(event.target.value as GuardrailKind);
                setValues({});
              }}
            >
              {(Object.keys(KIND_LABELS) as GuardrailKind[]).map((item) => (
                <option key={item} value={item}>
                  {KIND_LABELS[item]}
                </option>
              ))}
            </select>
          </div>

          {FIELDS[kind].map((field) => (
            <div className={styles.fieldGroup} key={field.key}>
              <label htmlFor={`guardrail-${field.key}`}>
                {field.secret ? secretHint(editing, field.label) : field.label}
              </label>
              {field.multiline ? (
                <>
                  <textarea
                    id={`guardrail-${field.key}`}
                    rows={4}
                    value={values[field.key] ?? ''}
                    placeholder={field.placeholder}
                    onChange={(event) =>
                      setValues({ ...values, [field.key]: event.target.value })
                    }
                  />
                  {/* 가진 설정이 없는 고객이 여기서 막힌다 — 시작점을 한 번에 넣어 준다.
                      이미 적어 둔 것이 있으면 덮어쓰지 않는다. */}
                  {PRESETS[kind]?.field === field.key && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || Boolean((values[field.key] ?? '').trim())}
                      onClick={() =>
                        setValues({ ...values, [field.key]: PRESETS[kind]!.value })
                      }
                    >
                      기본 설정 넣기
                    </Button>
                  )}
                </>
              ) : (
                <input
                  id={`guardrail-${field.key}`}
                  type={field.secret ? 'password' : 'text'}
                  value={values[field.key] ?? ''}
                  placeholder={field.placeholder}
                  onChange={(event) =>
                    setValues({ ...values, [field.key]: event.target.value })
                  }
                />
              )}
            </div>
          ))}
        </div>

        {formError && <p className={styles.inlineEmpty} role="alert">{formError}</p>}
        {note && <p className={styles.inlineEmpty}>{note}</p>}

        <div className={styles.formSubmit}>
          <Button onClick={submit} disabled={!canSubmit || busy}>
            {busy ? '처리하는 중…' : editing ? '저장' : '등록'}
          </Button>
          {editing && (
            <Button variant="outline" onClick={resetForm} disabled={busy}>
              취소
            </Button>
          )}
        </div>
      </OpsSectionCard>

      <OpsSectionCard title={'등록된 가드레일 ' + rows.length + '건'}>
        {rows.length === 0 ? (
          <OpsEmpty message="아직 어느 팀에도 등록한 가드레일이 없습니다." />
        ) : (
          <OpsDataTable minWidth={960}>
            <thead>
              <tr>
                <th style={{ width: 130 }}>팀</th>
                <th style={{ width: 170 }}>이름</th>
                <th>종류</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 90 }}>키</th>
                <th style={{ width: 110 }}>확인</th>
                <th style={{ width: 180 }} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.provider_id}>
                  <td>{row.team_name ?? row.team_id}</td>
                  <td>{row.name}</td>
                  <td>{KIND_LABELS[row.kind] ?? row.kind}</td>
                  <td>
                    <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                  </td>
                  <td>{row.has_credential ? '있음' : '없음'}</td>
                  <td>{row.last_checked_at ? row.last_checked_at.slice(0, 10) : '없음'}</td>
                  <td>
                    <div className={styles.cellActions}>
                      <Button
                        size="sm"
                        variant="outline"
                        data-button
                        disabled={busy}
                        onClick={() => startEdit(row)}
                      >
                        수정
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        data-button
                        disabled={busy}
                        onClick={() => remove(row)}
                      >
                        삭제
                      </Button>
                    </div>
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
