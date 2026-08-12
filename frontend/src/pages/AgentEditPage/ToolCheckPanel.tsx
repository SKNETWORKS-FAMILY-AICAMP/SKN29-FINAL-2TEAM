import { useEffect, useState } from 'react';
import { Badge, Button, Input } from '../../components';
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
  /** 마운트 시 한 번 자동으로 확인을 돌린다 — 검증 단계와 나란히 자동 실행될 때 쓴다. */
  autoRun?: boolean;
}

type FieldKind = 'string' | 'number' | 'json';

function fieldKind(type: string | undefined): FieldKind {
  if (type === 'string') return 'string';
  if (type === 'integer' || type === 'number') return 'number';
  return 'json';
}

const STATUS_LABEL: Record<ToolCheckResult['status'], { tone: BadgeTone; label: string }> = {
  OK: { tone: 'success', label: '성공' },
  FAILED: { tone: 'danger', label: '실패' },
  SIMULATED: { tone: 'warning', label: '시뮬레이션 (실제로 부르지 않음)' },
  SKIPPED: { tone: 'neutral', label: '건너뜀' },
};

/**
 * 2단계(대화 테스트) 안의 선택적 보조 기능 — 선택한 도구 전부를 모델 판단 없이
 * 순서대로 직접 불러 본다.
 *
 * 채팅식 테스트는 모델이 어떤 도구를 부를지 스스로 정해서, 데이터가 없거나
 * 모델이 안 부른 도구는 확인이 안 된다. 이 패널은 그 빈틈을 메운다.
 */
export function ToolCheckPanel({ token, allTools, toolRefs, autoRun = false }: ToolCheckPanelProps) {
  const [rawArgs, setRawArgs] = useState<Record<string, string>>({});
  const [checking, setChecking] = useState(false);
  const [results, setResults] = useState<ToolCheckResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toolByRef = new Map(allTools.map((tool) => [tool.tool_ref, tool]));

  async function run() {
    if (!token || toolRefs.length === 0 || checking) return;
    setChecking(true);
    setResults(null);
    setError(null);

    const argumentsByRef: Record<string, Record<string, unknown>> = {};
    for (const ref of toolRefs) {
      const properties = toolByRef.get(ref)?.input_schema?.properties ?? {};
      const built: Record<string, unknown> = {};
      for (const prop of Object.keys(properties)) {
        const raw = rawArgs[`${ref}::${prop}`];
        if (raw === undefined || raw === '') continue;
        const kind = fieldKind(properties[prop].type);
        if (kind === 'number') {
          const parsed = Number(raw);
          if (!Number.isNaN(parsed)) built[prop] = parsed;
        } else if (kind === 'json') {
          try {
            built[prop] = JSON.parse(raw);
          } catch {
            // 잘못된 JSON은 그냥 뺀다.
          }
        } else {
          built[prop] = raw;
        }
      }
      argumentsByRef[ref] = built;
    }

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
      {toolRefs.length === 0 && <p className={pageStyles.help}>먼저 도구를 선택해 주세요.</p>}

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
                    placeholder={kind === 'json' ? '{ } 또는 [ ] 형식의 JSON' : properties[prop].description || ''}
                    value={rawArgs[key] ?? ''}
                    onChange={(event) => setRawArgs((prev) => ({ ...prev, [key]: event.target.value }))}
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
