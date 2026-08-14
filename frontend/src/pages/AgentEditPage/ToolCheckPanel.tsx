import { useEffect, useState } from 'react';
import { Badge, Button, Icon, Input } from '../../components';
import { CHECK_STATUS } from './checkLabels';
import type { BadgeTone } from '../../components';
import { checkBuilderTools } from '../../api/agents';
import type { ToolChoice, ToolCheckResult } from '../../api/agents';
import { ApiError } from '../../api/client';
import pageStyles from './AgentEditPage.module.css';
import styles from './TestRunModal.module.css';

export interface ToolCheckPanelProps {
  token: string | null;
  allTools: ToolChoice[];
  toolRefs: string[];
  /** 칩의 × — 도구 하나를 뺀다. */
  onToggleTool: (ref: string) => void;
  /** 「도구 추가/제외」 — 메인 화면과 같은 선택 팝업을 연다. */
  onOpenToolPicker: () => void;
  /** 마운트 시 한 번 자동으로 확인을 돌린다 — 검증 단계와 나란히 자동 실행될 때 쓴다. */
  autoRun?: boolean;
}

type FieldKind = 'string' | 'number' | 'array' | 'object' | 'json';

function fieldKind(type: string | undefined): FieldKind {
  if (type === 'string') return 'string';
  if (type === 'integer' || type === 'number') return 'number';
  if (type === 'array') return 'array';
  if (type === 'object') return 'object';
  return 'json';
}

interface BuildArgumentsResult {
  argumentsByRef: Record<string, Record<string, unknown>>;
  errors: Record<string, string>;
}

/**
 * 원문 입력 문자열을 도구 인자로 조립한다. 잘못된 값을 조용히 버리지 않고
 * 필드별 오류로 돌려준다 — 오류가 하나라도 있으면 호출측이 API를 부르지 않는다.
 */
function buildArguments(
  toolRefs: string[],
  toolByRef: Map<string, ToolChoice>,
  rawArgs: Record<string, string>,
): BuildArgumentsResult {
  const argumentsByRef: Record<string, Record<string, unknown>> = {};
  const errors: Record<string, string> = {};

  for (const ref of toolRefs) {
    const schema = toolByRef.get(ref)?.input_schema;
    const properties = schema?.properties ?? {};
    const required = new Set(schema?.required ?? []);
    const built: Record<string, unknown> = {};

    for (const prop of Object.keys(properties)) {
      const key = `${ref}::${prop}`;
      const raw = rawArgs[key] ?? '';
      const kind = fieldKind(properties[prop].type);

      if (raw === '') {
        if (required.has(prop)) errors[key] = '필수 입력입니다.';
        continue;
      }

      if (kind === 'number') {
        const parsed = Number(raw);
        if (Number.isNaN(parsed)) {
          errors[key] = '숫자로 입력해 주세요.';
        } else {
          built[prop] = parsed;
        }
        continue;
      }

      if (kind === 'string') {
        built[prop] = raw;
        continue;
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        errors[key] = '올바른 JSON 형식으로 입력해 주세요.';
        continue;
      }
      if (kind === 'array' && !Array.isArray(parsed)) {
        errors[key] = 'JSON 배열([ ]) 형식으로 입력해 주세요.';
        continue;
      }
      if (kind === 'object' && (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed))) {
        errors[key] = 'JSON 객체({ }) 형식으로 입력해 주세요.';
        continue;
      }
      built[prop] = parsed;
    }

    argumentsByRef[ref] = built;
  }

  return { argumentsByRef, errors };
}

const STATUS_LABEL: Record<ToolCheckResult['status'], { tone: BadgeTone; label: string }> = {
  ...CHECK_STATUS,
  SKIPPED: { tone: 'neutral', label: '건너뜀' },
};

/**
 * 2단계(대화 테스트) 안의 선택적 보조 기능 — 선택한 도구 전부를 모델 판단 없이
 * 순서대로 직접 불러 본다.
 *
 * 채팅식 테스트는 모델이 어떤 도구를 부를지 스스로 정해서, 데이터가 없거나
 * 모델이 안 부른 도구는 확인이 안 된다. 이 패널은 그 빈틈을 메운다.
 */
