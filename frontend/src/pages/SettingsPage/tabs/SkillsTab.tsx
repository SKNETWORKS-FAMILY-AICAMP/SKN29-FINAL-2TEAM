import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Badge, Button, Icon, InfoNote, Input, Modal, ToggleSwitch, useToast } from '../../../components';
import { listAgentVersions } from '../../../api/agentVersions';
import {
  ApiError,
  createMySkill,
  deleteMySkill,
  deleteTeamSkill,
  getMySkill,
  getTeamSkill,
  importTeamSkill,
  listMySkills,
  listTeamSkills,
  shareMySkill,
  stopSharingMySkill,
  setMySkillEnabled,
  submitMySkillUpdate,
} from '../../../api/skills';
import type { Skill } from '../../../api/skills';
import {
  cancelSkillJob,
  deleteSkillJob,
  getSkillJob,
  getSkillJobFailureCopy,
  getSkillJobRepairCopy,
  isSkillJobOpen,
  listSkillJobs,
  retrySkillJob,
} from '../../../api/skillJobs';
import type { SkillJob, SkillJobStage } from '../../../api/skillJobs';
import {
  confirmMessage,
  createSession,
  deleteSession,
  setSessionToolRefs,
  streamMessage,
} from '../../../api/chat';
import type { ChatEvent } from '../../../api/chat';
import { ASK_FOLLOWUP_TOOL_NAME } from '../../ChatPage/liveChat';
import { loadSessionToken } from '../../../utils/session';
import { notifySkillJobRemoved, notifySkillJobStarted } from '../../../utils/skillJobSignal';
import { josa } from '../../../utils/josa';
import styles from './tabs.module.css';

/**
 * 「스킬」 탭 — 업무 절차를 적어 두면 에이전트가 필요할 때 골라 읽는다.
 *
 * **사람의 「기술 스택」과 다른 것이다.** 그쪽은 HR 이 아는 보유 역량이고
 * (`SkillList.tsx`), 여기는 「구매 검토는 이렇게 한다」 같은 절차 문서다.
 *
 * ## 서버가 붙었다 (2026-08-22)
 *
 * 저장·조회는 `apps/skills`(내부적으로 `services.agent_runtime.skills.service`
 * — 채팅의 `skill_register` 도구와 같은 함수)가 한다. 404 를 「준비 중」으로
 * 따로 그리던 자리는 이제 없다 — 진짜 실패만 오류로 보인다.
 *
 * ## 활성화된 스킬 / 내 스킬 / 팀 스킬
 *
 * 안쪽 탭 셋으로 나눈다(`MyFilesTab.tsx`의 내 파일/공유 받은 파일과 같은
 * 자리). **개인 스킬만 에이전트가 사용한다.** 팀 스킬은 팀원이 공유한
 * 카탈로그이며, 다른 팀원이 가져오면 독립 개인 사본이 된다. 원 공유자의
 * 비활성화·공유 중지와 팀장의 카탈로그 삭제는 이미 가져간 사본에 영향을
 * 주지 않는다.
 *
 * **「활성화된 스킬」은 새 데이터가 아니라 필터다**(2026-08-26). 맨 앞
 * 탭이자 기본 화면이다 — "지금 에이전트가 실제로 쓰는 스킬이 뭔지"가
 * 가장 자주 확인하는 정보라서다. `personalSkills`를 `enabled`로 거른
 * 것과 완전히 같은 목록이라(`viewTabToScope`), 수정·삭제·공유·끄기 같은
 * 행동은 「내 스킬」 탭과 똑같이 그대로 된다 — 끄면 이 탭에서는 바로
 * 사라지고 「내 스킬」에는 비활성으로 남는다. 예전에 「내 스킬」 탭
 * 안에 있던 활성화된 스킬/팀에 공유한 스킬/팀 스킬에서 가져온 스킬 세
 * 필터는 지웠다 — 첫 번째는 이 탭으로 대체됐고, 나머지 둘은 각 행의
 * "공유중"/"팀 스킬" 배지로 이미 보이는 정보라 필터로 한 번 더 물을
 * 필요가 없었다.
 *
 * ## 만드는 두 가지 방법
 *
 * 「파일 업로드」 탭은 Claude 의 스킬 업로드와 같은 방식이다 — **이름은
 * 사람이 칸에 적는 것이 아니라 파일의 frontmatter(`name:`)에서 그대로
 * 읽는다.** `.md` 파일 하나를 읽어 이름·설명·본문을 그 자리에서 채운다.
 * 이름이 같은 스킬이 이미 있으면 서버가 덮어쓰지 않고 거부한다(409) — 그
 * 문구를 그대로 토스트로 보여준다.
 *
 * 「직접 작성」 탭은 **이름·설명·내용 칸을 더 안 받는다**(2026-08-24, 이 화면
 * 안에서 바로 만들도록 재작업 2026-08-24). 만들 스킬을 한 문장으로 적으면
 * 이 화면을 떠나지 않고 그대로 채팅 세션 하나를 조용히 열어(`createSession`)
 * `skill-creator` 내장 스킬에게 그 문장을 보낸다 — 이름·설명을 스스로 짓고,
 * 정보가 부족하면 `skill_creator_ask_followup`으로 한 번에 하나씩 되묻고,
 * 마지막엔 `skill_register` 확인 카드를 이 모달 안에 그대로 그린다
 * (`builtin_content.py`의 절차, 아래 `creation` 상태 기계). 여기서 폼으로
 * 다시 받으면 그 절차와 같은 판단을 사람이 두 번 하게 된다 — 그래서 안
 * 받는다. 수정(`editing.skill !== null`)은 이 대상이 아니다 — 이미 있는
 * 스킬을 고치는 것은 "만들기 절차"가 아니라 값 하나를 바꾸는 것이라 폼이
 * 그대로 맞다.
 *
 * ## 이름은 한 번 정하면 못 바꾼다
 *
 * 저장 경로 자체가 이름으로 정해져서다(`api/skills.ts` 참고). 수정 화면에서는
 * 이름 칸을 잠근다 — 바꿀 수 있는 것처럼 보여 주고 서버가 조용히 무시하면
 * 더 나쁘다.
 *
 * ## 업로드 용량 (2026-08-22)
 *
 * `deepagents`가 SKILL.md 파일 하나에 진짜로 두는 상한은 10MB인데, 넘기면
 * 사람에게 아무 신호 없이 그 스킬이 조용히 목록에서 빠진다(`service.py`의
 * `MAX_SKILL_BODY_BYTES` 주석 참고). 여기서는 그 상한의 1/50인 200KB로
 * 미리 막는다 — 화면에서 바로 알려주지, 나중에 에이전트가 못 읽는 채로
 * 조용히 사라지게 두지 않는다.
 */

type Scope = 'personal' | 'team';
/**
 * 상단 내비게이션 탭(2026-08-26). `Scope`와 분리한다 — 「활성화된 스킬」은
 * 새 데이터 소스가 아니라 `personalSkills`를 `enabled`로 한 번 더 거른
 * 화면일 뿐이라, 만들기·수정·삭제·공유 같은 실제 동작은 전부 `scope`가
 * 여전히 `'personal'`인 채로(`viewTabToScope` 아래) 그대로 동작해야 한다.
 */
type ViewTab = 'active' | 'personal' | 'team';

function viewTabToScope(viewTab: ViewTab): Scope {
  return viewTab === 'team' ? 'team' : 'personal';
}

type CreateMode = 'write' | 'upload';

const JOB_STAGE_LABELS: Record<SkillJobStage, string> = {
  WAITING: '검증 대기',
  CHECKING: '기본 정보 확인',
  PREPARING_TESTS: '테스트 준비',
  TESTING: '스킬 테스트',
  PUBLISHING: '스킬 등록',
};

function jobStatusLabel(job: SkillJob): string {
  switch (job.status) {
    case 'SUCCEEDED':
      return '등록 완료';
    case 'FAILED':
      return '등록 실패';
    case 'CANCEL_REQUESTED':
      return '취소 중';
    case 'CANCELED':
      return '취소됨';
    default:
      return JOB_STAGE_LABELS[job.stage];
  }
}

function jobStatusTone(job: SkillJob): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (job.status === 'FAILED') return 'danger';
  if (job.status === 'SUCCEEDED') return 'success';
  if (job.status === 'CANCELED') return 'neutral';
  if (job.status === 'CANCEL_REQUESTED') return 'warning';
  return 'info';
}

/** 같은 반복 작업의 3/36, 6/36…은 한 줄로 합쳐 상세 로그를 읽기 쉽게 한다. */
function recentProgressEvents(job: SkillJob) {
  const collapsed: SkillJob['progress_events'] = [];
  for (const event of job.progress_events.slice(0, -1)) {
    const last = collapsed[collapsed.length - 1];
    if (last?.message === event.message) collapsed[collapsed.length - 1] = event;
    else collapsed.push(event);
  }
  return collapsed.slice(-5);
}


/** 만들기와 수정이 같은 폼을 쓴다. `null` 이면 폼이 닫혀 있다. */
type Editing = {
  scope: Scope;
  skill: Skill | null;
  name: string;
  description: string;
  body: string;
  mode: CreateMode;
  /** 업로드 탭에서 고른 파일 이름. 미리보기 표시 여부를 가른다. */
  uploadFileName: string | null;
  uploadSourceContent: string | null;
  /** 업로드한 파일을 못 읽었을 때의 사유. */
  uploadError: string | null;
  /**
   * 「직접 작성」 탭에서 새로 만들 때 받는 한 문장(2026-08-24). 이름·설명·
   * 내용을 여기서 안 받고, 이 문장을 들고 채팅(`/chat?ask=…`)으로 넘어간다
   * — `name`/`description`/`body`는 그 경로에서는 안 쓴다(수정 폼에서만
   * 쓴다).
   */
  sentence: string;
} | null;

/**
 * 「직접 작성」 새로 만들기 상태 기계(2026-08-24). 채팅으로 넘기지 않고 이
 * 모달 안에서 그대로 돌린다 — `ChatPage.tsx`의 `liveChat.ts` 리듀서를 그대로
 * 쓰지 않는 이유는, 그쪽은 대화 전체(과거 턴·추론·도구 진행률 카드)를 그리는
 * 상태 기계라 이 모달에 필요한 건 "질문 하나·확인 카드 하나·최종 결과"뿐이라
 * 훨씬 작다. 대신 이벤트 계약(`ChatEvent`, `ASK_FOLLOWUP_TOOL_NAME`)은 그대로
 * 재사용한다 — 서버가 보내는 모양은 채팅과 똑같기 때문이다.
 */
