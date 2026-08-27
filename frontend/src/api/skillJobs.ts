import { apiRequest, ApiError } from './client';

/**
 * 스킬 등록 검증 job — 정본: 03_스킬_검증_등록_설계.md §7/§9/§14.
 *
 * `skill_register`(채팅 도구)나 설정 화면에서 스킬을 등록하면 이제 즉시
 * SKILL.md가 써지지 않는다. `skill_registration_job` 하나가 생기고, 별도
 * 워커(`python manage.py skill_validation_worker`)가 형식·라우팅·행동
 * 검증을 통과시킨 뒤에만 실제로 등록된다.
 * `SkillJobCenter`가 이 값을 폴링해서 진행 카드를 그린다.
 */

/** 정본 §7 `stage` 5단계와 정확히 같은 순서 — `stage_index`가 이 안에서 몇 번째인지 가리킨다. */
export const SKILL_JOB_STAGES = [
  'WAITING',
  'CHECKING',
  'PREPARING_TESTS',
  'TESTING',
  'PUBLISHING',
] as const;

export type SkillJobStage = (typeof SKILL_JOB_STAGES)[number];
export type SkillJobStatus = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCEL_REQUESTED' | 'CANCELED';

export interface SkillJob {
  job_id: string;
  skill_name: string;
  operation: 'CREATE' | 'UPDATE' | 'RETRY';
  attempt: number;
  retry_of_job_id: string | null;
  status: SkillJobStatus;
  stage: SkillJobStage;
  stage_index: number;
  stage_count: number;
  failure_code: string | null;
  failure_summary: string | null;
  failure_details: Record<string, unknown> | null;
  failure_category: 'SYSTEM' | 'CHANGED_CONTEXT' | 'BASIC_INFO' | 'SKILL_QUALITY' | null;
  /** 5단계 안에서 워커가 지금 수행 중인 관찰 가능한 세부 작업. */
  progress_message: string;
  progress_current: number | null;
  progress_total: number | null;
  progress_events: Array<{
    message: string;
    at: string;
    current: number | null;
    total: number | null;
  }>;
  created_at: string | null;
  started_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  worker_available: boolean | null;
  queue_delayed: boolean;
  queue_age_seconds: number;
  waiting_reason: string | null;
  model_call_count: number;
  estimated_cost_usd: number;
  /** 목록 응답에는 없고 단건 상세 조회에만 포함된다. */
  candidate_document?: {
    name: string;
    description: string;
    body: string;
    enabled?: boolean;
  } | null;
}

export interface SkillJobFailureCopy {
  reason: string;
  suggestion: string;
}

export interface SkillJobRepairCopy {
  missing: string;
  question: string;
  placeholder: string;
}