export function ToolCheckPanel({
  token,
  allTools,
  toolRefs,
  onToggleTool,
  onOpenToolPicker,
  autoRun = false,
}: ToolCheckPanelProps) {
  const [rawArgs, setRawArgs] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [checking, setChecking] = useState(false);
  const [results, setResults] = useState<ToolCheckResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toolByRef = new Map(allTools.map((tool) => [tool.tool_ref, tool]));

  function setFieldValue(key: string, value: string) {
    setRawArgs((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  async function run() {
    if (!token || toolRefs.length === 0 || checking) return;
    setError(null);

    const { argumentsByRef, errors } = buildArguments(toolRefs, toolByRef, rawArgs);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setChecking(true);
    setResults(null);
    try {
      const response = await checkBuilderTools(token, { tool_refs: toolRefs, arguments: argumentsByRef });
      setResults(response.results);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '도구 확인에 실패했습니다.');
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    if (autoRun && toolRefs.length > 0) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <p className={pageStyles.help}>
        선택한 도구 전부를 모델 판단 없이 순서대로 직접 불러 봅니다. 모델이 안 불러서 확인이 안
        되는 상황을 없애려는 것입니다. 승인이 필요한 도구는 여기서도 실제로 실행하지 않고
        시뮬레이션만 합니다.
      </p>

      <div className={pageStyles.field}>
        <span className={pageStyles.fieldLabel}>사용할 도구</span>
        <div className={pageStyles.toolSummary}>
          {toolRefs.length === 0 && <p className={pageStyles.help}>아직 고른 도구가 없습니다.</p>}
          {toolRefs.map((ref) => {
            const label = toolByRef.get(ref)?.name ?? ref;
            return (
              <span key={ref} className={pageStyles.toolChip}>
                {label}
                <button type="button" aria-label={`${label} 빼기`} onClick={() => onToggleTool(ref)}>
                  <Icon name="x" size={11} />
                </button>
              </span>
            );
          })}
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onOpenToolPicker}>
          도구 추가/제외
        </Button>
      </div>

      {toolRefs.map((ref) => {
        const tool = toolByRef.get(ref);
        const properties = tool?.input_schema?.properties ?? {};
        const propNames = Object.keys(properties);
        const required = new Set(tool?.input_schema?.required ?? []);
        return (
          <div key={ref} className={styles.step}>
            <div className={styles.stepBody}>
              <span className={styles.stepName}>{tool?.name ?? ref}</span>
              {propNames.length === 0 && <span className={pageStyles.help}>입력 값이 필요 없습니다.</span>}
              {propNames.map((prop) => {
                const key = `${ref}::${prop}`;
                const kind = fieldKind(properties[prop].type);
                return (
                  <Input
                    key={key}
                    label={`${prop}${required.has(prop) ? ' *' : ''}`}
                    id={`tool-check-${key}`}
                    name={key}
                    placeholder={
                      kind === 'array' || kind === 'object' || kind === 'json'
                        ? '{ } 또는 [ ] 형식의 JSON'
                        : properties[prop].description || ''
                    }
                    value={rawArgs[key] ?? ''}
                    error={fieldErrors[key]}
                    onChange={(event) => setFieldValue(key, event.target.value)}
                  />
                );
              })}
            </div>
          </div>
        );
      })}

      <Button onClick={run} disabled={checking || toolRefs.length === 0}>
        {checking ? '확인하는 중…' : results ? '다시 확인' : '전체 도구 확인'}
      </Button>
      {error && <p className={pageStyles.error}>{error}</p>}

      {results && (
        <div className={styles.trace}>
          {results.map((result, index) => {
            const chip = STATUS_LABEL[result.status];
            return (
              <div key={`${result.tool_ref}-${index}`} className={styles.step}>
                <span className={styles.stepOrder}>{index + 1}</span>
                <div className={styles.stepBody}>
                  <span className={styles.stepName}>
                    {result.tool_name}
                    <Badge tone={chip.tone}>{chip.label}</Badge>
                  </span>
                  {result.detail && <span className={pageStyles.help}>{result.detail}</span>}
                  {result.status === 'FAILED' && result.error_code && (
                    <span className={pageStyles.help}>오류: {result.error_code}</span>
                  )}
                  {result.arguments && Object.keys(result.arguments).length > 0 && (
                    <pre className={styles.args}>{JSON.stringify(result.arguments, null, 2)}</pre>
                  )}
                  {result.status === 'OK' && result.output !== undefined && (
                    <pre className={styles.args}>{JSON.stringify(result.output, null, 2)}</pre>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