type CreationPhase = 'running' | 'ask' | 'confirm' | 'done' | 'cancelled' | 'error';

interface CreationAction {
  name: string;
  args: Record<string, unknown>;
}

interface CreationState {
  phase: CreationPhase;
  sessionId: string | null;
  /** `phase === 'ask'`일 때의 되묻기 질문. */
  question: string | null;
  /** `phase === 'confirm'`일 때 승인을 기다리는 도구 호출들(보통 `skill_register` 하나). */
  actions: CreationAction[] | null;
  /** `phase === 'done'`일 때, 등록까지 마친 모델의 마지막 답. */
  finalText: string | null;
  /** 실제로 `skill_register`가 성공했는가. `result` 이벤트의 완료 판정에 쓴다. */
  registered: boolean;
  /** 사용자가 등록 확인 카드에서 거절했는가. */
  registrationCancelled: boolean;
  /** `phase === 'error'`일 때 사유. */
  errorText: string | null;
  /**
   * `phase === 'running'`일 때 **왜** 도는지(2026-08-24 UX 점검 — 거절을
   * 눌러도 제목·본문이 항상 "스킬을 만드는 중…"이라, 실제로는 취소를
   * 반영하는 중인데 마치 새로 만드는 것처럼 보이고, 그 동안 모달을 닫을
   * 수도 없었다). 이유별로 제목·본문 문구와 닫기 가능 여부를 가른다.
   */
  runningReason: 'start' | 'answer' | 'approve' | 'cancel' | null;
}

function emptyEditing(scope: Scope): NonNullable<Editing> {
  return {
    scope,
    skill: null,
    name: '',
    description: '',
    body: '',
    mode: 'write',
    uploadFileName: null,
    uploadSourceContent: null,
    uploadError: null,
    sentence: '',
  };
}

/**
 * 업로드한 `.md` 의 frontmatter 를 미리 읽어 화면에 보여 주기 위한 것.
 *
 * **최종 판단은 서버가 한다** — `services.agent_runtime.skills.service.parse_skill_md`
 * 와 같은 모양(`---\nname: …\ndescription: …\n---\n\n본문`)을 가볍게 흉내만
 * 낸다. 여기서 걸러도 서버가 다시 검사하므로, 여기 로직이 느슨해도 안전하다 —
 * 대신 사람에게는 올리자마자 무엇이 저장될지 보여 준다.
 */