/** 내부 평가 지표를 숨기고 사용자가 고칠 수 있는 말로 바꾼다. */
export function getSkillJobFailureCopy(job: SkillJob): SkillJobFailureCopy {
  const details = job.failure_details ?? {};
  const metric = (name: string): number | null =>
    typeof details[name] === 'number' ? (details[name] as number) : null;

  switch (job.failure_code) {
    case 'TRIGGER_ACCURACY_TOO_LOW': {
      const missedWhenNeeded = (metric('recall') ?? 1) < 0.8;
      const activatedTooBroadly =
        (metric('precision') ?? 1) < 0.8 || (metric('false_activation_rate') ?? 0) > 0.2;
      const didNotFollowProcedure = (metric('behavior_pass_rate') ?? 1) < 0.8;
      if (didNotFollowProcedure && (missedWhenNeeded || activatedTooBroadly)) {
        return {
          reason: `${missedWhenNeeded ? '필요한 요청에서 안정적으로 선택되지 않았고, ' : ''}${activatedTooBroadly ? '비슷하지만 관계없는 요청에서도 선택되었으며, ' : ''}선택된 뒤에도 작성한 절차와 결과 기준을 충분히 따르지 못했습니다.`,
          suggestion: '사용 조건과 제외 조건을 더 분명히 나누고, 결과에 반드시 들어갈 내용과 하면 안 되는 행동을 짧은 예시로 보완해 주세요.',
        };
      }
      if (didNotFollowProcedure) {
        return {
          reason: '스킬은 선택되었지만 작성한 절차나 결과 기준을 답변에서 안정적으로 지키지 못했습니다.',
          suggestion: '처리 순서를 짧고 분명하게 정리하고, 정상 결과의 예시와 반드시 지켜야 할 항목을 추가해 주세요.',
        };
      }
      if (missedWhenNeeded && activatedTooBroadly) {
        return {
          reason: '이 스킬을 써야 하는 요청에서는 잘 선택되지 않았고, 비슷하지만 관계없는 요청에서도 선택되었습니다.',
          suggestion: '설명에 “어떤 요청일 때만 사용하는지”와 “어떤 요청에는 사용하지 않는지”를 함께 적고, 실제 사용 예시를 본문에 추가해 주세요.',
        };
      }
      if (missedWhenNeeded) {
        return {
          reason: '이 스킬이 필요한 요청에서도 에이전트가 스킬을 안정적으로 선택하지 못했습니다.',
          suggestion: '사용자가 실제로 말할 표현을 설명에 구체적으로 넣어 주세요. 비슷한 요청 표현과 처리할 입력·결과도 본문에 적으면 도움이 됩니다.',
        };
      }
      return {
        reason: '이 스킬과 직접 관계없는 비슷한 요청에서도 스킬이 선택되었습니다.',
        suggestion: '설명의 사용 범위를 더 좁혀 주세요. 반드시 만족해야 하는 조건과 사용하지 않아야 할 경우를 명확히 적어 주세요.',
      };
    }
    case 'SKILL_NAME_CONFLICT':
      return {
        reason: `이미 '${job.skill_name}' 이름의 스킬이 있어 같은 이름으로 등록할 수 없습니다.`,
        suggestion: '기존 스킬을 수정하거나, 무엇이 다른 스킬인지 드러나는 새 이름으로 바꿔 주세요.',
      };
    case 'INVALID_SKILL_FORMAT':
      return {
        reason: job.failure_summary || '스킬의 이름, 설명 또는 내용 형식이 등록 기준에 맞지 않습니다.',
        suggestion: '이름과 설명을 간결하게 정리하고, 본문에는 에이전트가 실제로 따라야 할 순서와 주의사항을 적어 주세요.',
      };
    case 'TEST_GENERATION_FAILED':
    case 'TEST_CASE_REVIEW_FAILED':
      return {
        reason: '스킬의 사용 상황이 충분히 구체적이지 않아 검증할 상황을 만들지 못했습니다.',
        suggestion: '언제 사용하고 언제 사용하지 않는지, 입력과 원하는 결과가 무엇인지 조금 더 구체적으로 적어 주세요.',
      };
    case 'EVAL_INFRA_ERROR':
    case 'EVAL_JOB_TIMEOUT':
    case 'WORKER_INTERNAL_ERROR':
    case 'EVAL_BUDGET_EXCEEDED':
    case 'EVAL_PROVIDER_CAPACITY_TIMEOUT':
      return {
        reason: '스킬 내용이 아니라 검증 시스템의 일시적인 문제로 검증을 완료하지 못했습니다.',
        suggestion: '내용을 바꾸지 않고 잠시 후 다시 시도해 주세요. 계속 실패하면 관리자에게 알려 주세요.',
      };
    case 'STALE_CANDIDATE':
    case 'STALE_EVAL_CONTEXT':
      return {
        reason: '검증하는 동안 같은 스킬의 내용이 다른 곳에서 변경되었습니다.',
        suggestion: '최신 스킬 내용을 확인한 뒤 보완 내용을 다시 적용해 주세요.',
      };
    default:
      return {
        reason: job.failure_summary || '스킬 검증을 완료하지 못했습니다.',
        suggestion: '스킬을 언제 사용하고 어떤 결과를 내야 하는지 더 구체적으로 적어서 다시 시도해 주세요.',
      };
  }
}