function parseSkillMdPreview(content: string): { name: string; description: string; body: string } {
  const trimmed = content.replace(/^﻿/, '');
  if (!trimmed.startsWith('---')) {
    throw new Error('SKILL.md 형식이 아닙니다. 맨 위가 ---로 시작해야 합니다.');
  }
  const rest = trimmed.slice(3);
  const closeIndex = rest.indexOf('\n---');
  if (closeIndex === -1) {
    throw new Error('정보 칸(---)이 닫히지 않았습니다.');
  }
  const frontmatter = rest.slice(0, closeIndex);
  const body = rest
    .slice(closeIndex + 4)
    .replace(/^\n+/, '')
    .replace(/\n+$/, '');

  let name = '';
  let description = '';
  for (const line of frontmatter.split('\n')) {
    const match = line.match(/^([a-zA-Z_]+):\s*(.*)$/);
    if (!match) continue;
    const value = match[2].trim().replace(/^['"]|['"]$/g, '');
    if (match[1] === 'name') name = value;
    if (match[1] === 'description') description = value;
  }

  if (!name) throw new Error('파일에 이름(name)이 없습니다.');
  if (!description) throw new Error('파일에 설명(description)이 없습니다.');

  return { name, description, body };
}

const UPLOAD_ACCEPT = '.md';

/**
 * 스킬 본문 용량 상한. **서버 `service.py`의 `MAX_SKILL_BODY_BYTES`와 같은
 * 값이다** — 여기서 미리 막아야 파일을 다 읽고 나서야(업로드) 혹은 저장을
 * 눌러서야(직접 작성) 서버 오류로 아는 일이 없다. 값을 바꿀 때는 두 곳을
 * 같이 바꾼다.
 */
const MAX_SKILL_BODY_BYTES = 200 * 1024;

function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

function formatKB(bytes: number): string {
  return `${Math.ceil(bytes / 1024)}KB`;
}

export function SkillsTab() {
  const { showToast } = useToast();
  const token = loadSessionToken();
  const [searchParams, setSearchParams] = useSearchParams();

  // 「활성화된 스킬」을 맨 앞 탭으로 둔다(2026-08-26) — 지금 에이전트가
  // 실제로 쓰는 스킬이 뭔지가 가장 자주 확인하는 정보라 기본 화면으로 둔다.
  const [viewTab, setViewTab] = useState<ViewTab>('active');
  const scope = viewTabToScope(viewTab);
  const [personalSkills, setPersonalSkills] = useState<Skill[]>([]);
  const [teamSkills, setTeamSkills] = useState<Skill[]>([]);
  const [search, setSearch] = useState('');
  // 팀 스킬에만 남는 필터(2026-08-26) — 「활성화된 스킬」이 전용 탭으로
  // 빠지면서 개인 쪽 필터(활성화된 스킬/팀에 공유한 스킬/팀 스킬에서
  // 가져온 스킬)는 다 지웠다. 셋 다 이제 탭이나 배지로 이미 보이는
  // 정보라(활성 탭, 행의 "공유중"/"팀 스킬" 배지) 필터로 한 번 더 물을
  // 필요가 없다.
  const [teamFilters, setTeamFilters] = useState({ sharedOnly: false, importedOnly: false });
  const [error, setError] = useState<string | null>(null);
  /** 한 번이라도 목록을 받아 봤는가. **빈 목록과 못 받은 것을 가른다.** */
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirming, setConfirming] = useState<{ scope: Scope; skill: Skill } | null>(null);
  const [busy, setBusy] = useState(false);
  /** 상태 변경 중인 행만 잠근다. 개인·팀에서 id가 같을 수 있어 범위도 포함한다. */
  const [togglingSkillKey, setTogglingSkillKey] = useState<string | null>(null);
  const [sharingSkillKey, setSharingSkillKey] = useState<string | null>(null);
  const [importingSkillKey, setImportingSkillKey] = useState<string | null>(null);
  const [viewingSkill, setViewingSkill] = useState<Skill | null>(null);
  const [registrationJobs, setRegistrationJobs] = useState<SkillJob[]>([]);
  const [viewingJob, setViewingJob] = useState<SkillJob | null>(null);
  const [repairingJob, setRepairingJob] = useState<SkillJob | null>(null);
  const [repairInstruction, setRepairInstruction] = useState('');
  const [repairSubmitting, setRepairSubmitting] = useState(false);
  /** 삭제 직전 시작된 목록 요청이 늦게 끝나도 지운 실패 job을 되살리지 않는다. */
  const removedJobIdsRef = useRef(new Set<string>());
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** `null`이면 아직 「직접 작성」 한 문장 입력 단계 — `goCreateHere()`가 채운다. */
  const [creation, setCreation] = useState<CreationState | null>(null);
  const [retrySourceJobId, setRetrySourceJobId] = useState<string | null>(null);
  /** 되묻기 카드(`skill_creator_ask_followup`)의 답변 입력값. 질문이 바뀔 때마다 비운다. */
  const [followupAnswer, setFollowupAnswer] = useState('');

  async function load() {
    if (!token) return;
    try {
      // 둘을 함께 받는다. 탭을 바꿀 때마다 부르면 넘어갈 때 빈 화면이 번쩍인다.
      const [mine, team, jobs] = await Promise.all([
        listMySkills(token),
        listTeamSkills(token),
        listSkillJobs(token),
      ]);
      setPersonalSkills(mine);
      setTeamSkills(team);
      setRegistrationJobs(jobs.filter((job) => !removedJobIdsRef.current.has(job.job_id)));
      setError(null);
      setLoaded(true);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : '목록을 불러오지 못했습니다.');
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // 설정 화면을 열어 둔 동안에도 백그라운드 워커의 단계를 반영한다. 완료되면
  // 실제 SKILL.md 목록도 다시 받아 방금 등록된 스킬이 즉시 나타나게 한다.
  useEffect(() => {
    if (!token || !registrationJobs.some(isSkillJobOpen)) return;
    const timer = window.setInterval(async () => {
      try {
        const jobs = await listSkillJobs(token);
        const hadOpen = registrationJobs.some(isSkillJobOpen);
        const hasOpen = jobs.some(isSkillJobOpen);
        const visibleJobs = jobs.filter((job) => !removedJobIdsRef.current.has(job.job_id));
        setRegistrationJobs(visibleJobs);
        setViewingJob((current) => visibleJobs.find((job) => job.job_id === current?.job_id) ?? current);
        if (hadOpen && !hasOpen) await load();
      } catch {
        // 전역 진행 카드와 마찬가지로 다음 폴링에서 다시 확인한다.
      }
    }, 3_000);
    return () => window.clearInterval(timer);
    // `load`는 이 컴포넌트 안의 목록 전체 갱신 함수다. job 상태가 변할 때마다
    // interval을 재설정하는 것이 의도된 동작이다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, registrationJobs]);

  // 오른쪽 아래 카드의 `?job=` 링크로 들어오면 해당 작업을 바로 연다.
  useEffect(() => {
    const jobId = searchParams.get('job');
    if (!token || !jobId) return;
    const cached = registrationJobs.find((job) => job.job_id === jobId);
    if (cached) {
      setViewTab('personal');
      setViewingJob(cached);
      return;
    }
    getSkillJob(token, jobId)
      .then((job) => {
        setViewTab('personal');
        setViewingJob(job);
      })
      .catch((exc) => {
        showToast(exc instanceof ApiError ? exc.message : '검증 작업을 찾지 못했습니다.', 'error');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, searchParams, registrationJobs]);

  function closeJobDetail() {
    setViewingJob(null);
    if (!searchParams.has('job')) return;
    const next = new URLSearchParams(searchParams);
    next.delete('job');
    setSearchParams(next, { replace: true });
  }

  async function openJobDetail(job: SkillJob) {
    if (!token) return;
    try {
      const full = await getSkillJob(token, job.job_id);
      setViewingJob(full);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '검증 작업을 불러오지 못했습니다.', 'error');
    }
  }

  async function cancelRegistrationJob(job: SkillJob) {
    if (!token) return;
    try {
      const updated = await cancelSkillJob(token, job.job_id);
      setRegistrationJobs((rows) => rows.map((row) => (row.job_id === updated.job_id ? updated : row)));
      setViewingJob(updated);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '검증 작업을 취소하지 못했습니다.', 'error');
    }
  }

  async function removeRegistrationJob(job: SkillJob) {
    if (!token) return;
    try {
      await deleteSkillJob(token, job.job_id);
      removedJobIdsRef.current.add(job.job_id);
      setRegistrationJobs((rows) => rows.filter((row) => row.job_id !== job.job_id));
      notifySkillJobRemoved(job.job_id);
      closeJobDetail();
      showToast('검증 기록을 삭제했습니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '검증 기록을 삭제하지 못했습니다.', 'error');
    }
  }

  /** 수정 창을 여는 것만으로는 실패 기록을 지우지 않는다. 취소하면 그대로 남는다. */
  async function openRepair(job: SkillJob, initialInstruction = '') {
    if (!token) return;
    try {
      const full = job.candidate_document ? job : await getSkillJob(token, job.job_id);
      if (!full.candidate_document) {
        showToast('보완할 기존 스킬 초안을 찾지 못했습니다.', 'error');
        return;
      }
      closeJobDetail();
      setRepairingJob(full);
      setRepairInstruction(initialInstruction);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '실패한 스킬을 수정하지 못했습니다.', 'error');
    }
  }

  /**
   * 수정 폼을 연다. **본문은 그때 받는다** — 목록 응답에 본문을 실으면
   * 스킬이 늘수록 목록이 무거워지는데, 정작 읽는 건 여는 한 건뿐이다.
   */
  async function openEdit(editScope: Scope, skill: Skill) {
    if (!token) return;
    setBusy(true);
    try {
      const full =
        editScope === 'personal'
          ? await getMySkill(token, skill.skill_id)
          : await getTeamSkill(token, skill.skill_id);
      setEditing({
        scope: editScope,
        skill: full,
        name: full.name,
        description: full.description,
        body: full.body ?? '',
        mode: 'write',
        uploadFileName: null,
        uploadSourceContent: null,
        uploadError: null,
        sentence: '',
      });
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function openTeamSkill(skill: Skill) {
    if (!token) return;
    setBusy(true);
    try {
      setViewingSkill(await getTeamSkill(token, skill.skill_id));
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '스킬 내용을 불러오지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  function onPickFile(file: File) {
    if (!file.name.toLowerCase().endsWith('.md')) {
      setEditing((prev) =>
        prev ? { ...prev, uploadFileName: file.name, uploadError: '.md 파일만 올릴 수 있습니다.' } : prev,
      );
      return;
    }
    if (file.size > MAX_SKILL_BODY_BYTES) {
      setEditing((prev) =>
        prev
          ? {
              ...prev,
              uploadFileName: file.name,
              uploadError: `파일이 너무 큽니다 (${formatKB(file.size)}). 최대 ${formatKB(MAX_SKILL_BODY_BYTES)}까지 올릴 수 있습니다.`,
            }
          : prev,
      );
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      try {
        const parsed = parseSkillMdPreview(text);
        setEditing((prev) =>
          prev
            ? {
                ...prev,
                name: parsed.name,
                description: parsed.description,
                body: parsed.body,
                uploadFileName: file.name,
                uploadSourceContent: text,
                uploadError: null,
              }
            : prev,
        );
      } catch (exc) {
        setEditing((prev) =>
          prev
            ? { ...prev, uploadFileName: file.name, uploadError: exc instanceof Error ? exc.message : '파일을 읽지 못했습니다.' }
            : prev,
        );
      }
    };
    reader.onerror = () => {
      setEditing((prev) => (prev ? { ...prev, uploadFileName: file.name, uploadError: '파일을 읽지 못했습니다.' } : prev));
    };
    reader.readAsText(file);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onPickFile(file);
  }

  async function save() {
    if (!token || !editing) return;
    setBusy(true);
    try {
      if (editing.skill) {
        const patch = { description: editing.description.trim(), body: editing.body };
        await submitMySkillUpdate(token, editing.skill.skill_id, patch);
        showToast('수정 내용을 검증하기 시작했습니다.', 'success');
      } else {
        const input = {
          name: editing.name.trim(),
          description: editing.description.trim(),
          body: editing.body,
          ...(editing.mode === 'upload' && editing.uploadSourceContent
            ? { source_content: editing.uploadSourceContent }
            : {}),
        };
        await createMySkill(token, input);
        showToast('스킬을 검증하기 시작했습니다.', 'success');
      }
      notifySkillJobStarted();
      setEditing(null);
    } catch (exc) {
      // 이름이 겹치면 서버가 409로 거부한다 — 그 문구를 그대로 보여준다.
      showToast(exc instanceof ApiError ? exc.message : '저장하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  /**
   * 채팅과 같은 기본 에이전트를 고른다(`ChatPage.tsx`의 `usable.find((row) =>
   * row.is_default_chat)` 자리와 같은 규칙). 이 화면은 대화 목록이 없으므로
   * 매번 새로 조회한다 — 스킬 만들기는 자주 하는 조작이 아니라 캐싱까지는
   * 과하다.
   */
  async function resolveDefaultAgentId(): Promise<string | null> {
    if (!token) return null;
    const rows = await listAgentVersions(token);
    const usable = rows.filter((row) => row.status === 'ACTIVE' || row.status === 'DRAFT');
    return usable.find((row) => row.is_default_chat)?.agent_id ?? usable[0]?.agent_id ?? null;
  }

  /**
   * 스트림 이벤트 하나를 `creation` 상태로 접는다. `liveChat.ts`의
   * `awaiting_confirmation` 분기와 같은 판정 규칙을 쓴다 — 이 턴에 걸린
   * 호출이 `skill_creator_ask_followup` 하나뿐이면 되묻기, 아니면(보통
   * `skill_register`) 승인 카드다. 다른 타입(진행률·추론 등)은 이 작은
   * 모달에선 그리지 않고 조용히 무시한다 — 최종 결과만 보여 준다.
   *
   * **`result`만으로 "등록됐다"고 단정하지 않는다**(2026-08-24 실제로
   * 겪은 문제 — 모델이 정보가 부족한데도 `skill_creator_ask_followup`을
   * 안 부르고 채팅 텍스트로 질문 목록만 나열한 채 끝낸 경우에도 `result`가
   * 온다). 실제 등록 여부는 `skill_register`의 `tool_completed`를 따로
   * 봐서 `registered`에 남긴다 — `result` 쪽은 그 값을 안 건드린다(아래
   * `...prev`로 유지).
   */
  function handleCreationEvent(event: ChatEvent) {
    if (event.type === 'awaiting_confirmation') {
      let actions: CreationAction[];
      if ('action_requests' in event) {
        actions = event.action_requests.map((request) => ({ name: request.name, args: request.args ?? {} }));
      } else {
        actions = [{ name: event.tool_name, args: event.arguments ?? {} }];
      }
      const isAsk = actions.length === 1 && actions[0].name === ASK_FOLLOWUP_TOOL_NAME;
      if (isAsk) {
        const question = typeof actions[0].args.question === 'string' ? (actions[0].args.question as string) : '';
        setFollowupAnswer('');
        setCreation((prev) => (prev ? { ...prev, phase: 'ask', question, actions: null } : prev));
      } else {
        // 앞 단계의 답변이 재설명 입력칸에 남아 그대로 재전송되는 일을 막는다.
        setFollowupAnswer('');
        setCreation((prev) => (prev ? { ...prev, phase: 'confirm', actions, question: null } : prev));
      }
      return;
    }
    if (event.type === 'tool_completed' && event.tool_ref === 'skill_register' && event.status === 'OK') {
      // `SkillJobCenter`에게 방금 검증 job이 생겼다고 알린다(2026-08-26) —
      // `ChatPage.tsx`의 일반 채팅 경로와 같은 신호(`skillJobSignal.ts`).
      // 이 모달은 `liveChat.ts`의 리듀서를 안 쓰므로(맨 위 docstring) 그
      // 경로를 못 타서 여기서 따로 부른다.
      notifySkillJobStarted();
      setCreation((prev) => (prev ? { ...prev, registered: true } : prev));
      return;
    }
    if (event.type === 'result') {
      setCreation((prev) => {
        if (!prev) return prev;
        if (prev.registrationCancelled) {
          // **모델의 실제 응답을 지우지 않는다**(2026-08-24 UX 점검 — 예전엔
          // `finalText: null`로 버려서, 거절한 뒤엔 아무 내용도 없이 「닫기」
          // 버튼 하나만 남는 막다른 화면이었다. 이제 그 응답을 보여주고,
          // 바로 이어서 설명할 수 있는 입력칸을 아래(`continueAfterCancel`)
          // 붙인다 — 세션은 안 지웠으니 그대로 이어갈 수 있다.
          return { ...prev, phase: 'cancelled', finalText: event.text, errorText: null, runningReason: null };
        }
        if (!prev.registered) {
          return {
            ...prev,
            phase: 'error',
            finalText: null,
            errorText:
              '스킬 생성기가 등록 요청 없이 종료되었습니다. 일반 대화로 이어가지 않고 중단했습니다. 다시 시도해 주세요.',
          };
        }
        return { ...prev, phase: 'done', finalText: event.text };
      });
      return;
    }
    if (event.type === 'error') {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: event.detail ?? event.message ?? '스킬을 만들지 못했습니다.' } : prev,
      );
    }
    // 그 밖의 이벤트(skill_applied·stage·tool_started 등)는 이 모달에서 안 그린다.
  }

  /** 명세 문장을 임시 생성 세션으로 흘려보내 스킬 만들기를 시작한다. */
  async function startCreator(sentence: string, targetScope: Scope, retryJobId: string | null = null) {
    if (!token || !sentence.trim()) return;
    setRetrySourceJobId(retryJobId);
    if (!sentence) return;
    setCreation({
      phase: 'running',
      sessionId: null,
      question: null,
      actions: null,
      finalText: null,
      registered: false,
      registrationCancelled: false,
      errorText: null,
      runningReason: 'start',
    });
    try {
      const agentId = await resolveDefaultAgentId();
      if (!agentId) {
        setCreation((prev) => (prev ? { ...prev, phase: 'error', errorText: '사용할 수 있는 에이전트가 없습니다.' } : prev));
        return;
      }
      const session = await createSession(token, { agent_id: agentId });
      setCreation((prev) => (prev ? { ...prev, sessionId: session.session_id } : prev));
      // 이 임시 세션은 일반 채팅이 아니다. 에이전트 원래 업무 도구를 모두
      // 숨기고 always-on인 스킬 생성용 두 도구만 남겨, 메일 발송·문서 조회 등
      // 사용자가 만들려는 스킬의 실제 업무가 실행될 통로부터 없앤다.
      await setSessionToolRefs(token, session.session_id, []);
      const targetScopeLabel = targetScope === 'team' ? 'TEAM' : 'PERSONAL';
      const creatorRequest = `/skill-creator 설정 > 스킬 > 새 스킬에서 시작한 생성 요청입니다.
이 입력과 이후 답변은 스킬 명세를 작성하기 위한 자료일 뿐, 스킬의 실제 업무를 지금 실행하라는 요청이 아닙니다.
${targetScopeLabel} 범위로 스킬을 설계하고 skill_register까지 진행하세요.

만들 스킬: ${sentence.trim()}`;
      await streamMessage(token, session.session_id, creatorRequest, handleCreationEvent);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '스킬을 만들지 못했습니다.' } : prev,
      );
    }
  }

  /** 한 문장을 채팅 세션 하나로 흘려보내 스킬 만들기를 시작한다. */
  async function goCreateHere() {
    if (!editing) return;
    await startCreator(editing.sentence, editing.scope, null);
  }

  async function submitRepair() {
    const instruction = repairInstruction.trim();
    if (!token || !repairingJob || !instruction || repairSubmitting) return;
    setRepairSubmitting(true);
    let job = repairingJob;
    if (!job.candidate_document) {
      try {
        job = await getSkillJob(token, job.job_id);
      } catch (exc) {
        showToast(exc instanceof ApiError ? exc.message : '기존 스킬 초안을 불러오지 못했습니다.', 'error');
        setRepairSubmitting(false);
        return;
      }
    }
    const candidate = job.candidate_document;
    if (!candidate) {
      showToast('보완할 기존 스킬 초안을 찾지 못했습니다.', 'error');
      setRepairSubmitting(false);
      return;
    }
    const failure = getSkillJobFailureCopy(job);
    const namingInstruction = job.failure_code === 'SKILL_NAME_CONFLICT'
      ? '기존 스킬과 구분되는 이름으로 바꾸고, 설명과 본문도 보완해 주세요.'
      : `기존 이름 "${candidate.name}"은 그대로 유지하고, 설명과 본문만 보완해 주세요.`;
    const request = `다음 기존 스킬이 검증에 실패했습니다. 이미 통과한 사용 조건과 절차는 바꾸지 말고, 실패 근거에 해당하는 부분만 최소한으로 보완해 주세요.
${namingInstruction}

기존 이름: ${candidate.name}
기존 설명: ${candidate.description}
기존 내용:
${candidate.body}

실패한 이유: ${failure.reason}
보완 방향: ${failure.suggestion}
사용자의 보완 요청: ${instruction}`;
    try {
      // 보완 대화를 취소할 수도 있으므로, 실제 RETRY job이 만들어지기 전에는
      // 이전 실패 기록을 그대로 둔다.
      setRepairingJob(null);
      setRepairInstruction('');
      setViewingJob(null);
      setEditing({ ...emptyEditing('personal'), sentence: request });
      await startCreator(request, 'personal', job.job_id);
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '스킬을 다시 만들지 못했습니다.', 'error');
    } finally {
      setRepairSubmitting(false);
    }
  }

  async function retryUnchanged(job: SkillJob) {
    if (!token) return;
    try {
      const retried = await retrySkillJob(token, job.job_id);
      removedJobIdsRef.current.add(job.job_id);
      setRegistrationJobs((rows) => [
        retried,
        ...rows.filter((row) => row.job_id !== job.job_id && row.job_id !== retried.job_id),
      ]);
      notifySkillJobRemoved(job.job_id);
      notifySkillJobStarted();
      setViewingJob(retried);
      showToast('현재 환경에서 검증을 다시 시작했습니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '검증을 다시 시작하지 못했습니다.', 'error');
    }
  }

  /** 되묻기 질문에 답을 보낸다 — `type: 'respond'`로 그 도구 호출을 건너뛰고 답을 모델에게 그대로 돌려준다. */
  async function submitFollowup() {
    const answer = followupAnswer.trim();
    if (!token || !creation?.sessionId || !answer) return;
    setCreation((prev) => (prev ? { ...prev, phase: 'running', question: null, runningReason: 'answer' } : prev));
    try {
      await confirmMessage(token, creation.sessionId, undefined, handleCreationEvent, undefined, [
        {
          action_index: 0,
          type: 'respond',
          message:
            '스킬 생성 명세에 대한 답변입니다. 실제 메일·번역·문서 등의 처리 입력이 아닙니다.\n\n' +
            answer,
        },
      ]);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '답을 보내지 못했습니다.' } : prev,
      );
    }
  }

  /** `skill_register` 확인 카드 — 승인은 전체 승인(`selected` 생략), 거절은 걸린 호출 전부를 거절한다. */
  async function submitConfirm(approve: boolean) {
    if (!token || !creation?.sessionId) return;
    const pending = creation.actions ?? [];
    setCreation((prev) =>
      prev
        ? {
            ...prev,
            phase: 'running',
            actions: null,
            registrationCancelled: !approve,
            runningReason: approve ? 'approve' : 'cancel',
          }
        : prev,
    );
    try {
      if (approve) {
        if (retrySourceJobId) {
          const sourceJobId = retrySourceJobId;
          const registerAction = pending.find((action) => action.name === 'skill_register');
          const args = registerAction?.args ?? {};
          const candidate = {
            name: String(args.name ?? '').trim(),
            description: String(args.description ?? '').trim(),
            body: String(args.body ?? ''),
          };
          const retried = await retrySkillJob(token, sourceJobId, candidate);
          // 새 검증 작업 생성이 성공한 시점에만 이전 실패를 화면에서 교체한다.
          // DB의 부모 행은 재시도 이력 추적을 위해 그대로 보존된다.
          removedJobIdsRef.current.add(sourceJobId);
          setRegistrationJobs((rows) => [
            retried,
            ...rows.filter((row) => row.job_id !== sourceJobId && row.job_id !== retried.job_id),
          ]);
          notifySkillJobRemoved(sourceJobId);
          notifySkillJobStarted();
          setRetrySourceJobId(null);
          setCreation((prev) => prev ? {
            ...prev, phase: 'done', registered: true, actions: null, runningReason: null,
            finalText: '보완한 내용으로 스킬 검증을 다시 시작했습니다.',
          } : prev);
          return;
        }
        await confirmMessage(token, creation.sessionId, undefined, handleCreationEvent);
      } else {
        await confirmMessage(
          token,
          creation.sessionId,
          undefined,
          handleCreationEvent,
          undefined,
          pending.map((_, index) => ({ action_index: index, type: 'reject' as const })),
        );
        // 거절 뒤 모델이 반환하는 문장에는 도구명·저장 범위 같은 내부 구현
        // 용어가 섞일 수 있다. 사용자가 보고 있던 초안의 핵심만 다시 보여
        // 주고, 그 상태에서 자연어로 수정 요청을 이어가게 한다.
        const registerAction = pending.find((action) => action.name === 'skill_register');
        const draftName = String(registerAction?.args.name ?? '').trim();
        const draftDescription = String(registerAction?.args.description ?? '').trim();
        const draftSummary = [
          draftName ? `작성 중인 스킬: ${draftName}` : '',
          draftDescription,
        ].filter(Boolean).join('\n');
        setCreation((prev) =>
          prev
            ? {
                ...prev,
                phase: 'cancelled',
                registrationCancelled: true,
                runningReason: null,
                finalText: draftSummary || '작성 중인 초안은 아직 등록하지 않았습니다.',
              }
            : prev,
        );
      }
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '처리하지 못했습니다.' } : prev,
      );
    }
  }

  /**
   * 거절(다시 설명하기) 뒤에 이어서 설명한다(2026-08-24 UX 점검 — 예전엔
   * 거절하면 모델의 응답도 안 보여주고 「닫기」밖에 없는 막다른 화면이었다).
   * 세션은 살아 있으므로(`closeCreation`을 안 불렀다) `confirmMessage`가
   * 아니라 보통 발화처럼 `streamMessage`로 새 턴을 이어 보낸다 — 거절로
   * 이미 그 호출은 끝났고, 이건 다음 턴의 새 사용자 발화다.
   */
  async function continueAfterCancel() {
    const text = followupAnswer.trim();
    const sessionId = creation?.sessionId;
    if (!token || !sessionId || !text) return;
    setFollowupAnswer('');
    setCreation((prev) =>
      prev
        ? { ...prev, phase: 'running', runningReason: 'answer', registrationCancelled: false, finalText: null }
        : prev,
    );
    try {
      await streamMessage(token, sessionId, text, handleCreationEvent);
    } catch (exc) {
      setCreation((prev) =>
        prev ? { ...prev, phase: 'error', errorText: exc instanceof ApiError ? exc.message : '메시지를 보내지 못했습니다.' } : prev,
      );
    }
  }

  /**
   * 스킬 만들기 대화창을 닫는다 — 성공·취소·오류 어느 경우든 여기 하나로
   * 모은다. **채팅 세션을 지운다.** 이 흐름은 `/chat/sessions/`를 그대로
   * 빌려 쓰지만(위 `goCreateHere` 주석) 사용자에게는 절대 "채팅"이
   * 아니다 — 스킬을 만들기 위한 질의응답일 뿐이다. 안 지우면 이게 진짜
   * 대화 목록(Chat 사이드바)에 남아 뒤섞인다(2026-08-24 실제로 겪은
   * 문제). `skill_register`는 이미 스킬 저장소에 별도로 저장했으므로
   * 세션을 지워도 등록된 스킬 자체는 그대로 남는다 — 지우는 건 이
   * 흐름의 흔적일 뿐이다. 실패해도 조용히 넘어간다(모달을 닫는 것보다
   * 중요하지 않다).
   */
  function closeCreation() {
    const sessionId = creation?.sessionId;
    setCreation(null);
    setEditing(null);
    if (token && sessionId) {
      void deleteSession(token, sessionId).catch(() => {});
    }
  }

  /** 오류 화면의 「다시 시도」— 대화창은 안 닫고 실패한 세션만 지운다. `goCreateHere()`가 새 세션을 다시 만든다. */
  function retryCreation() {
    const sessionId = creation?.sessionId;
    setCreation(null);
    if (token && sessionId) {
      void deleteSession(token, sessionId).catch(() => {});
    }
  }

  /** 만들기 완료(`phase === 'done'`) 뒤 「확인」— 대화창을 닫고 목록을 새로 받는다. */
  function finishCreation() {
    closeCreation();
    void load();
  }

  /**
   * 활성/비활성 토글. **삭제와 다르다** — 값은 그대로 두고
   * 꺼진 스킬은 서버가 비활성 namespace로 옮겨 에이전트에게 보이지 않게 한다.
   * 목록 전체를 다시 안
   * 불러온다 — 서버가 돌려준 그 한 건만 바꿔치면 된다(`remove()`와 같은 이유).
   */
  async function toggleEnabled(toggleScope: Scope, skill: Skill) {
    const toggleKey = `${toggleScope}:${skill.skill_id}`;
    if (!token || togglingSkillKey === toggleKey) return;
    const next = !skill.enabled;
    setTogglingSkillKey(toggleKey);
    try {
      const updated = await setMySkillEnabled(token, skill.skill_id, next);
      setPersonalSkills((prev) => prev.map((item) => (item.skill_id === updated.skill_id ? updated : item)));
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '상태를 바꾸지 못했습니다.', 'error');
    } finally {
      setTogglingSkillKey(null);
    }
  }

  async function remove(removeScope: Scope, skill: Skill) {
    if (!token) return;
    setConfirming(null);
    setBusy(true);
    try {
      if (removeScope === 'personal') {
        await deleteMySkill(token, skill.skill_id);
        setPersonalSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
        setTeamSkills((prev) =>
          prev
            .filter((item) => !(item.shared_by_me && item.name === skill.name))
            .map((item) =>
              skill.imported_from_team && item.name === skill.name
                ? { ...item, imported_by_me: false }
                : item,
            ),
        );
      } else {
        await deleteTeamSkill(token, skill.skill_id);
        setTeamSkills((prev) => prev.filter((item) => item.skill_id !== skill.skill_id));
      }
      showToast(
        removeScope === 'personal'
          ? '내 스킬을 삭제했습니다.'
          : '팀 공유 목록에서 삭제했습니다. 이미 가져간 개인 사본은 유지됩니다.',
        'success',
      );
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '삭제하지 못했습니다.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function setShared(skill: Skill, shared: boolean) {
    if (!token || sharingSkillKey === skill.skill_id) return;
    setSharingSkillKey(skill.skill_id);
    try {
      if (shared) {
        const teamSkill = await shareMySkill(token, skill.skill_id);
        setTeamSkills((prev) => [...prev, teamSkill].sort((a, b) => a.name.localeCompare(b.name)));
        showToast('팀에 스킬을 공유했습니다.', 'success');
      } else {
        await stopSharingMySkill(token, skill.skill_id);
        setTeamSkills((prev) => prev.filter((item) => !(item.shared_by_me && item.name === skill.name)));
        showToast('팀 공유를 중지했습니다. 내 스킬은 그대로 남아 있습니다.', 'success');
      }
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '공유 상태를 바꾸지 못했습니다.', 'error');
    } finally {
      setSharingSkillKey(null);
    }
  }

  async function importSharedSkill(skill: Skill) {
    if (!token || importingSkillKey === skill.skill_id || skill.imported_by_me) return;
    setImportingSkillKey(skill.skill_id);
    try {
      const imported = await importTeamSkill(token, skill.skill_id);
      if ('job_id' in imported) {
        setRegistrationJobs((prev) => [imported, ...prev]);
        notifySkillJobStarted();
        showToast('현재 환경에서 검증한 뒤 내 스킬로 등록합니다.', 'success');
        return;
      }
      setPersonalSkills((prev) => [...prev, imported].sort((a, b) => a.name.localeCompare(b.name)));
      setTeamSkills((prev) =>
        prev.map((item) =>
          item.skill_id === skill.skill_id ? { ...item, imported_by_me: true } : item,
        ),
      );
      showToast('내 스킬로 가져왔습니다. 이제 활성 상태와 내용은 나에게만 적용됩니다.', 'success');
    } catch (exc) {
      showToast(exc instanceof ApiError ? exc.message : '내 스킬로 가져오지 못했습니다.', 'error');
    } finally {
      setImportingSkillKey(null);
    }
  }

  const rows = scope === 'personal' ? personalSkills : teamSkills;
  const sharedPersonalNames = useMemo(
    () => new Set(teamSkills.filter((skill) => skill.shared_by_me).map((skill) => skill.name)),
    [teamSkills],
  );

  /**
   * 이름으로 걸러진 목록. 서버를 다시 안 부른다 — 두 목록 다 이미 화면에 있다.
   * 「활성화된 스킬」 탭은 여기서 `enabled`로 한 번 더 거른다 — 별도 API가
   * 아니라 `personalSkills`를 보여주는 필터일 뿐이다(위 `viewTabToScope`).
   */
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows.filter((skill) => {
      if (viewTab === 'active' && !skill.enabled) return false;
      if (scope === 'team') {
        if (teamFilters.sharedOnly && !skill.shared_by_me) return false;
        if (teamFilters.importedOnly && !skill.imported_by_me) return false;
      }
      return !query || skill.name.toLowerCase().includes(query) || skill.description.toLowerCase().includes(query);
    });
  }, [rows, scope, viewTab, search, teamFilters]);

  // 성공한 작업은 아래 실제 스킬 목록으로 자리를 넘긴다. 진행·실패·취소
  // 작업만 이 구획에 남겨 "왜 스킬이 아직 안 보이는지"를 설명한다.
  const visibleRegistrationJobs = useMemo(
    () => registrationJobs.filter((job) => job.status !== 'SUCCEEDED'),
    [registrationJobs],
  );

  const bodyBytes = editing ? byteLength(editing.body) : 0;
  const bodyTooLarge = bodyBytes > MAX_SKILL_BODY_BYTES;

  /** 새로 만들기 · 직접 작성 — 한 문장을 채웠는가. */
  const sentenceReady = editing !== null && editing.sentence.trim().length > 0;
  /** 새로 만들기 · 직접 작성 탭인가(폼이 아니라 한 문장 입력을 보여줄 자리). */
  const isSentenceCreate = editing?.skill === null && editing.mode === 'write';

  /** 업로드 탭은 파일을 성공적으로 읽었을 때만 저장할 수 있다. */
  const saveable =
    editing !== null &&
    editing.name.trim().length > 0 &&
    editing.description.trim().length > 0 &&
    !bodyTooLarge &&
    (editing.skill !== null || (editing.uploadFileName !== null && editing.uploadError === null));

  return (
    <div className={styles.tab}>
      {error && <p className={`${styles.notice} ${styles.noticeDanger}`}>{error}</p>}

      <section className={styles.card}>
        <div className={`${styles.cardHead} ${styles.cardHeadRow}`}>
          <h2 className={styles.cardTitle}>
            스킬
            <InfoNote title="스킬">
              <p>회사에서 일하는 절차를 적어 두는 곳입니다. 에이전트가 그대로 따라 합니다.</p>
              <p>
                <strong>설명</strong>은 에이전트가 이 스킬을 쓸지 판단하는 근거입니다. 어떤 일에
                쓰는 절차인지 한 줄로 적으세요.
              </p>
              <p>내용은 고른 뒤에 읽습니다. 길어도 대화가 무거워지지 않습니다.</p>
              <p>
                <strong>내 스킬</strong>만 에이전트가 사용합니다. <strong>팀 스킬</strong>은 팀원이
                공유한 스킬을 살펴보고 내 스킬로 가져오는 곳입니다.
                <strong>활성화된 스킬</strong>은 내 스킬 중 지금 켜져 있는 것만 모아 보여줍니다.
              </p>
              <p>
                파일로 올릴 때는 이름을 따로 적지 않습니다 — 파일 안 <code>name</code>을 그대로
                씁니다. 파일 하나는 최대 {formatKB(MAX_SKILL_BODY_BYTES)}까지 올릴 수 있습니다.
              </p>
              <p>가져온 스킬은 독립된 내 스킬이므로 원 공유자의 비활성화나 공유 중지에 영향을 받지 않습니다.</p>
              <p>
                <strong>skill-creator</strong>는 모든 팀원에게 기본 제공되는 내장 스킬입니다.
                이 목록에는 안 뜨지만(개인/팀 스킬이 아니라서), 채팅에서 "~하는 스킬
                만들어줘"라고 하면 자동으로 켜져 필요한 것을 되물어 가며 스킬을 만듭니다.
              </p>
              <p>
                토글을 끄면 삭제하지 않고도 에이전트가 그 스킬을 못 보게 할 수 있습니다.
                내용은 그대로 남아 있어 언제든 다시 켤 수 있습니다. 이 상태는 나에게만 적용됩니다.
              </p>
            </InfoNote>
          </h2>
          {/* 검색창을 「새 스킬」 옆에 둔다 — 목록 위 한 줄에서 필터와 만들기를
              같이 다룬다. */}
          <div className={styles.headActions}>
            <div className={styles.searchBox}>
              <Icon name="search" size={16} color="var(--color-placeholder)" />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="스킬 이름 또는 설명 검색..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            {scope === 'personal' && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setCreation(null);
                  setEditing(emptyEditing(scope));
                }}
              >
                새 스킬
              </Button>
            )}
          </div>
        </div>

        {visibleRegistrationJobs.length > 0 && (
          <div className={styles.jobSection}>
            <div className={styles.jobSectionHead}>
              <strong>등록 진행</strong>
              <span>검증을 통과한 뒤 내 스킬에 표시됩니다.</span>
            </div>
            <div className={styles.list}>
              {visibleRegistrationJobs.map((job) => (
                <button
                  key={job.job_id}
                  type="button"
                  className={`${styles.row} ${styles.jobRow}`}
                  onClick={() => void openJobDetail(job)}
                >
                  <span className={styles.rowIcon}>
                    <Icon
                      name={job.status === 'FAILED' ? 'triangle-alert' : isSkillJobOpen(job) ? 'loader' : 'x'}
                      size={18}
                      spin={isSkillJobOpen(job)}
                      color={job.status === 'FAILED' ? 'var(--color-danger)' : 'var(--color-primary)'}
                    />
                  </span>
                  <span className={styles.rowBody}>
                    <span className={styles.rowName}>{job.skill_name}</span>
                    <span className={styles.rowMeta}>
                      {job.status === 'FAILED'
                        ? getSkillJobFailureCopy(job).reason
                        : job.waiting_reason ?? `${job.stage_index + 1}/5 · ${JOB_STAGE_LABELS[job.stage]}`}
                    </span>
                  </span>
                  <Badge tone={jobStatusTone(job)}>{jobStatusLabel(job)}</Badge>
                  <span className={styles.jobDetailText}>자세히보기</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className={styles.innerTabs} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={viewTab === 'active'}
            className={[styles.innerTab, viewTab === 'active' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setViewTab('active')}
          >
            활성화된 스킬 {personalSkills.filter((skill) => skill.enabled).length}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewTab === 'personal'}
            className={[styles.innerTab, viewTab === 'personal' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setViewTab('personal')}
          >
            내 스킬 {personalSkills.length}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewTab === 'team'}
            className={[styles.innerTab, viewTab === 'team' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setViewTab('team')}
          >
            팀 스킬 {teamSkills.length}
          </button>
        </div>

        {/* 팀 스킬에만 필터를 남긴다 — 개인 쪽(활성화된 스킬/팀에 공유한
            스킬/팀 스킬에서 가져온 스킬)은 지웠다(2026-08-26). 「활성화된
            스킬」은 이제 필터가 아니라 전용 탭이고, 나머지 둘은 각 행의
            "공유중"/"팀 스킬" 배지로 이미 보인다. */}
        {scope === 'team' && (
          <div className={styles.skillFilters} aria-label="팀 스킬 필터">
            <button
              type="button"
              aria-pressed={teamFilters.importedOnly}
              className={[styles.skillFilter, teamFilters.importedOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
              onClick={() =>
                setTeamFilters((prev) => ({ ...prev, importedOnly: !prev.importedOnly }))
              }
            >
              등록된 스킬
            </button>
            <button
              type="button"
              aria-pressed={teamFilters.sharedOnly}
              className={[styles.skillFilter, teamFilters.sharedOnly ? styles.skillFilterOn : ''].filter(Boolean).join(' ')}
              onClick={() =>
                setTeamFilters((prev) => ({ ...prev, sharedOnly: !prev.sharedOnly }))
              }
            >
              내가 공유한 스킬
            </button>
          </div>
        )}

        <div className={styles.list}>
          {loaded && rows.length === 0 && (
            <p className={styles.cardSub}>
              {viewTab === 'active'
                ? '아직 만든 스킬이 없습니다.'
                : scope === 'personal'
                  ? '아직 만든 스킬이 없습니다.'
                  : '아직 등록된 팀 스킬이 없습니다.'}
            </p>
          )}

          {loaded && rows.length > 0 && filteredRows.length === 0 && (
            <p className={styles.cardSub}>
              {viewTab === 'active'
                ? '활성화된 스킬이 없습니다. 내 스킬 탭에서 켤 수 있습니다.'
                : '선택한 조건에 맞는 스킬이 없습니다.'}
            </p>
          )}

          {filteredRows.map((skill) => {
            const toggleKey = `${scope}:${skill.skill_id}`;
            const toggling = togglingSkillKey === toggleKey;
            const sharedByMe = scope === 'team' ? skill.shared_by_me : sharedPersonalNames.has(skill.name);
            const sharing = sharingSkillKey === skill.skill_id;
            const importing = importingSkillKey === skill.skill_id;
            return (
              <div key={skill.skill_id} className={`${styles.row} ${styles.rowTall}`}>
                <span className={styles.rowIcon}>
                  <Icon name="sparkles" size={20} color="var(--color-primary)" />
                </span>
                <div className={styles.rowBody}>
                  <span className={styles.rowName}>
                    {skill.name}
                    {sharedByMe && <Badge tone="primary">공유중</Badge>}
                    {scope === 'personal' && skill.imported_from_team && (
                      <Badge tone="neutral">팀 스킬</Badge>
                    )}
                  </span>
                  {/* 설명은 줄여서 감추지 않는다 — 에이전트가 이것만 보고 고르는
                      값이라, 사람도 여기서 그대로 읽고 고칠 수 있어야 한다. */}
                  <span className={styles.rowMeta}>{skill.description}</span>
                </div>
                {scope === 'personal' ? (
                  <div className={`${styles.rowActions} ${styles.personalActions}`}>
                    {/* 꺼지면 값은 그대로 두고 에이전트에게만 안 보이게 한다
                        (삭제와 다름) — `toggleEnabled()` 참고. */}
                    <div
                      className={[
                        styles.skillState,
                        skill.enabled ? styles.skillStateOn : styles.skillStateOff,
                      ].join(' ')}
                    >
                      <span className={styles.skillStateText} aria-live="polite">
                        {toggling ? '변경 중' : skill.enabled ? '활성' : '비활성'}
                      </span>
                      <ToggleSwitch
                        checked={skill.enabled}
                        disabled={toggling}
                        ariaLabel={`${skill.name} 스킬을 ${skill.enabled ? '비활성화' : '활성화'}`}
                        onChange={() => void toggleEnabled(scope, skill)}
                      />
                    </div>
                    {!skill.imported_from_team && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy || sharing}
                        onClick={() => void setShared(skill, !sharedByMe)}
                      >
                        {sharing ? '처리 중…' : sharedByMe ? '중지' : '공유'}
                      </Button>
                    )}
                    {skill.imported_from_team && <span className={styles.shareActionSlot} aria-hidden="true" />}
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => openEdit('personal', skill)}>
                      수정
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming({ scope, skill })}>
                      삭제
                    </Button>
                  </div>
                ) : (
                  <div className={styles.rowActions}>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => void openTeamSkill(skill)}>
                      내용 보기
                    </Button>
                    {!skill.shared_by_me && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy || importing || skill.imported_by_me}
                        onClick={() => void importSharedSkill(skill)}
                      >
                        {importing
                          ? '가져오는 중…'
                          : skill.imported_by_me
                            ? '이미 등록됨'
                            : skill.requires_validation
                              ? '내 스킬로 등록'
                              : '내 스킬로 등록'}
                      </Button>
                    )}
                    {skill.shared_by_me && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={sharing}
                        onClick={() => void setShared(skill, false)}
                      >
                        {sharing ? '처리 중…' : '중지'}
                      </Button>
                    )}
                    {skill.can_delete && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setConfirming({ scope: 'team', skill })}
                      >
                        삭제
                      </Button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <Modal
        open={editing !== null}
        onClose={() => (creation ? closeCreation() : setEditing(null))}
        // **`running`이라고 무조건 못 닫게 하지 않는다**(2026-08-24 UX 점검
        // — "거절해도 1초 만에 안 끝나는데 뒤로 가기도 없다"는 지적). 정말
        // 닫으면 안 되는 경우는 지금 막 시작했거나(`start`) 실제로 등록
        // 쓰기가 걸린 순간(`approve`)뿐이다 — 그 둘은 닫아도 배경에서 계속
        // 진행돼 나중에 목록에 예상 못 한 결과가 나타날 수 있다(`Modal.tsx`의
        // `dismissible` 문서 그대로). 되묻기 답 반영(`answer`)이나 거절 반영
        // (`cancel`)은 실패해도 아무 것도 안 만들어지므로 언제든 닫아도 된다.
        dismissible={
          creation
            ? creation.phase !== 'running' ||
              creation.runningReason === 'answer' ||
              creation.runningReason === 'cancel'
            : true
        }
        title={
          creation
            ? creation.phase === 'running'
              ? {
                  start: '스킬을 만드는 중…',
                  answer: '답변을 반영하는 중…',
                  approve: '검증을 시작하는 중…',
                  cancel: '취소하는 중…',
                }[creation.runningReason ?? 'start']
              : creation.phase === 'done'
                ? '검증을 시작했습니다'
                : {
                    ask: '하나만 확인할게요',
                    confirm: '검증 시작 확인',
                    cancelled: '다시 설명해 주세요',
                    error: '스킬을 만들지 못했습니다',
                  }[creation.phase]
            : editing?.skill
              ? '스킬 수정'
              : editing?.scope === 'team'
                ? '새 팀 스킬'
                : '새 스킬'
        }
        footer={
          creation ? (
            creation.phase === 'ask' ? (
              <>
                <Button variant="outline" onClick={closeCreation}>
                  닫기
                </Button>
                <Button variant="primary" disabled={!followupAnswer.trim()} onClick={() => void submitFollowup()}>
                  답변 보내기
                </Button>
              </>
            ) : creation.phase === 'confirm' ? (
              <>
                {/* **"거절"이 아니라 "다시 설명하기"다**(2026-08-24) — 이
                    화면의 거절은 완전히 그만두는 게 아니라 "이 초안 말고 다시
                    설명하고 싶다"는 뜻에 가깝다(스킬 생성 절차 자체가 몇 번을
                    고쳐 말해도 되는 걸 전제한다). 버튼 문구도 그 의도를
                    그대로 따라간다. */}
                <Button variant="outline" onClick={() => void submitConfirm(false)}>
                  다시 설명하기
                </Button>
                <Button variant="primary" onClick={() => void submitConfirm(true)}>
                  검증 시작
                </Button>
              </>
            ) : creation.phase === 'done' ? (
              <Button variant="primary" onClick={finishCreation}>
                확인
              </Button>
            ) : creation.phase === 'cancelled' ? (
              <>
                <Button variant="outline" onClick={closeCreation}>
                  닫기
                </Button>
                {/* **막다른 화면이 아니다**(2026-08-24 UX 점검 — 예전엔
                    「닫기」하나뿐이라, 다시 만들려면 모달을 닫고 한 문장부터
                    다시 적어야 했다). 세션은 살아 있으므로 바로 이어서
                    설명할 수 있다. */}
                <Button
                  variant="primary"
                  disabled={!followupAnswer.trim()}
                  onClick={() => void continueAfterCancel()}
                >
                  이어서 설명하기
                </Button>
              </>
            ) : creation.phase === 'error' ? (
              <>
                <Button variant="outline" onClick={retryCreation}>
                  다시 시도
                </Button>
                <Button variant="primary" onClick={closeCreation}>
                  닫기
                </Button>
              </>
            ) : (
              // running — 진행 중에는 닫을 수 있는 버튼을 안 둔다. 대신 위
              // `dismissible`이 이유(`runningReason`)에 따라 X 버튼 자체를
              // 열어 준다 — 등록 확인의 「거절」처럼 빠르게 빠져나갈 방법이
              // 필요한 경우를 그쪽에서 이미 감당한다.
              undefined
            )
          ) : (
            <>
              <Button variant="outline" onClick={() => setEditing(null)}>
                취소
              </Button>
              {isSentenceCreate ? (
                <Button variant="primary" disabled={!sentenceReady} onClick={() => void goCreateHere()}>
                  만들기
                </Button>
              ) : (
                <Button variant="primary" disabled={!saveable || busy} onClick={() => void save()}>
                  {busy ? '저장하는 중…' : '저장'}
                </Button>
              )}
            </>
          )
        }
      >
        {creation ? (
          <div className={styles.formStack}>
            {creation.phase === 'running' && (
              <div className={styles.statusRow}>
                <Icon name="loader" size={16} color="var(--color-primary)" spin />
                <p className={styles.confirmText}>
                  {{
                    start: '스킬을 만드는 중입니다…',
                    answer: '답변을 반영하는 중입니다…',
                    approve: '스킬을 등록하는 중입니다…',
                    cancel: '취소를 반영하는 중입니다…',
                  }[creation.runningReason ?? 'start']}
                </p>
              </div>
            )}
            {/* 거절(다시 설명하기)을 반영하는 동안은 안전하게 닫아도 된다는
                걸 알려준다(2026-08-24) — 위 `dismissible`이 실제로 이 순간
                모달을 열어 두므로, 굳이 몇 초를 기다리지 않아도 된다는 걸
                말로도 확인해 준다. */}
            {creation.phase === 'running' && creation.runningReason === 'cancel' && (
              <p className={styles.cardSub}>지금 닫아도 괜찮습니다 — 등록되지 않습니다.</p>
            )}

            {creation.phase === 'ask' && (
              <div className={styles.formField}>
                {/* 모델 생성 문장이 아니라 화면이 직접 고정으로 보여주는
                    안내다(2026-08-24) — "지금 실제로 뭔가 보내는 채팅"으로
                    오해하지 않도록, 이 답이 스킬 설계에만 쓰인다는 걸 프롬프트
                    문구와 무관하게 항상 같은 자리에서 알려준다. */}
                <p className={styles.cardSub}>스킬을 등록하기 위한 질문입니다 — 지금 실행되지 않습니다.</p>
                <p className={styles.confirmText}>{creation.question}</p>
                <textarea
                  className={styles.formTextarea}
                  rows={5}
                  autoFocus
                  value={followupAnswer}
                  placeholder="이곳에 답변을 해주세요"
                  onChange={(event) => setFollowupAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      void submitFollowup();
                    }
                  }}
                />
              </div>
            )}

            {creation.phase === 'confirm' && (
              <>
                {/* **"등록합니다"가 아니다**(2026-08-26) — 승인해도 즉시
                    등록되지 않는다. 검증 job만 만들고, 실제 등록은 백그라운드
                    검증(형식 검사, 앞으로는 트리거 테스트까지)을 통과해야
                    일어난다("스킬 검증·등록 최종 설계.md" §5/§6). */}
                <p className={styles.confirmText}>다음 스킬의 검증을 시작합니다.</p>
                {(creation.actions ?? []).map((action, index) => {
                  const name = typeof action.args.name === 'string' ? action.args.name : action.name;
                  const description = typeof action.args.description === 'string' ? action.args.description : null;
                  return (
                    <div key={index} className={styles.formField}>
                      <span className={styles.formLabel}>{name}</span>
                      {description && <p className={styles.cardSub}>{description}</p>}
                    </div>
                  );
                })}
                {/* 이름·설명이 마음에 안 들면 등록 대신 「다시 설명하기」를
                    누르라는 걸 여기서도 한 번 더 짚는다(2026-08-24) — 「등록
                    전에 나온 설명을 고치고 싶으면?」에 대한 답. 이 칸 자체는
                    읽기 전용이다 — 고치려면 다시 설명해서 모델이 새 초안을
                    짓게 한다(값만 바꿔 승인하면 사람이 안 본 내용이 등록될
                    수 있어, 승인 게이트가 지금 보여준 값 그대로만 등록한다). */}
                <p className={styles.cardSub}>
                  이름이나 설명을 바꾸고 싶으면 「다시 설명하기」를 누르고 무엇을 바꿀지 알려주세요.
                </p>
              </>
            )}

            {creation.phase === 'done' && (
              <div className={styles.statusRow}>
                <Icon name="check-circle" size={16} color="var(--color-primary)" />
                <div className={styles.formStack}>
                  <p className={styles.confirmText}>{creation.finalText || '검증을 시작했습니다.'}</p>
                  {/* 결과는 이 화면이 아니라 오른쪽 아래 진행 카드(SkillJobCenter)나
                      스킬 목록에서 확인한다 — 검증이 몇 초~몇 분 걸릴 수 있어
                      이 모달을 붙잡고 기다릴 필요가 없다는 걸 명시한다. */}
                  <p className={styles.cardSub}>
                    검증 결과는 화면 오른쪽 아래 진행 카드나 위 스킬 목록에서 확인할 수 있습니다.
                  </p>
                </div>
              </div>
            )}

            {creation.phase === 'cancelled' && (
              // **막다른 화면이 아니다**(2026-08-24 UX 점검) — 모델이 실제로
              // 뭐라고 답했는지 보여주고, 바로 이어서 설명할 수 있는 입력칸을
              // 준다. 세션이 살아 있어(`closeCreation` 전) 그대로 이어진다.
              <div className={styles.formField}>
                <p className={styles.confirmText}>
                  {creation.finalText || '이 초안으로는 등록하지 않았습니다.'}
                </p>
                <p className={styles.cardSub}>
                  무엇을 바꿀지 알려주시면 이어서 다시 만들어 드릴게요. 그만하시려면 닫기를 눌러주세요.
                </p>
                <textarea
                  className={styles.formTextarea}
                  rows={4}
                  autoFocus
                  value={followupAnswer}
                  placeholder="예: 좀 더 격식 있는 톤으로, 이름을 다르게"
                  onChange={(event) => setFollowupAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      void continueAfterCancel();
                    }
                  }}
                />
              </div>
            )}

            {creation.phase === 'error' && (
              <p className={`${styles.notice} ${styles.noticeDanger}`}>{creation.errorText}</p>
            )}
          </div>
        ) : (
        <div className={styles.formStack}>
          {/* 새로 만들 때만 방법을 고른다 — 수정할 때는 이미 있는 내용을
              고치는 것이라 「업로드」가 의미가 없다. */}
          {editing?.skill === null && (
            <div className={styles.innerTabs} role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={editing.mode === 'write'}
                className={[styles.innerTab, editing.mode === 'write' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
                onClick={() => setEditing((prev) => (prev ? { ...prev, mode: 'write' } : prev))}
              >
                직접 작성
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={editing.mode === 'upload'}
                className={[styles.innerTab, editing.mode === 'upload' ? styles.innerTabOn : ''].filter(Boolean).join(' ')}
                onClick={() => setEditing((prev) => (prev ? { ...prev, mode: 'upload' } : prev))}
              >
                파일 업로드
              </button>
            </div>
          )}

          {editing?.skill === null && editing.mode === 'upload' ? (
            <>
              {/* Claude 의 스킬 업로드와 같은 방식 — 이름은 이 화면에서 안
                  받는다. 파일의 frontmatter `name:` 을 그대로 쓴다. */}
              <div
                className={[styles.dropZone, dragging ? styles.dropZoneOn : ''].filter(Boolean).join(' ')}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click();
                }}
              >
                <Icon name="file-text" size={22} color="var(--color-primary)" />
                <span className={styles.dropTitle}>
                  {editing.uploadFileName ?? '여기로 끌어다 놓거나 눌러서 SKILL.md를 고르세요'}
                </span>
                <span className={styles.dropHint}>
                  .md 파일 하나 · frontmatter에 name·description 필요 · 최대 {formatKB(MAX_SKILL_BODY_BYTES)}
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={UPLOAD_ACCEPT}
                  className={styles.fileInput}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) onPickFile(file);
                    event.target.value = '';
                  }}
                />
              </div>

              {editing.uploadError && <p className={`${styles.notice} ${styles.noticeDanger}`}>{editing.uploadError}</p>}

              {editing.uploadFileName && !editing.uploadError && (
                <div className={styles.formStack}>
                  <div className={styles.formField}>
                    <span className={styles.formLabel}>이름</span>
                    <p className={styles.confirmText}>{editing.name}</p>
                  </div>
                  <div className={styles.formField}>
                    <span className={styles.formLabel}>설명</span>
                    <p className={styles.confirmText}>{editing.description}</p>
                  </div>
                </div>
              )}
            </>
          ) : isSentenceCreate ? (
            <div className={styles.formField}>
              <label className={styles.formLabel} htmlFor="skill-sentence">
                어떤 스킬을 만들고 싶으신가요?
              </label>
              <textarea
                id="skill-sentence"
                className={styles.formTextarea}
                rows={5}
                value={editing?.sentence ?? ''}
                placeholder="예: 회의록을 요약해서 담당자별 할 일로 정리하는 스킬 만들어줘"
                onChange={(event) =>
                  setEditing((prev) => (prev ? { ...prev, sentence: event.target.value } : prev))
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    void goCreateHere();
                  }
                }}
              />
              <p className={styles.cardSub}>
                한 문장으로 적으면 바로 여기서 만듭니다. 이름·설명은 스킬이 스스로 짓고, 더
                필요한 정보가 있으면 이어서 하나씩 되물어 확인합니다.
              </p>
            </div>
          ) : (
            <>
              <Input
                label="이름"
                required
                disabled={editing?.skill != null}
                value={editing?.name ?? ''}
                placeholder="구매 검토 절차"
                onChange={(event) =>
                  setEditing((prev) => (prev ? { ...prev, name: event.target.value } : prev))
                }
              />
              <Input
                label="설명"
                required
                value={editing?.description ?? ''}
                placeholder="구매 요청을 검토하고 승인 라인을 정할 때 사용합니다"
                onChange={(event) =>
                  setEditing((prev) => (prev ? { ...prev, description: event.target.value } : prev))
                }
              />
              <div className={styles.formField}>
                <label className={styles.formLabel} htmlFor="skill-body">
                  내용
                </label>
                <textarea
                  id="skill-body"
                  className={styles.formTextarea}
                  rows={12}
                  value={editing?.body ?? ''}
                  placeholder={'1. 요청 금액을 확인한다.\n2. 500만원을 넘으면 팀장 승인을 받는다.'}
                  onChange={(event) =>
                    setEditing((prev) => (prev ? { ...prev, body: event.target.value } : prev))
                  }
                />
                <span className={[styles.byteCount, bodyTooLarge ? styles.byteCountOver : ''].filter(Boolean).join(' ')}>
                  {formatKB(bodyBytes)} / {formatKB(MAX_SKILL_BODY_BYTES)}
                  {bodyTooLarge && ' · 용량을 넘었습니다'}
                </span>
              </div>
            </>
          )}
        </div>
        )}
      </Modal>

      <Modal
        open={viewingJob !== null}
        onClose={closeJobDetail}
        title="스킬 검증 상세"
        footer={(
          <>
            {viewingJob && isSkillJobOpen(viewingJob) && viewingJob.status !== 'CANCEL_REQUESTED' && (
              <Button variant="outline" onClick={() => void cancelRegistrationJob(viewingJob)}>
                검증 취소
              </Button>
            )}
            {viewingJob && (viewingJob.status === 'FAILED' || viewingJob.status === 'CANCELED') && (
              <Button variant="outline" onClick={() => void removeRegistrationJob(viewingJob)}>
                기록 삭제
              </Button>
            )}
            {viewingJob?.status === 'FAILED' && (
              <Button
                variant="outline"
                onClick={() => void openRepair(viewingJob)}
              >
                수정
              </Button>
            )}
            {viewingJob?.status === 'FAILED' && ['SYSTEM', 'CHANGED_CONTEXT'].includes(viewingJob.failure_category ?? '') && (
              <Button variant="outline" onClick={() => void retryUnchanged(viewingJob)}>
                그대로 다시 검증
              </Button>
            )}
            <Button variant="primary" onClick={closeJobDetail}>
              확인
            </Button>
          </>
        )}
      >
        <div className={styles.formStack}>
          <div className={styles.formField}>
            <span className={styles.formLabel}>스킬</span>
            <p className={styles.confirmText}>{viewingJob?.skill_name}</p>
          </div>
          <div className={styles.formField}>
            <span className={styles.formLabel}>현재 상태</span>
            {viewingJob && <Badge tone={jobStatusTone(viewingJob)}>{jobStatusLabel(viewingJob)}</Badge>}
            {viewingJob && isSkillJobOpen(viewingJob) && (
              <p className={styles.cardSub}>
                {viewingJob.stage_index + 1}/5 · {JOB_STAGE_LABELS[viewingJob.stage]}
              </p>
            )}
          </div>
          {viewingJob && isSkillJobOpen(viewingJob) && (
            <div className={styles.formField}>
              <span className={styles.formLabel}>현재 진행 중인 작업</span>
              <div className={styles.jobActivityCurrent} aria-live="polite">
                <Icon name="loader" size={16} spin color="var(--color-primary)" />
                <span>{viewingJob.progress_message}</span>
                {viewingJob.progress_total !== null && viewingJob.progress_total > 0 && (
                  <strong>
                    {viewingJob.progress_current ?? 0}/{viewingJob.progress_total}
                  </strong>
                )}
              </div>
              {recentProgressEvents(viewingJob).length > 0 && (
                <ol className={styles.jobActivityHistory} aria-label="최근 완료한 검증 작업">
                  {recentProgressEvents(viewingJob).map((event, index) => (
                    <li key={`${event.at}-${index}`}>
                      <Icon name="check" size={12} color="var(--color-success)" />
                      <span>{event.message}</span>
                      {event.total !== null && event.total > 0 && (
                        <strong>{event.current ?? 0}/{event.total}</strong>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
          {viewingJob?.status === 'FAILED' && (
            <>
              <div className={styles.failurePanel}>
                <div className={styles.failurePanelHead}>
                  <Icon name="triangle-alert" size={17} color="var(--color-danger)" />
                  <strong>{getSkillJobFailureCopy(viewingJob).reason}</strong>
                </div>
                <div className={styles.failureNext}>
                  <span>다시 만들 때</span>
                  <p>{getSkillJobFailureCopy(viewingJob).suggestion}</p>
                </div>
              </div>
              {viewingJob.candidate_document && (
                <details className={styles.repairDraft}>
                  <summary>검증한 스킬 내용 전체 보기</summary>
                  <div><span>이름</span><strong>{viewingJob.candidate_document.name}</strong></div>
                  <div><span>설명</span><p>{viewingJob.candidate_document.description}</p></div>
                  <div><span>내용</span><pre>{viewingJob.candidate_document.body || '작성된 내용이 없습니다.'}</pre></div>
                </details>
              )}
              {viewingJob.failure_code === 'SKILL_NAME_CONFLICT' &&
                Array.isArray(viewingJob.failure_details?.suggested_names) &&
                viewingJob.failure_details.suggested_names.length > 0 && (
                  <div className={styles.formField}>
                    <span className={styles.formLabel}>다른 이름 제안</span>
                    <div className={styles.filterRow}>
                      {viewingJob.failure_details.suggested_names.map((name) => (
                        <Button
                          key={String(name)}
                          variant="outline"
                          onClick={() => void openRepair(
                            viewingJob,
                            `스킬 이름을 ${String(name)}(으)로 바꿔 주세요.`,
                          )}
                        >
                          {String(name)}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
            </>
          )}
          {viewingJob?.status === 'CANCELED' && (
            <p className={styles.cardSub}>취소된 작업입니다. 실제 스킬은 등록되지 않았습니다.</p>
          )}
          {viewingJob?.status === 'SUCCEEDED' && (
            <p className={styles.cardSub}>검증을 통과해 내 스킬에 등록되었습니다.</p>
          )}
        </div>
      </Modal>

      <Modal
        open={repairingJob !== null}
        onClose={() => {
          if (repairSubmitting) return;
          setRepairingJob(null);
          setRepairInstruction('');
        }}
        title="실패한 스킬 보완"
        footer={(
          <>
            <Button
              variant="outline"
              disabled={repairSubmitting}
              onClick={() => {
                setRepairingJob(null);
                setRepairInstruction('');
              }}
            >
              취소
            </Button>
            <Button
              variant="primary"
              disabled={!repairInstruction.trim() || repairSubmitting}
              onClick={() => void submitRepair()}
            >
              {repairSubmitting ? '준비 중…' : '다시 만들기'}
            </Button>
          </>
        )}
      >
        <div className={styles.formStack}>
          {repairingJob?.candidate_document && (
            <div className={styles.repairDraft}>
              <div>
                <span>이름</span>
                <strong>{repairingJob.candidate_document.name}</strong>
              </div>
              <div>
                <span>설명</span>
                <p>{repairingJob.candidate_document.description}</p>
              </div>
              <div>
                <span>현재 내용</span>
                <pre>{repairingJob.candidate_document.body || '작성된 내용이 없습니다.'}</pre>
              </div>
            </div>
          )}
          {repairingJob && (
            <>
              <div className={styles.formField}>
                <span className={styles.formLabel}>왜 보완이 필요한가요?</span>
                <p className={`${styles.notice} ${styles.noticeDanger}`}>
                  {getSkillJobFailureCopy(repairingJob).reason}
                </p>
              </div>
              <div className={styles.formField}>
                <span className={styles.formLabel}>현재 초안에 부족한 내용</span>
                <p className={`${styles.notice} ${styles.noticeNeutral}`}>
                  {getSkillJobRepairCopy(repairingJob).missing}
                </p>
              </div>
            </>
          )}
          <div className={styles.formField}>
            <label className={styles.formLabel} htmlFor="skill-repair-instruction">
              {repairingJob ? getSkillJobRepairCopy(repairingJob).question : '추가할 내용을 알려주세요.'}
            </label>
            <textarea
              id="skill-repair-instruction"
              className={styles.formTextarea}
              rows={5}
              autoFocus
              value={repairInstruction}
              placeholder={repairingJob ? getSkillJobRepairCopy(repairingJob).placeholder : '추가할 내용을 적어주세요.'}
              disabled={repairSubmitting}
              onChange={(event) => setRepairInstruction(event.target.value)}
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={viewingSkill !== null}
        onClose={() => setViewingSkill(null)}
        title="팀 스킬 내용"
        footer={(
          <Button variant="primary" onClick={() => setViewingSkill(null)}>
            확인
          </Button>
        )}
      >
        <div className={styles.formStack}>
          <div className={styles.formField}>
            <span className={styles.formLabel}>이름</span>
            <p className={styles.confirmText}>{viewingSkill?.name}</p>
          </div>
          <div className={styles.formField}>
            <span className={styles.formLabel}>설명</span>
            <p className={styles.confirmText}>{viewingSkill?.description}</p>
          </div>
          <div className={styles.formField}>
            <span className={styles.formLabel}>내용</span>
            <pre className={styles.skillBodyPreview}>{viewingSkill?.body || '작성된 내용이 없습니다.'}</pre>
          </div>
        </div>
      </Modal>

      {/* 「내 파일」 삭제와 같은 꼴로 묻는다 — 되돌릴 수 없는 것은 무엇이
          사라지는지 먼저 말한다. */}
      <Modal
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title="스킬 삭제"
        footer={(
          <>
            <Button variant="outline" onClick={() => setConfirming(null)}>
              취소
            </Button>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => confirming && void remove(confirming.scope, confirming.skill)}
            >
              {busy ? '삭제하는 중…' : '삭제'}
            </Button>
          </>
        )}
      >
        <p className={styles.confirmText}>
          <strong>{confirming?.skill.name}</strong>
          {josa(confirming?.skill.name ?? '', '을/를')} 삭제합니다. <strong>되돌릴 수 없습니다.</strong>
        </p>
        <p className={styles.confirmText}>
          {confirming?.scope === 'team'
            ? '팀 공유 목록에서만 삭제됩니다. 팀원이 이미 가져간 개인 사본은 삭제되지 않습니다.'
            : '에이전트가 더 이상 이 절차를 따르지 않습니다.'}
        </p>
      </Modal>
    </div>
  );
}