/** 보완 창에서 사용자가 실제로 답할 수 있도록 부족한 정보와 질문을 구체화한다. */
export function getSkillJobRepairCopy(job: SkillJob): SkillJobRepairCopy {
  const details = job.failure_details ?? {};
  const metric = (name: string): number | null =>
    typeof details[name] === 'number' ? (details[name] as number) : null;

  if (job.failure_code === 'TRIGGER_ACCURACY_TOO_LOW') {
    const missedWhenNeeded = (metric('recall') ?? 1) < 0.8;
    const activatedTooBroadly =
      (metric('precision') ?? 1) < 0.8 || (metric('false_activation_rate') ?? 0) > 0.2;
    const didNotFollowProcedure = (metric('behavior_pass_rate') ?? 1) < 0.8;
    if (didNotFollowProcedure) {
      return {
        missing: '현재 초안에는 사용 범위뿐 아니라, 결과가 올바른지 바로 확인할 수 있는 필수 항목과 잘못된 결과의 기준도 부족합니다.',
        question: '이 스킬의 결과에 반드시 들어가야 할 내용과 절대로 하면 안 되는 행동을 실제 예시와 함께 알려주세요.',
        placeholder: '정상 결과에는 …가 반드시 있어야 해. …는 하지 말고, 예시는 …처럼 보여줘.',
      };
    }
    if (missedWhenNeeded && activatedTooBroadly) {
      return {
        missing: '현재 설명에는 이 스킬이 맡을 요청의 공통 조건과, 겉보기에는 비슷하지만 다른 작업을 구분할 기준이 부족합니다.',
        question: '어떤 요청은 이 스킬이 맡아야 하고, 어떤 비슷한 요청은 맡지 않아야 하나요?',
        placeholder: '맡아야 하는 요청과 맡지 않아야 하는 비슷한 요청을 각각 한 가지씩 적어주세요.',
      };
    }
    if (missedWhenNeeded) {
      return {
        missing: '현재 설명에는 사용자가 어떤 입력을 주고 어떤 결과를 요청할 때 이 스킬을 선택해야 하는지가 충분히 드러나지 않습니다.',
        question: '사용자는 보통 무엇을 주고, 어떤 결과를 요청할 때 이 스킬을 사용하나요?',
        placeholder: '사용자가 주는 입력과 원하는 결과를 실제 요청하듯 적어주세요.',
      };
    }
    return {
      missing: '현재 설명만으로는 이 스킬과 가까운 다른 작업의 경계가 분명하지 않습니다.',
      question: '이 스킬이 처리할 범위의 끝은 어디이며, 가장 헷갈리기 쉬운 다른 작업은 무엇인가요?',
      placeholder: '처리할 범위와 처리하지 않을 가까운 작업을 함께 적어주세요.',
    };
  }

  switch (job.failure_code) {
    case 'TEST_GENERATION_FAILED':
    case 'TEST_CASE_REVIEW_FAILED':
      return {
        missing: '현재 초안에는 실제 사용 상황을 만들 만큼 입력, 처리 기준, 결과 형태가 충분히 구체적으로 적혀 있지 않습니다.',
        question: '이 스킬이 받을 입력, 처리할 순서, 최종 결과 형태를 순서대로 알려주세요.',
        placeholder: '입력은 …, 처리 순서는 …, 결과는 … 형태로 보여줘.',
      };
    case 'SKILL_NAME_CONFLICT':
      return {
        missing: '현재 이름이 이미 등록된 스킬과 같아 두 스킬을 구분할 수 없습니다.',
        question: '기존 스킬과 다른 점이 드러나는 새 이름이나 용도를 알려주세요.',
        placeholder: '기존 스킬과 다른 대상이나 결과를 적어주세요.',
      };
    case 'INVALID_SKILL_FORMAT':
      return {
        missing: '현재 초안의 이름·설명·본문 중 하나가 등록 형식에 맞지 않거나 실행 절차가 부족합니다.',
        question: '에이전트가 실제로 따라야 할 순서와 꼭 지켜야 할 규칙을 알려주세요.',
        placeholder: '먼저 …하고, 다음으로 …한다. …인 경우에는 …한다.',
      };
    case 'EVAL_INFRA_ERROR':
    case 'EVAL_JOB_TIMEOUT':
    case 'WORKER_INTERNAL_ERROR':
    case 'EVAL_BUDGET_EXCEEDED':
    case 'EVAL_PROVIDER_CAPACITY_TIMEOUT':
      return {
        missing: '스킬 내용에서 빠진 정보는 확인되지 않았습니다. 검증 시스템의 일시적인 문제였습니다.',
        question: '내용을 바꾸지 않고 다시 만들려면 그대로 진행한다고 적어주세요.',
        placeholder: '내용은 그대로 두고 다시 만들어줘.',
      };
    case 'STALE_CANDIDATE':
    case 'STALE_EVAL_CONTEXT':
      return {
        missing: '검증을 시작한 뒤 같은 스킬이 변경되어, 어느 내용을 기준으로 할지 확정할 수 없습니다.',
        question: '아래 기존 초안을 기준으로 다시 만들지, 변경할 내용을 반영할지 알려주세요.',
        placeholder: '아래 초안을 기준으로 다시 만들거나, 바꿀 내용을 적어주세요.',
      };
    default: {
      const summary = `${job.failure_summary ?? ''} ${job.failure_code ?? ''}`.toLowerCase();
      if (summary.includes('결과') || summary.includes('오류') || summary.includes('응답')) {
        return {
          missing: '현재 본문에는 정상적인 결과의 모습과 잘못된 결과를 판단할 기준, 문제가 생겼을 때의 처리 방법이 부족합니다.',
          question: '정상 결과에 반드시 들어갈 내용과 오류라고 볼 상황, 오류일 때 처리 방법을 알려주세요.',
          placeholder: '정상 결과에는 …가 있어야 하고, …이면 오류로 본다. 오류일 때는 …한다.',
        };
      }
      return {
        missing: '현재 초안만으로는 에이전트가 같은 방식으로 반복 수행할 수 있는 입력, 절차 또는 결과 기준이 부족합니다.',
        question: '현재 내용에 추가해야 할 입력 조건, 처리 순서 또는 결과 기준을 알려주세요.',
        placeholder: '추가할 조건이나 처리 방법을 구체적으로 적어주세요.',
      };
    }
  }
}

/** 진행 중이거나(QUEUED/RUNNING) 취소 처리 중인(CANCEL_REQUESTED) job. */
export function isSkillJobOpen(job: SkillJob): boolean {
  return job.status === 'QUEUED' || job.status === 'RUNNING' || job.status === 'CANCEL_REQUESTED';
}

/** 성공·실패·취소로 끝나 더는 안 바뀌는 job. */
export function isSkillJobTerminal(job: SkillJob): boolean {
  return job.status === 'SUCCEEDED' || job.status === 'FAILED' || job.status === 'CANCELED';
}

/** 내 열린 job 목록 — `SkillJobCenter`가 새로고침 후 복원할 때 쓴다(§13). */
export function listOpenSkillJobs(token: string) {
  return apiRequest<SkillJob[]>('/skill-registration-jobs/?open=true', { token });
}

/** 설정 > 스킬에서 진행 중·실패한 검증 작업을 함께 보여 줄 때 쓴다. */
export function listSkillJobs(token: string) {
  return apiRequest<SkillJob[]>('/skill-registration-jobs/', { token });
}

export function getSkillJob(token: string, jobId: string) {
  return apiRequest<SkillJob>(`/skill-registration-jobs/${jobId}/`, { token });
}

export function cancelSkillJob(token: string, jobId: string) {
  return apiRequest<SkillJob>(`/skill-registration-jobs/${jobId}/cancel/`, { method: 'POST', token });
}

export function retrySkillJob(
  token: string,
  jobId: string,
  candidateDocument?: { name: string; description: string; body: string },
) {
  return apiRequest<SkillJob>(`/skill-registration-jobs/${jobId}/retry/`, {
    method: 'POST', token, body: candidateDocument ? { candidate_document: candidateDocument } : {},
  });
}

/** 실패·취소로 끝난 job만 지울 수 있다 — 진행 중이거나 성공한 job은 서버가 거부한다. */
export function deleteSkillJob(token: string, jobId: string) {
  return apiRequest<void>(`/skill-registration-jobs/${jobId}/`, { method: 'DELETE', token });
}

export { ApiError };
